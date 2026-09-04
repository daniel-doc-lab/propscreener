"""Datafordelerens fildownload (ny platform, verificeret 4. sep. 2026).

    GET https://api.datafordeler.dk/FileDownloads/GetAvailableFileDownloads?Register=EJF&apikey=…
    GET https://api.datafordeler.dk/FileDownloads/v1.0/GetFile?Filename=<fileName>&apikey=…
    GET …/GetFile?Register=EJF&LatestTotalForEntity=Ejerskab&Type=Current&Format=csv&apikey=…

Frie registre (DAR, BBR, MAT, EBR, VUR) kan hentes med API-Key. Ejerfortegnelsen (EJF) kræver
OAuth (client credentials mod https://auth.datafordeler.dk/realms/distribution/protocol/openid-connect/token)
og en godkendt "Anmodning om adgang" i Datafordeler Administration.

Vi bygger kompakte indekser af de landsdækkende totaldownloads (CSV, streamet fra zip):
  * EJF  Ejerskab                -> cvr -> [{bfe, andel, ejerforhold}]
  * VUR  ejendomsvurdering       -> bfe -> {ejendomsvaerdi, grundvaerdi, aar}
  * EBR  Ejendomsbeliggenhed     -> bfe -> {adresse, postnr, by, kommune}
Indekserne gemmes som gzip-JSON i en mappe og genbruges af pipelinen (Actions-cache).
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import logging
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..config import Settings
from ..http import Http, HttpError

log = logging.getLogger(__name__)

FILES_BASE = "https://api.datafordeler.dk/FileDownloads"
TOKEN_URL = "https://auth.datafordeler.dk/realms/distribution/protocol/openid-connect/token"


@dataclass
class FileInfo:
    file_name: str
    register: str
    entity: str
    type_of_download: str
    type_of_data: str
    fmt: str
    municipality: str | None
    generated: str
    size: int

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> FileInfo:
        return cls(
            file_name=d.get("fileName", ""), register=d.get("register", ""), entity=d.get("entityName", ""),
            type_of_download=d.get("typeOfDownload", ""), type_of_data=d.get("typeOfData", ""),
            fmt=d.get("containedFileFormat", ""), municipality=d.get("municipalityCode"),
            generated=d.get("generationTime", ""), size=int(d.get("fileSizeInBytes") or 0),
        )


class DatafordelerFiles:
    def __init__(self, settings: Settings, http: Http):
        self.s = settings
        self.http = http
        self._token: str | None = None
        self._token_exp = 0.0

    # -- auth ---------------------------------------------------------------
    def _auth_params(self) -> dict[str, str]:
        if self.s.datafordeler_client_id and self.s.datafordeler_client_secret:
            return {}
        return {"apikey": self.s.datafordeler_api_key} if self.s.datafordeler_api_key else {}

    def _auth_headers(self) -> dict[str, str]:
        if not (self.s.datafordeler_client_id and self.s.datafordeler_client_secret):
            return {}
        if self._token and time.time() < self._token_exp - 30:
            return {"Authorization": f"Bearer {self._token}"}
        import requests

        r = requests.post(self.s.datafordeler_token_url, data={
            "grant_type": "client_credentials", "client_id": self.s.datafordeler_client_id,
            "client_secret": self.s.datafordeler_client_secret}, timeout=30)
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._token_exp = time.time() + float(body.get("expires_in", 300))
        return {"Authorization": f"Bearer {self._token}"}

    # -- listing ------------------------------------------------------------
    def list_files(self, register: str) -> list[FileInfo]:
        body = self.http.get_json(f"{FILES_BASE}/GetAvailableFileDownloads",
                                  params={"Register": register, **self._auth_params()},
                                  headers=self._auth_headers() or None, cache_ttl_s=None)
        items = body.get("availableFileDownloads", []) if isinstance(body, dict) else []
        return [FileInfo.from_json(x) for x in items]

    def entities(self, register: str) -> dict[str, list[str]]:
        """Entitetsnavn -> [typeOfDownload/typeOfData/format] – til opdagelse af navne."""
        out: dict[str, set[str]] = {}
        for f in self.list_files(register):
            out.setdefault(f.entity, set()).add(f"{f.type_of_download}/{f.type_of_data}/{f.fmt}"
                                                 + ("/kommune" if f.municipality else ""))
        return {k: sorted(v) for k, v in sorted(out.items())}

    def latest_total(self, register: str, entity_pattern: str, fmt: str = "csv",
                     type_of_data: str | tuple[str, ...] = ("Current", "Temporal", "Bitemporal")) -> FileInfo | None:
        """Nyeste landsdækkende totaludtræk. VUR udstilles fx kun bitemporalt (verificeret 4/9-2026),
        så vi prøver datatyperne i rækkefølge og lader indeksbyggerne filtrere til gældende rækker."""
        pat = re.compile(entity_pattern, re.IGNORECASE)
        kinds = (type_of_data,) if isinstance(type_of_data, str) else type_of_data
        files = [f for f in self.list_files(register)
                 if pat.search(f.entity) and f.type_of_download == "TotalDownload"
                 and f.fmt.lower() == fmt and not f.municipality]
        for kind in kinds:
            cands = [f for f in files if f.type_of_data == kind]
            if cands:
                cands.sort(key=lambda f: f.generated, reverse=True)
                return cands[0]
        return None

    # -- download -----------------------------------------------------------
    def download(self, info: FileInfo, dest: Path) -> Path:
        import requests

        dest.parent.mkdir(parents=True, exist_ok=True)
        params = {"Filename": info.file_name, **self._auth_params()}
        with requests.get(f"{FILES_BASE}/v1.0/GetFile", params=params, headers=self._auth_headers() or None,
                          stream=True, timeout=600) as r:
            if r.status_code >= 400:
                raise HttpError(r.status_code, r.url, r.text[:200])
            with dest.open("wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
        log.info("hentet %s (%.1f MB)", info.file_name, dest.stat().st_size / 1e6)
        return dest

    @staticmethod
    def iter_csv_rows(zip_path: Path) -> Iterable[dict[str, str]]:
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if not name.lower().endswith(".csv"):
                    continue
                with zf.open(name) as raw:
                    text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                    sample = text.read(4096)
                    text.seek(0) if text.seekable() else None
                    dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t") if sample else csv.excel
                    with zf.open(name) as raw2:
                        text2 = io.TextIOWrapper(raw2, encoding="utf-8-sig", newline="")
                        yield from csv.DictReader(text2, dialect=dialect)


# ---------------------------------------------------------------- indeksbygning

def _col(row: dict[str, str], *patterns: str) -> str | None:
    for pat in patterns:
        rx = re.compile(pat, re.IGNORECASE)
        for k, v in row.items():
            if k and rx.search(k) and v not in (None, ""):
                return v
    return None


def _is_current(row: dict[str, str]) -> bool:
    """Gældende række i et (bi)temporalt udtræk: status gældende og hverken registrerings- eller virkningstid lukket."""
    status = _col(row, r"^status$", r"^registreringsstatus$")
    if status and status.lower() not in ("gældende", "gaeldende", "aktiv", "current"):
        return False
    for k, v in row.items():
        if k and re.search(r"(registrering|virkning)Til$", k, re.IGNORECASE) and v not in (None, ""):
            return False
    return True


def build_ejf_index(rows: Iterable[dict[str, str]]) -> dict[str, list[dict[str, Any]]]:
    """Ejerskab-rækker -> {cvr: [{bfe, andel, ejerforhold}]}. Kun virksomhedsejere (CVR)."""
    idx: dict[str, list[dict[str, Any]]] = {}
    n = 0
    for row in rows:
        n += 1
        if not _is_current(row):
            continue
        cvr = _col(row, r"cvr", r"ejendeVirksomhed", r"virksomhed")
        bfe = _col(row, r"bfe")
        if not cvr or not bfe:
            continue
        cvr = re.sub(r"\D", "", cvr)
        if len(cvr) != 8:
            continue
        t, nv = _col(row, r"taeller|tæller"), _col(row, r"naevner|nævner")
        idx.setdefault(cvr, []).append({
            "bfe": int(re.sub(r"\D", "", bfe) or 0), "andel": f"{t}/{nv}" if t and nv else None,
            "ejerforhold": _col(row, r"ejerforhold"), "fra": _col(row, r"virkningFra|gyldigFra|overtagelse"),
        })
        if n % 500_000 == 0:
            log.info("ejerskab: %d rækker, %d virksomheder", n, len(idx))
    return idx


def build_bfe_xref(rows: Iterable[dict[str, str]]) -> dict[str, int]:
    """VUR BFEKrydsreference: vurderingsejendom-id -> BFE-nummer (kun gældende rækker)."""
    xref: dict[str, int] = {}
    for row in rows:
        if not _is_current(row):
            continue
        vid = _col(row, r"vurderingsejendom", r"VURejendom", r"ejendomsid")
        bfe = _col(row, r"bfe")
        if vid and bfe:
            xref[vid.strip()] = int(re.sub(r"\D", "", bfe) or 0)
    return xref


def build_vur_index(rows: Iterable[dict[str, str]], wanted_bfe: set[int] | None = None,
                    xref: dict[str, int] | None = None) -> dict[str, dict[str, Any]]:
    """Ejendomsvurdering-rækker -> {bfe: {ejendomsvaerdi, grundvaerdi, aar}}, seneste vurderingsår vinder.
    BFE tages fra rækken selv eller via krydsreferencen (vurderingsejendom-id -> BFE)."""
    idx: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not _is_current(row):
            continue
        bfe = _col(row, r"bfe")
        b = int(re.sub(r"\D", "", bfe) or 0) if bfe else 0
        if not b and xref:
            vid = _col(row, r"vurderingsejendom", r"VURejendom", r"ejendomsid")
            b = xref.get((vid or "").strip(), 0)
        if not b:
            continue
        if wanted_bfe is not None and b not in wanted_bfe:
            continue
        val = _col(row, r"^ejendomsv(ae|æ)rdi", r"ejendomsvaerdi", r"ejendomsværdi")
        grund = _col(row, r"grundv(ae|æ)rdi")
        aar = _col(row, r"vurderings(aar|år)", r"^aar$|^år$")
        entry = {"ejendomsvaerdi": _num(val), "grundvaerdi": _num(grund), "aar": aar}
        prev = idx.get(str(b))
        if prev is None or (aar or "") >= (prev.get("aar") or ""):
            idx[str(b)] = entry
    return idx


def build_ebr_index(rows: Iterable[dict[str, str]], wanted_bfe: set[int] | None = None) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for row in rows:
        bfe = _col(row, r"bfe")
        if not bfe:
            continue
        b = int(re.sub(r"\D", "", bfe) or 0)
        if wanted_bfe is not None and b not in wanted_bfe:
            continue
        idx[str(b)] = {
            "adresse": _col(row, r"adressebetegnelse", r"betegnelse", r"vejnavn"),
            "kommune": _col(row, r"kommunekode", r"kommune"),
            "adresse_id": _col(row, r"adresseIdentificerer|husnummer|adgangsadresse"),
        }
    return idx


def _num(v: str | None) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(float(str(v).replace(".", "").replace(",", ".")))
    except ValueError:
        return None


def save_index(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)


def load_index(path: Path) -> Any | None:
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)
