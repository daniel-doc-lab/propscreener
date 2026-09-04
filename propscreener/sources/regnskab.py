"""Årsrapporter fra Erhvervsstyrelsens offentlige regnskabsindeks.

Indekset er et åbent Elasticsearch-endpoint uden login:
    http://distribution.virk.dk/offentliggoerelser/_search
Hvert hit indeholder `dokumenter[]` med `dokumentUrl` + `dokumentMimeType`
(application/xml = XBRL, application/pdf = den juridisk gyldige rapport,
application/xhtml+xml = Inline XBRL fra 2025).
Dokumentation: https://datacvr.virk.dk/artikel/system-til-system-adgang-til-regnskabsdata
"""
from __future__ import annotations

import logging
from typing import Any

from ..config import Settings
from ..http import Http
from ..models import BankruptcyCase, Financials
from ..xbrl import CONCEPTS, parse_xbrl

log = logging.getLogger(__name__)


class RegnskabClient:
    def __init__(self, settings: Settings, http: Http):
        self.s = settings
        self.http = http

    def latest_reports(self, cvr: str, n: int = 3) -> list[dict[str, Any]]:
        q = {
            "query": {"bool": {"must": [{"term": {"cvrNummer": int(cvr)}}]}},
            "sort": [{"offentliggoerelsesTidspunkt": {"order": "desc"}}],
            "size": n,
        }
        body = self.http.post_json(self.s.regnskab_es_base, q, cache_ttl_s=7 * 24 * 3600)
        return [h["_source"] for h in body.get("hits", {}).get("hits", [])]

    def fetch_financials(self, cvr: str) -> Financials | None:
        try:
            reports = self.latest_reports(cvr)
        except Exception as e:  # noqa: BLE001
            log.warning("regnskabsindeks fejl for %s: %s", cvr, e)
            return None
        for rep in reports:
            docs = rep.get("dokumenter") or []
            xbrl = next((d for d in docs if "xml" in (d.get("dokumentMimeType") or "")), None)
            pdf = next((d for d in docs if "pdf" in (d.get("dokumentMimeType") or "")), None)
            if not xbrl:
                continue
            try:
                content = self.http.get_text(xbrl["dokumentUrl"], cache_ttl_s=30 * 24 * 3600)
                facts = parse_xbrl(content)
            except Exception as e:  # noqa: BLE001
                log.warning("XBRL parse fejl %s: %s", xbrl.get("dokumentUrl"), e)
                continue
            fin = Financials(
                regnskabsaar_slut=facts.period_end or (rep.get("regnskab", {}).get("regnskabsperiode", {}) or {}).get("slutDato"),
                kilde_url=(pdf or xbrl).get("dokumentUrl"),
            )
            for concept, attr in CONCEPTS.items():
                if concept in facts.values and getattr(fin, attr) is None:
                    setattr(fin, attr, facts.values[concept])
            return fin
        return None


def derive_ratios(f: Financials) -> Financials:
    inv, lab = f.investeringsejendomme or 0, f.grunde_og_bygninger or 0
    prop = max(inv, lab) if (inv or lab) else None
    f.ejendomsvaerdi_bogfoert = prop
    if f.aktiver:
        if prop:
            f.ejendomsandel_pct = round(100 * prop / f.aktiver, 1)
        if f.egenkapital is not None:
            f.soliditet_pct = round(100 * f.egenkapital / f.aktiver, 1)
    if prop and f.realkreditgaeld:
        f.ltv_pct = round(100 * f.realkreditgaeld / prop, 1)
    debts = [d for d in (f.langfristet_gaeld, f.kortfristet_gaeld) if d is not None]
    if debts:
        f.samlet_gaeld = sum(debts)
    elif f.aktiver is not None and f.egenkapital is not None:
        f.samlet_gaeld = f.aktiver - f.egenkapital
    return f


def enrich_with_regnskab(case: BankruptcyCase, client: RegnskabClient) -> BankruptcyCase:
    if not case.selskab.cvr:
        return case
    fin = client.fetch_financials(case.selskab.cvr)
    if fin:
        case.regnskab = derive_ratios(fin)
        case.kilder.append("regnskab-xbrl")
        if fin.kilde_url:
            case.links["aarsrapport"] = fin.kilde_url
    else:
        case.noter.append("Ingen XBRL-årsrapport fundet (nystiftet, holding uden pligt eller kun PDF)")
    return case
