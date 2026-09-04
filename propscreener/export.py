"""Eksport: JSON (kanonisk), CSV (regneark) og statisk dashboard med indlejrede data."""
from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .models import BankruptcyCase

TEMPLATE_DIR = Path(__file__).parent / "templates"
DATA_MARKER = "/*__PROPSCREENER_DATA__*/null"

CSV_COLUMNS = [
    ("score", lambda c: c.score),
    ("konfidens", lambda c: c.konfidens),
    ("cvr", lambda c: c.selskab.cvr),
    ("navn", lambda c: c.selskab.navn),
    ("selskabsform", lambda c: c.selskab.selskabsform),
    ("branche", lambda c: c.selskab.branchekode),
    ("branchetekst", lambda c: c.selskab.branchetekst),
    ("region", lambda c: c.selskab.region),
    ("kommune", lambda c: c.selskab.kommune),
    ("postnr", lambda c: c.selskab.postnr),
    ("by", lambda c: c.selskab.by),
    ("dekretdato", lambda c: c.dekretdato),
    ("offentliggjort", lambda c: c.offentliggjort),
    ("anmeldelsesfrist", lambda c: c.anmeldelsesfrist),
    ("skifteret", lambda c: c.skifteret.navn),
    ("sagsnummer", lambda c: c.skifteret.sagsnummer),
    ("kurator", lambda c: c.kurator.navn),
    ("kurator_firma", lambda c: c.kurator.firma),
    ("kurator_email", lambda c: c.kurator.email),
    ("kurator_telefon", lambda c: c.kurator.telefon),
    ("ejendomstype", lambda c: c.ejendomstype_hoved),
    ("antal_ejendomme", lambda c: len(c.ejendomme)),
    ("ejendomsvaerdi_bogfoert", lambda c: c.regnskab.ejendomsvaerdi_bogfoert),
    ("offentlig_vurdering_sum", lambda c: sum(p.offentlig_vurdering or 0 for p in c.ejendomme) or None),
    ("aktiver", lambda c: c.regnskab.aktiver),
    ("egenkapital", lambda c: c.regnskab.egenkapital),
    ("realkreditgaeld", lambda c: c.regnskab.realkreditgaeld),
    ("samlet_gaeld", lambda c: c.regnskab.samlet_gaeld),
    ("ltv_pct", lambda c: c.regnskab.ltv_pct),
    ("soliditet_pct", lambda c: c.regnskab.soliditet_pct),
    ("aarets_resultat", lambda c: c.regnskab.aarets_resultat),
    ("regnskabsaar_slut", lambda c: c.regnskab.regnskabsaar_slut),
    ("statstidende_url", lambda c: c.statstidende_url),
    ("cvr_url", lambda c: c.links.get("cvr")),
    ("aarsrapport_url", lambda c: c.links.get("aarsrapport")),
]


def build_dataset(cases: list[BankruptcyCase], stats: Any, demo: bool = False) -> dict[str, Any]:
    return {
        "meta": {
            "genereret": datetime.now(UTC).isoformat(timespec="seconds"),
            "version": __version__,
            "antal": len(cases),
            "demo": demo,
            "kilder_aktive": getattr(stats, "kilder_aktive", []),
            "stats": asdict(stats) if hasattr(stats, "__dataclass_fields__") else stats,
        },
        "cases": [c.to_dict() for c in cases],
    }


def write_json(dataset: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dataset, ensure_ascii=False, indent=1), encoding="utf-8")


def write_csv(cases: list[BankruptcyCase], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow([name for name, _ in CSV_COLUMNS])
        for c in cases:
            w.writerow(["" if (v := fn(c)) is None else v for _, fn in CSV_COLUMNS])


def build_site(dataset: dict[str, Any], out_path: Path, template: Path | None = None) -> Path:
    """Indlejr datasættet i dashboard-skabelonen så den kan åbnes uden server (og som artifact)."""
    template = template or TEMPLATE_DIR / "dashboard.html"
    html = template.read_text(encoding="utf-8")
    payload = json.dumps(dataset, ensure_ascii=False).replace("</", "<\\/")
    if DATA_MARKER not in html:
        raise RuntimeError(f"Skabelonen mangler markøren {DATA_MARKER}")
    html = html.replace(DATA_MARKER, payload, 1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def load_cases(path: Path) -> tuple[list[BankruptcyCase], dict[str, Any]]:
    d = json.loads(path.read_text(encoding="utf-8"))
    return [BankruptcyCase.from_dict(x) for x in d["cases"]], d.get("meta", {})
