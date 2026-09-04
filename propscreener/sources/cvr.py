"""CVR-berigelse.

Primær kilde: cvrapi.dk (gratis, offentlig, kræver blot en beskrivende User-Agent).
Sekundær: Erhvervsstyrelsens system-til-system Elasticsearch (`cvr-permanent`),
som kræver brugeraftale men giver fuld historik, reelle ejere, bibrancher og
status-tidsstempler – og som kan bruges som *alternativ konkurskilde*
(virksomhedsstatus = "UNDER KONKURS"), hvis Statstidende ikke er tilgængelig.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from ..config import Settings
from ..http import Http, HttpError
from ..models import BankruptcyCase, Company

log = logging.getLogger(__name__)

REGION_BY_POSTNR = [
    # (fra, til, region)
    (1000, 2999, "Hovedstaden"), (3000, 3699, "Hovedstaden"), (3700, 3799, "Hovedstaden"),  # Bornholm hører til Hovedstaden
    (3800, 3999, "Grønland/Færøerne"),
    (4000, 4999, "Sjælland"),
    (5000, 5999, "Syddanmark"), (6000, 6999, "Syddanmark"),
    (7000, 7999, "Midtjylland"), (8000, 8999, "Midtjylland"),
    (9000, 9999, "Nordjylland"),
]


def region_for_postnr(postnr: str | None) -> str | None:
    if not postnr or not postnr.isdigit():
        return None
    n = int(postnr)
    # Sydjylland (6000–6999) og Fyn (5000–5999) er Syddanmark; 7000–7999 delvis Syddanmark (Fredericia/Vejle/Kolding)
    if 7000 <= n <= 7199 or 6000 <= n <= 6999 or 5000 <= n <= 5999:
        return "Syddanmark"
    for lo, hi, r in REGION_BY_POSTNR:
        if lo <= n <= hi:
            return r
    return None


class CvrApi:
    """cvrapi.dk – https://cvrapi.dk/documentation (gratis, men med daglig kvote pr. IP)."""

    def __init__(self, settings: Settings, http: Http):
        self.s = settings
        self.http = http
        self.quota_exceeded = False
        self.last_error: str | None = None

    def lookup(self, cvr: str | None = None, name: str | None = None) -> dict[str, Any] | None:
        if self.quota_exceeded:
            return None
        params: dict[str, Any] = {"country": "dk", "format": "json"}
        if cvr:
            params["vat"] = cvr
        elif name:
            params["search"] = name
        else:
            return None
        try:
            body = self.http.get_json(self.s.cvrapi_base, params=params,
                                      headers={"User-Agent": self.s.cvrapi_user_agent}, cache_ttl_s=24 * 3600)
        except HttpError as e:
            log.warning("cvrapi %s: %s", params, e)
            self.last_error = str(e)
            if e.status in (403, 429):
                self.quota_exceeded = True
            return None
        if not isinstance(body, dict) or body.get("error"):
            err = str((body or {}).get("error") if isinstance(body, dict) else body)
            self.last_error = err
            if "QUOTA" in err.upper() or "LIMIT" in err.upper():
                self.quota_exceeded = True
                log.warning("cvrapi: kvote opbrugt (%s) – springer resten over", err)
            return None
        return body

    @staticmethod
    def apply(company: Company, data: dict[str, Any]) -> Company:
        company.cvr = str(data.get("vat") or company.cvr or "")
        company.navn = data.get("name") or company.navn
        company.adresse = data.get("address") or company.adresse
        company.postnr = str(data.get("zipcode") or company.postnr or "") or None
        company.by = data.get("city") or company.by
        company.kommune = data.get("cityname") or company.kommune
        company.stiftet = data.get("startdate") or company.stiftet
        company.status = data.get("status") or company.status
        company.ansatte = _int(data.get("employees")) or company.ansatte
        ic = data.get("industrycode")
        company.branchekode = str(ic) if ic else company.branchekode
        company.branchetekst = data.get("industrydesc") or company.branchetekst
        company.selskabsform = _company_form(data.get("companydesc")) or company.selskabsform
        owners = data.get("owners") or []
        company.ejere = [o.get("name") for o in owners if isinstance(o, dict) and o.get("name")]
        company.region = region_for_postnr(company.postnr)
        company.cvr_url = f"https://datacvr.virk.dk/enhed/virksomhed/{company.cvr}" if company.cvr else None
        return company


class CvrElastic:
    """Erhvervsstyrelsens system-til-system adgang (kræver CVR_ES_USER/PASSWORD)."""

    def __init__(self, settings: Settings, http: Http):
        self.s = settings
        self.http = http

    def _auth(self) -> tuple[str, str]:
        return (self.s.cvr_es_user, self.s.cvr_es_password)

    def get(self, cvr: str) -> dict[str, Any] | None:
        q = {"query": {"term": {"Vrvirksomhed.cvrNummer": int(cvr)}}, "size": 1}
        body = self.http.post_json(self.s.cvr_es_base, q, auth=self._auth(), cache_ttl_s=24 * 3600)
        hits = body.get("hits", {}).get("hits", [])
        return hits[0]["_source"]["Vrvirksomhed"] if hits else None

    def recently_bankrupt(self, days_back: int, size: int = 1000) -> list[dict[str, Any]]:
        """Alternativ konkurskilde: virksomheder der har fået status UNDER KONKURS inden for N dage."""
        since = (date.today() - timedelta(days=days_back)).isoformat()
        q = {
            "size": size,
            "query": {"bool": {"must": [
                {"nested": {"path": "Vrvirksomhed.virksomhedsstatus", "query": {"bool": {"must": [
                    {"match": {"Vrvirksomhed.virksomhedsstatus.status": "UNDER KONKURS"}},
                    {"range": {"Vrvirksomhed.virksomhedsstatus.periode.gyldigFra": {"gte": since}}},
                ]}}}},
            ]}},
            "_source": ["Vrvirksomhed.cvrNummer", "Vrvirksomhed.virksomhedMetadata", "Vrvirksomhed.virksomhedsstatus"],
        }
        body = self.http.post_json(self.s.cvr_es_base, q, auth=self._auth(), cache_ttl_s=3600)
        return [h["_source"]["Vrvirksomhed"] for h in body.get("hits", {}).get("hits", [])]

    @staticmethod
    def apply(company: Company, v: dict[str, Any]) -> Company:
        meta = v.get("virksomhedMetadata", {}) or {}
        company.cvr = str(v.get("cvrNummer") or company.cvr)
        company.navn = (meta.get("nyesteNavn") or {}).get("navn") or company.navn
        company.binavne = [b.get("navn") for b in (v.get("binavne") or []) if b.get("navn") and not b.get("periode", {}).get("gyldigTil")]
        hb = meta.get("nyesteHovedbranche") or {}
        company.branchekode = str(hb.get("branchekode") or company.branchekode or "") or None
        company.branchetekst = hb.get("branchetekst") or company.branchetekst
        company.bibrancher = [str(b.get("branchekode")) for b in (meta.get("nyesteBibranche1"), meta.get("nyesteBibranche2"),
                                                                 meta.get("nyesteBibranche3")) if b and b.get("branchekode")]
        vf = meta.get("nyesteVirksomhedsform") or {}
        company.selskabsform = _company_form(vf.get("kortBeskrivelse") or vf.get("langBeskrivelse")) or company.selskabsform
        addr = meta.get("nyesteBeliggenhedsadresse") or {}
        if addr:
            street = " ".join(x for x in [addr.get("vejnavn"), str(addr.get("husnummerFra") or "")] if x).strip()
            company.adresse = street or company.adresse
            company.postnr = str(addr.get("postnummer") or company.postnr or "") or None
            company.by = addr.get("postdistrikt") or company.by
            company.kommune = (addr.get("kommune") or {}).get("kommuneNavn") or company.kommune
        company.status = meta.get("sammensatStatus") or company.status
        company.stiftet = meta.get("stiftelsesDato") or company.stiftet
        ans = meta.get("nyesteAarsbeskaeftigelse") or {}
        company.ansatte = _int(ans.get("antalAnsatte")) or company.ansatte
        # deltagere: reelle ejere / direktion
        for rel in v.get("deltagerRelation") or []:
            navn = ((rel.get("deltager") or {}).get("navne") or [{}])[-1].get("navn")
            for org in rel.get("organisationer") or []:
                hoved = org.get("hovedtype", "")
                if navn and hoved in ("REGISTER", "FULDT_ANSVARLIG_DELTAGERE") and navn not in company.ejere:
                    company.ejere.append(navn)
                if navn and hoved == "LEDELSESORGAN" and navn not in company.ledelse:
                    company.ledelse.append(navn)
        company.region = region_for_postnr(company.postnr)
        company.cvr_url = f"https://datacvr.virk.dk/enhed/virksomhed/{company.cvr}"
        return company


class StatstidendeCvr:
    """Fallback: statstidende.dk's eget CVR-opslag (GET /api/cvr/{cvr}), som frontend'en bruger.
    Svarets feltnavne er ikke dokumenteret; vi mapper tolerant."""

    KEYS = {
        "navn": ("name", "navn", "companyName", "virksomhedsnavn"),
        "adresse": ("address", "adresse", "street", "vejnavn", "addressLine1"),
        "postnr": ("zipcode", "postnummer", "zip", "postalCode", "postnr"),
        "by": ("city", "by", "postdistrikt", "cityName"),
        "branchekode": ("industrycode", "branchekode", "industryCode", "hovedbranche"),
        "branchetekst": ("industrydesc", "branchetekst", "industryDescription"),
        "selskabsform": ("companydesc", "virksomhedsform", "companyType", "companyForm"),
        "status": ("status", "virksomhedsstatus"),
    }

    def __init__(self, settings: Settings, http: Http):
        self.s = settings
        self.http = http

    def lookup(self, cvr: str) -> dict[str, Any] | None:
        try:
            body = self.http.get_json(f"{self.s.statstidende_web_base}/api/cvr/{cvr}", cache_ttl_s=24 * 3600)
        except HttpError as e:
            log.debug("statstidende cvr %s: %s", cvr, e)
            return None
        if not isinstance(body, dict):
            return None
        inner = body.get("company") if isinstance(body.get("company"), dict) else body
        if not inner or (inner.get("statusCode") not in (None, 200)):
            return None
        return inner

    @classmethod
    def apply(cls, company: Company, data: dict[str, Any]) -> Company:
        low = {k.lower(): v for k, v in data.items()}

        def pick(attr: str) -> Any:
            for k in cls.KEYS[attr]:
                v = low.get(k.lower())
                if v not in (None, "", {}):
                    return v
            return None

        company.navn = pick("navn") or company.navn
        company.adresse = pick("adresse") or company.adresse
        company.postnr = str(pick("postnr") or company.postnr or "") or None
        company.by = pick("by") or company.by
        bc = pick("branchekode")
        if isinstance(bc, dict):
            bc = bc.get("branchekode") or bc.get("code")
        company.branchekode = str(bc) if bc else company.branchekode
        company.branchetekst = pick("branchetekst") or company.branchetekst
        company.selskabsform = _company_form(str(pick("selskabsform") or "")) or company.selskabsform
        company.status = str(pick("status") or company.status or "") or None
        company.region = region_for_postnr(company.postnr)
        company.cvr_url = f"https://datacvr.virk.dk/enhed/virksomhed/{company.cvr}" if company.cvr else None
        return company


def _int(v: Any) -> int | None:
    try:
        return int(str(v).replace(".", "").split("-")[0]) if v not in (None, "") else None
    except ValueError:
        return None


def _company_form(desc: str | None) -> str | None:
    if not desc:
        return None
    d = desc.lower()
    for form, keys in (("ApS", ("anpartsselskab", "aps")), ("A/S", ("aktieselskab", "a/s")),
                       ("K/S", ("kommanditselskab", "k/s")), ("P/S", ("partnerselskab", "p/s")),
                       ("I/S", ("interessentskab", "i/s")), ("IVS", ("iværksætterselskab", "ivs"))):
        if any(k in d for k in keys):
            return form
    return desc.strip()


def enrich_with_cvr(case: BankruptcyCase, api: CvrApi, es: CvrElastic | None,
                    fallback: StatstidendeCvr | None = None) -> BankruptcyCase:
    c = case.selskab
    data = None
    if es is not None and c.cvr:
        try:
            v = es.get(c.cvr)
            if v:
                CvrElastic.apply(c, v)
                case.kilder.append("cvr-es")
                return case
        except Exception as e:  # noqa: BLE001
            log.warning("CVR ES fejl for %s: %s", c.cvr, e)
    data = api.lookup(cvr=c.cvr) if c.cvr else api.lookup(name=c.navn)
    if data:
        CvrApi.apply(c, data)
        case.kilder.append("cvrapi")
        if not case.id or case.id.startswith("st-"):
            case.id = c.cvr or case.id
        case.links["cvr"] = c.cvr_url or case.links.get("cvr", "")
    else:
        alt = fallback.lookup(c.cvr) if (fallback is not None and c.cvr) else None
        if alt:
            StatstidendeCvr.apply(c, alt)
            case.kilder.append("statstidende-cvr")
        else:
            c.region = region_for_postnr(c.postnr)
            why = f" ({api.last_error})" if api.last_error else ""
            case.noter.append(f"CVR-opslag fejlede{why} – branche og ejere mangler")
    return case
