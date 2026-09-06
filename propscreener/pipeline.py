"""Orkestrering: Statstidende -> CVR -> regnskab -> Ejerfortegnelsen -> scoring -> filtrering."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from .config import Settings
from .detect import score_case
from .http import Http
from .models import Auction, BankruptcyCase
from .relations import compute_relations
from .sources.cvr import ApiCvrMcp, ApiCvrRest, CvrApi, CvrElastic, StatstidendeCvr, enrich_with_cvr
from .sources.ejerfortegnelse import (
    DawaClient,
    EjerfortegnelseClient,
    LocalIndexes,
    enrich_with_ejerfortegnelse,
)
from .sources.regnskab import RegnskabClient, enrich_with_regnskab
from .sources.statstidende import (
    StatstidendeClient,
    auction_debtor_keys,
    auction_from_message,
    message_to_case,
    normalize_company_name,
    parse_tvangsauktion,
)

log = logging.getLogger(__name__)


@dataclass
class RunStats:
    started: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    dekreter: int = 0
    tvangsauktioner: int = 0
    auktioner_i_alt: int = 0
    boer_med_relationer: int = 0
    beriget_cvr: int = 0
    beriget_regnskab: int = 0
    beriget_ejf: int = 0
    over_min_score: int = 0
    min_score: int = 0
    bevaret_fra_tidligere: int = 0
    kilder_aktive: list[str] = field(default_factory=list)
    fejl: list[str] = field(default_factory=list)


class Pipeline:
    def __init__(self, settings: Settings, http: Http | None = None):
        self.s = settings
        cert = (settings.statstidende_cert_file, settings.statstidende_key_file) if settings.has_statstidende_cert else None
        self.http = http or Http(settings.user_agent, settings.cache_dir, settings.request_delay_s, settings.timeout_s,
                                 cert=cert)
        self.statstidende = StatstidendeClient(settings, self.http)
        self.cvrapi = CvrApi(settings, self.http)
        self.cvr_es = CvrElastic(settings, self.http) if settings.has_cvr_es else None
        self.cvr_fallback = StatstidendeCvr(settings, self.http)
        self.cvr_mcp = ApiCvrMcp(settings, self.http) if settings.apicvr_mcp_url else None
        self.cvr_rest = ApiCvrRest(settings, self.http) if settings.apicvr_rest_base else None
        self.regnskab = RegnskabClient(settings, self.http)
        self.ejf = EjerfortegnelseClient(settings, self.http) if settings.has_datafordeler else None
        self.dawa = DawaClient(settings, self.http)
        self.local = LocalIndexes(settings.index_dir)
        self.stats = RunStats()
        self.auctions: list[Auction] = []

    # ------------------------------------------------------------------ steps
    def collect_cases(self, date_from: date, date_to: date | None = None) -> list[BankruptcyCase]:
        cases: dict[str, BankruptcyCase] = {}
        for msg in self.statstidende.search("konkurs_dekret", date_from, date_to):
            case = message_to_case(msg)
            if not case.selskab.cvr and not case.selskab.navn:
                continue  # personlig konkurs uden CVR -> ikke relevant
            key = case.selskab.cvr or case.id
            if key in cases:
                continue
            cases[key] = case
        self.stats.dekreter = len(cases)
        return list(cases.values())

    def attach_auctions(self, cases: list[BankruptcyCase], date_from: date) -> None:
        by_cvr = {c.selskab.cvr: c for c in cases if c.selskab.cvr}
        by_name = {normalize_company_name(c.selskab.navn): c for c in cases if c.selskab.navn}
        try:
            msgs = list(self.statstidende.search("tvangsauktion_fast_ejendom", date_from))
        except Exception as e:  # noqa: BLE001
            self.stats.fejl.append(f"tvangsauktioner: {e}")
            return
        seen: set[str] = set()
        for msg in msgs:
            if msg.id in seen:
                continue
            seen.add(msg.id)
            try:
                auction = auction_from_message(msg)
            except Exception as e:  # noqa: BLE001
                log.warning("auktion %s kunne ikke parses: %s", msg.id, e)
                auction = None
            cvr, navn = auction_debtor_keys(msg)
            target = by_cvr.get(cvr or "") or by_name.get(normalize_company_name(navn))
            if auction is not None:
                auction.konkursbo_id = target.id if target is not None else None
                self.auctions.append(auction)
            if target is None:
                continue
            target.ejendomme.append(parse_tvangsauktion(msg))
            target.links.setdefault("tvangsauktion", msg.url)
            if "tvangsauktion" not in target.kilder:
                target.kilder.append("tvangsauktion")
            self.stats.tvangsauktioner += 1
        self.stats.auktioner_i_alt = len(self.auctions)

    def geocode_auctions(self) -> None:
        for a in self.auctions:
            if a.adresse and a.lat is None:
                try:
                    ll = self.dawa.geocode(a.adresse, a.postnr)
                except Exception:  # noqa: BLE001
                    ll = None
                if ll:
                    a.lat, a.lon = ll

    def geocode_companies(self, cases: list[BankruptcyCase]) -> None:
        for c in cases:
            s = c.selskab
            if s.adresse and s.postnr and s.lat is None:
                try:
                    ll = self.dawa.geocode(s.adresse, s.postnr)
                except Exception:  # noqa: BLE001
                    ll = None
                if ll:
                    s.lat, s.lon = ll

    def enrich(self, case: BankruptcyCase) -> BankruptcyCase:
        """Fuld berigelse af ét bo (bruges af tests og `run`). Rækkefølgen i `run` er
        regnskab -> foreløbig score -> CVR (kvote) -> EJF -> endelig score."""
        self.enrich_regnskab(case)
        self.enrich_cvr(case)
        self.enrich_ejf(case)
        return self.finish(case)

    def enrich_regnskab(self, case: BankruptcyCase) -> None:
        enrich_with_regnskab(case, self.regnskab)
        if case.regnskab.aktiver is not None:
            self.stats.beriget_regnskab += 1
        score_case(case)  # foreløbig score (bruges til at prioritere CVR-opslag)

    def enrich_cvr(self, case: BankruptcyCase) -> None:
        enrich_with_cvr(case, self.cvrapi, self.cvr_es, self.cvr_fallback, self.cvr_mcp, self.cvr_rest)
        if case.selskab.branchekode:
            self.stats.beriget_cvr += 1

    def enrich_ejf(self, case: BankruptcyCase) -> None:
        enrich_with_ejerfortegnelse(case, self.ejf, self.dawa, local=self.local)
        if any(p.kilde == "ejerfortegnelsen" for p in case.ejendomme):
            self.stats.beriget_ejf += 1

    def finish(self, case: BankruptcyCase) -> BankruptcyCase:
        score_case(case)
        case.sidst_opdateret = datetime.now(UTC).isoformat(timespec="seconds")
        add_investor_links(case)
        return case

    def run(self, days_back: int | None = None, min_score: int | None = None) -> tuple[list[BankruptcyCase], RunStats]:
        days_back = days_back or self.s.days_back
        min_score = self.s.min_score if min_score is None else min_score
        date_from = date.today() - timedelta(days=days_back)
        self.stats.kilder_aktive = self.active_sources()
        self.stats.min_score = min_score

        cases = self.collect_cases(date_from)
        log.info("%d konkursdekreter fundet siden %s", len(cases), date_from)
        self.attach_auctions(cases, date_from)

        def _safe(step, case: BankruptcyCase) -> None:
            try:
                step(case)
            except Exception as e:  # noqa: BLE001
                log.exception("%s fejlede for %s", step.__name__, case.id)
                self.stats.fejl.append(f"{case.id} {step.__name__}: {e}")
                case.noter.append(f"{step.__name__} fejlede: {e}")

        for i, case in enumerate(cases, 1):
            _safe(self.enrich_regnskab, case)
            if i % 25 == 0:
                log.info("regnskab %d/%d", i, len(cases))
        # CVR-opslag har kvote: tag de mest lovende boer først
        for i, case in enumerate(sorted(cases, key=lambda c: -c.score), 1):
            _safe(self.enrich_cvr, case)
            _safe(self.enrich_ejf, case)
            self.finish(case)
            if i % 25 == 0:
                log.info("cvr/ejf %d/%d", i, len(cases))
        if self.cvrapi.quota_exceeded:
            self.stats.fejl.append(f"cvrapi.dk kvote opbrugt: {self.cvrapi.last_error}")

        self.stats.boer_med_relationer = compute_relations(cases, min_score)
        selected = [c for c in cases if c.score >= min_score]
        selected.sort(key=lambda c: (-c.score, c.dekretdato or "", c.selskab.navn or ""))
        self.stats.over_min_score = len(selected)
        self.geocode_companies(selected)
        self.geocode_auctions()
        return selected, self.stats

    def active_sources(self) -> list[str]:
        src = [f"statstidende:{self.s.statstidende_mode}", "apicvr-rest", "cvrapi", "apicvr-mcp", "regnskab-xbrl", "dawa"]
        if self.cvr_es:
            src.append("cvr-es")
        if self.local.has_ejf:
            src.append("ejerfortegnelsen-indeks")
        elif self.ejf:
            src.append("ejerfortegnelsen")
        if self.local.vur.get("bfe"):
            src.append("vurdering-indeks")
        return src


def add_investor_links(case: BankruptcyCase) -> None:
    c = case.selskab
    if c.cvr:
        case.links.setdefault("cvr", f"https://datacvr.virk.dk/enhed/virksomhed/{c.cvr}")
        case.links.setdefault("regnskaber", f"https://datacvr.virk.dk/enhed/virksomhed/{c.cvr}?tab=regnskaber")
    if c.adresse and c.postnr:
        q = f"{c.adresse}, {c.postnr} {c.by or ''}".strip()
        case.links.setdefault("kort", "https://www.google.com/maps/search/?api=1&query=" + q.replace(" ", "+"))
    case.links.setdefault("tinglysning", "https://www.tinglysning.dk")
    case.links.setdefault("ois", "https://www.ois.dk")
    if case.kurator.advokatsamfundet_url:
        case.links.setdefault("kurator_opslag", case.kurator.advokatsamfundet_url)
