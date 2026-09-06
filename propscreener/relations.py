"""Koncern-relationer mellem konkursboer.

Der findes ingen åben CVR-kilde med ejerstruktur (Erhvervsstyrelsens system-til-system-adgang
kræver aftale, og datacvr.virk.dk er bag Cloudflare). I stedet afledes *sandsynlige* koncern-
forhold af de data vi har for alle dekreter i perioden – også de boer der ikke selv ejer ejendom:

  * samme hjemstedsadresse (adresse + postnr)
  * samme registrerede ejer/ledelse (når CVR-kilden leverer navne)
  * samme navnestamme ("Kystparken Holding ApS" / "Kystparken Ejendomme ApS") kombineret med
    samme kurator, postnr eller dekretdato
  * samme kurator og dekret inden for 3 dage kombineret med navnestamme eller adresse

Hver relation gemmes på begge boer med begrundelse, så investoren kan vurdere dem selv.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any, Iterable

from .models import BankruptcyCase

GENERIC = {
    "aps", "a/s", "as", "k/s", "ks", "p/s", "ps", "i/s", "is", "ivs", "smba", "amba", "holding", "ejendomme",
    "ejendom", "ejendomsselskab", "ejendomsselskabet", "invest", "investering", "gruppen", "group", "danmark",
    "denmark", "selskabet", "selskab", "af", "og", "the", "company", "co", "nordic", "dk", "boliger", "bolig",
    "properties", "property", "development", "byg", "entreprise", "partners", "capital", "kapital", "real",
    "estate", "under", "konkurs", "tvangsopløsning", "likvidation", "anpartsselskab", "aktieselskab", "ny",
    "nye", "dansk", "danske", "nordisk", "scandinavian", "international", "trading", "consulting", "service",
    "projekt", "project", "komplementar", "komplementarselskabet", "komplementarselskab", "kommanditselskabet",
}
MAX_STEM_GROUP = 8


def name_stem(navn: str | None) -> str | None:
    """Første betydende ord i selskabsnavnet, fx 'kystparken' for 'Kystparken Ejendomme ApS'."""
    if not navn:
        return None
    n = re.sub(r"\s+(under\s+(?:tvangsopløsning|likvidation|rekonstruktion|konkurs)|i\s+likvidation)\b.*$", "",
               navn, flags=re.IGNORECASE)
    toks = [t for t in re.split(r"[^\wæøåÆØÅ/]+", n.lower()) if t]
    for t in toks:
        if t in GENERIC or t.isdigit() or len(t) < 4:
            continue
        return t
    return None


def _addr_key(c: BankruptcyCase) -> str | None:
    s = c.selskab
    if not s.adresse or not s.postnr:
        return None
    a = re.sub(r"[^\wæøå]+", " ", s.adresse.lower()).strip()
    a = re.sub(r"\b(st|th|tv|mf|sal|\d+\.)\b", "", a).strip()
    return f"{a}|{s.postnr}"


def _days(a: str | None, b: str | None) -> int | None:
    try:
        return abs((date.fromisoformat(a) - date.fromisoformat(b)).days) if a and b else None
    except ValueError:
        return None


def compute_relations(cases: Iterable[BankruptcyCase], min_score: int = 0) -> int:
    """Sætter `relationer` på alle boer. Returnerer antal boer med mindst én relation."""
    cases = list(cases)
    for c in cases:
        c.relationer = []
    by_addr: dict[str, list[BankruptcyCase]] = defaultdict(list)
    by_owner: dict[str, list[BankruptcyCase]] = defaultdict(list)
    by_stem: dict[str, list[BankruptcyCase]] = defaultdict(list)
    for c in cases:
        k = _addr_key(c)
        if k:
            by_addr[k].append(c)
        for o in list(c.selskab.ejere) + list(c.selskab.ledelse):
            if o and len(o) > 5:
                by_owner[o.strip().lower()].append(c)
        st = name_stem(c.selskab.navn)
        if st:
            by_stem[st].append(c)

    reasons: dict[tuple[str, str], list[str]] = defaultdict(list)

    def link(a: BankruptcyCase, b: BankruptcyCase, why: str) -> None:
        if a is b or a.id == b.id:
            return
        key = (a.id, b.id) if a.id < b.id else (b.id, a.id)
        if why not in reasons[key]:
            reasons[key].append(why)

    for group in by_addr.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                link(a, b, "samme hjemstedsadresse")
    for name, group in by_owner.items():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                link(a, b, f"samme ejer/ledelse ({name.title()})")
    for stem, group in by_stem.items():
        if len(group) > MAX_STEM_GROUP:
            continue
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                same_kur = a.kurator.navn and a.kurator.navn == b.kurator.navn
                same_post = a.selskab.postnr and a.selskab.postnr == b.selskab.postnr
                d = _days(a.dekretdato, b.dekretdato)
                if same_kur or same_post or (d is not None and d <= 3):
                    why = f"fælles navnestamme »{stem}«" + (" og samme kurator" if same_kur else
                                                            " og samme postnummer" if same_post else " og dekret samme dage")
                    link(a, b, why)
    # samme kurator + dekret inden for 3 dage + (adresse eller stamme) er dækket ovenfor; tilføj ren kurator+dato
    # kun når parret allerede er forbundet, som ekstra begrundelse
    by_id = {c.id: c for c in cases}
    for (ia, ib), why in reasons.items():
        a, b = by_id[ia], by_id[ib]
        d = _days(a.dekretdato, b.dekretdato)
        if a.kurator.navn and a.kurator.navn == b.kurator.navn and d is not None and d <= 3 \
                and "samme kurator og dekret samme dage" not in why:
            why.append("samme kurator og dekret samme dage")

    def entry(o: BankruptcyCase, why: list[str]) -> dict[str, Any]:
        return {
            "id": o.id, "cvr": o.selskab.cvr, "navn": o.selskab.navn, "score": o.score, "konfidens": o.konfidens,
            "dekretdato": o.dekretdato, "branchetekst": o.selskab.branchetekst, "by": o.selskab.by,
            "ejendomsvaerdi": o.regnskab.ejendomsvaerdi_bogfoert, "antal_ejendomme": len(o.ejendomme),
            "statstidende_url": o.statstidende_url, "i_registret": o.score >= min_score, "grund": list(why),
        }

    for (ia, ib), why in reasons.items():
        a, b = by_id[ia], by_id[ib]
        a.relationer.append(entry(b, why))
        b.relationer.append(entry(a, why))
    n = 0
    for c in cases:
        c.relationer.sort(key=lambda r: (-len(r["grund"]), -(r["score"] or 0)))
        c.relationer = c.relationer[:12]
        n += bool(c.relationer)
    return n
