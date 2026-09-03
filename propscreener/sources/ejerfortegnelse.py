"""Ejerfortegnelsen (EJF) via Datafordeleren – det direkte bevis for ejendomsejerskab.

REST-tjenesten `EjendommeMedSammeEjer` returnerer alle ejendomme (BFE-numre)
hvor et CVR-nummer er registreret ejer. Kræver en gratis tjenestebruger på
datafordeler.dk (brugernavn/adgangskode – sæt DATAFORDELER_USER/PASSWORD).

Dokumentation: https://datafordeler.dk/dataoversigt/ejerfortegnelsen-ejf/ejerfortegnelsen/
Bemærk at REST-varianten udfases ultimo 2026 til fordel for en ny; tjenestens
basis-URL er derfor konfigurerbar.

Adresse/BFE-opslag suppleres med DAWA (gratis, ingen login) for koordinater,
og Vurderingsportalen/VUR (Datafordeler) for offentlig ejendomsvurdering.
"""
from __future__ import annotations

import logging
from typing import Any

from ..config import Settings
from ..http import Http
from ..models import BankruptcyCase, Property

log = logging.getLogger(__name__)

EJF_PATH = "/EJERFORTEGNELSE/Ejerfortegnelsen/1/REST/EjendommeMedSammeEjer"
VUR_PATH = "/VUR/VUR/1/REST/BFEejendomsvurdering"  # ejendomsvurdering pr. BFE
DAWA_BFE_PATH = "/adresser"


class EjerfortegnelseClient:
    def __init__(self, settings: Settings, http: Http):
        self.s = settings
        self.http = http

    def _params(self, **kw: Any) -> dict[str, Any]:
        return {"username": self.s.datafordeler_user, "password": self.s.datafordeler_password,
                "format": "json", **kw}

    def properties_for_cvr(self, cvr: str) -> list[Property]:
        url = self.s.datafordeler_base + EJF_PATH
        body = self.http.get_json(url, params=self._params(CVRnr=cvr, pagesize=200), cache_ttl_s=24 * 3600)
        return [self._to_property(x) for x in _iter_ejerskaber(body)]

    @staticmethod
    def _to_property(e: dict[str, Any]) -> Property:
        bfe = e.get("bestemtFastEjendomBFENr") or e.get("bfeNummer") or (e.get("ejendom") or {}).get("bfeNummer")
        p = Property(
            bfe_nummer=str(bfe) if bfe else None,
            ejerandel=_andel(e),
            ejendomstype=e.get("ejendomstype") or (e.get("ejendom") or {}).get("ejendomstype"),
            kilde="ejerfortegnelsen",
        )
        adr = e.get("adresse") or (e.get("ejendom") or {}).get("adresse") or {}
        if isinstance(adr, dict):
            p.adresse = adr.get("adressebetegnelse") or adr.get("vejnavnHusnr")
            p.postnr = str(adr.get("postnummer") or "") or None
            p.by = adr.get("postdistrikt")
            p.kommune = adr.get("kommunenavn")
        elif isinstance(adr, str):
            p.adresse = adr
        return p

    def valuation(self, bfe: str) -> int | None:
        try:
            body = self.http.get_json(self.s.datafordeler_base + VUR_PATH,
                                      params=self._params(BFEnummer=bfe), cache_ttl_s=30 * 24 * 3600)
        except Exception as e:  # noqa: BLE001
            log.debug("VUR fejl %s: %s", bfe, e)
            return None
        items = body if isinstance(body, list) else body.get("features") or body.get("items") or []
        for it in items:
            v = it.get("ejendomsvaerdi") or (it.get("properties") or {}).get("ejendomsvaerdi")
            if v:
                try:
                    return int(float(v))
                except ValueError:
                    pass
        return None


class DawaClient:
    """Danmarks Adressers Web API – gratis geokodning + BFE->adresse."""

    def __init__(self, settings: Settings, http: Http):
        self.s = settings
        self.http = http

    def geocode(self, adresse: str, postnr: str | None) -> tuple[float, float] | None:
        q = f"{adresse}, {postnr}" if postnr else adresse
        try:
            body = self.http.get_json(self.s.dawa_base + "/adresser", params={"q": q, "per_side": 1, "struktur": "mini"},
                                      cache_ttl_s=30 * 24 * 3600)
        except Exception as e:  # noqa: BLE001
            log.debug("DAWA fejl %s: %s", q, e)
            return None
        if isinstance(body, list) and body:
            a = body[0]
            if a.get("x") and a.get("y"):
                return float(a["y"]), float(a["x"])
        return None

    def address_for_bfe(self, bfe: str) -> dict[str, Any] | None:
        try:
            body = self.http.get_json(self.s.dawa_base + "/adresser", params={"bfe": bfe, "per_side": 1, "struktur": "mini"},
                                      cache_ttl_s=30 * 24 * 3600)
        except Exception:  # noqa: BLE001
            return None
        return body[0] if isinstance(body, list) and body else None


def _iter_ejerskaber(body: Any):
    if isinstance(body, list):
        yield from body
    elif isinstance(body, dict):
        for key in ("features", "Ejerskab", "ejerskaber", "items", "data"):
            v = body.get(key)
            if isinstance(v, list):
                for x in v:
                    yield x.get("properties", x) if isinstance(x, dict) else x
                return
        if body.get("bestemtFastEjendomBFENr"):
            yield body


def _andel(e: dict[str, Any]) -> str | None:
    t, n = e.get("ejerandel_taeller") or e.get("ejerandelTaeller"), e.get("ejerandel_naevner") or e.get("ejerandelNaevner")
    if t and n:
        return f"{t}/{n}"
    return e.get("ejerandel")


def enrich_with_ejerfortegnelse(case: BankruptcyCase, ejf: EjerfortegnelseClient | None, dawa: DawaClient | None,
                                geocode: bool = True) -> BankruptcyCase:
    cvr = case.selskab.cvr
    if ejf is not None and cvr:
        try:
            props = ejf.properties_for_cvr(cvr)
        except Exception as e:  # noqa: BLE001
            log.warning("EJF fejl %s: %s", cvr, e)
            props = []
            case.noter.append("Ejerfortegnelsen kunne ikke slås op")
        known = {p.bfe_nummer for p in case.ejendomme if p.bfe_nummer}
        for p in props:
            if p.bfe_nummer and p.bfe_nummer in known:
                continue
            if dawa and p.bfe_nummer and not p.adresse:
                a = dawa.address_for_bfe(p.bfe_nummer)
                if a:
                    p.adresse = a.get("betegnelse") or a.get("vejnavn")
                    p.postnr = str(a.get("postnr") or "") or None
                    p.by = a.get("postnrnavn")
                    p.kommune = a.get("kommunenavn")
                    if a.get("x") and a.get("y"):
                        p.lat, p.lon = float(a["y"]), float(a["x"])
            if p.bfe_nummer:
                p.offentlig_vurdering = ejf.valuation(p.bfe_nummer)
            case.ejendomme.append(p)
        if props:
            case.kilder.append("ejerfortegnelsen")
    if dawa and geocode:
        for p in case.ejendomme:
            if p.adresse and p.lat is None:
                ll = dawa.geocode(p.adresse, p.postnr)
                if ll:
                    p.lat, p.lon = ll
    for p in case.ejendomme:
        if p.bfe_nummer:
            case.links.setdefault("tinglysning", "https://www.tinglysning.dk/tinglysning/ssl/ejendom/bfe")
            case.links.setdefault("ois", f"https://www.ois.dk/ui/property/search?bfe={p.bfe_nummer}")
    return case
