"""Parser til danske XBRL-årsrapporter (Erhvervsstyrelsens taksonomi, `fsa:`-navnerum).

Vi bruger kun standardbiblioteket. Strategien er bevidst tolerant: vi
matcher på lokalnavn (uden navnerum) og vælger for hvert begreb den værdi
hvis kontekst er *seneste balancedag* (instant) eller *seneste periode*
(duration). Det er tilstrækkeligt til nøgletal på selskabsniveau.

Understøtter både klassisk XBRL (.xml) og Inline XBRL (.xhtml, krav fra 2025).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

# Begreber vi udtrækker  ->  feltnavn i Financials
CONCEPTS: dict[str, str] = {
    "Assets": "aktiver",
    "Equity": "egenkapital",
    "InvestmentProperty": "investeringsejendomme",
    "LandAndBuildings": "grunde_og_bygninger",
    "PropertyPlantAndEquipment": "materielle_anlaeg",
    "MortgageDebt": "realkreditgaeld",
    "LongtermMortgageDebt": "realkreditgaeld",
    "LongtermLiabilitiesOtherThanProvisions": "langfristet_gaeld",
    "ShorttermLiabilitiesOtherThanProvisions": "kortfristet_gaeld",
    "Revenue": "omsaetning",
    "GrossProfitLoss": "bruttofortjeneste",
    "ProfitLoss": "aarets_resultat",
    "AverageNumberOfEmployees": "ansatte",
}

# Alias-begreber (ældre taksonomier / IFRS)
ALIASES: dict[str, str] = {
    "InvestmentProperties": "InvestmentProperty",
    "LandAndBuildingsInvestmentProperty": "InvestmentProperty",
    "GrossResult": "GrossProfitLoss",
    "ProfitLossFromOrdinaryOperatingActivities": "ProfitLoss",
    "NoncurrentLiabilitiesOtherThanProvisions": "LongtermLiabilitiesOtherThanProvisions",
    "CurrentLiabilitiesOtherThanProvisions": "ShorttermLiabilitiesOtherThanProvisions",
}


@dataclass
class XbrlContext:
    id: str
    instant: str | None = None
    start: str | None = None
    end: str | None = None
    has_dimensions: bool = False


@dataclass
class XbrlFacts:
    values: dict[str, int] = field(default_factory=dict)   # begreb -> værdi (DKK)
    period_end: str | None = None
    entity_name: str | None = None
    raw_count: int = 0


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag.split(":")[-1]


def _parse_number(text: str | None, scale: str | None, sign: str | None, fmt: str | None) -> int | None:
    if text is None:
        return None
    t = text.strip()
    if not t or t in ("-", "–"):
        return 0 if t else None
    fmt_l = (fmt or "").lower().replace("-", "")
    t = re.sub(r"[^\d,.\-]", "", t)
    if "commadecimal" in fmt_l:          # dansk: 1.234.567,89
        t = t.replace(".", "").replace(",", ".")
    elif "dotdecimal" in fmt_l:          # engelsk: 1,234,567.89
        t = t.replace(",", "")
    elif t.count(",") and t.count("."):
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif t.count(".") > 1:
        t = t.replace(".", "")
    elif t.count(",") == 1 and len(t.split(",")[1]) != 3:
        t = t.replace(",", ".")
    else:
        t = t.replace(",", "")
    try:
        v = float(t)
    except ValueError:
        return None
    if scale:
        try:
            v *= 10 ** int(scale)
        except ValueError:
            pass
    if sign == "-":
        v = -v
    return int(round(v))


def parse_xbrl(content: str | bytes) -> XbrlFacts:
    """Parse XBRL/iXBRL og returnér seneste værdier for CONCEPTS."""
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    # fjern BOM og DOCTYPE der kan forvirre ElementTree
    content = content.lstrip("﻿")
    content = re.sub(r"<!DOCTYPE[^>]*>", "", content, count=1)
    root = ET.fromstring(content)

    contexts: dict[str, XbrlContext] = {}
    for el in root.iter():
        if _local(el.tag) != "context":
            continue
        cid = el.get("id") or ""
        ctx = XbrlContext(id=cid)
        for sub in el.iter():
            ln = _local(sub.tag)
            if ln == "instant":
                ctx.instant = (sub.text or "").strip()
            elif ln == "startDate":
                ctx.start = (sub.text or "").strip()
            elif ln == "endDate":
                ctx.end = (sub.text or "").strip()
            elif ln in ("explicitMember", "typedMember", "segment", "scenario"):
                ctx.has_dimensions = True
        contexts[cid] = ctx

    facts = XbrlFacts()
    candidates: dict[str, list[tuple[str, int]]] = {}

    for el in root.iter():
        ln = _local(el.tag)
        name = el.get("name")  # inline XBRL: <ix:nonFraction name="fsa:Assets">
        if ln in ("nonFraction", "nonNumeric") and name:
            concept = name.split(":")[-1]
        else:
            concept = ln
        concept = ALIASES.get(concept, concept)
        if concept == "NameOfReportingEntity" and not facts.entity_name:
            facts.entity_name = "".join(el.itertext()).strip() or None
            continue
        if concept not in CONCEPTS:
            continue
        ctx = contexts.get(el.get("contextRef") or "")
        if ctx is None or ctx.has_dimensions:
            continue
        value = _parse_number("".join(el.itertext()), el.get("scale"), el.get("sign"), el.get("format"))
        if value is None:
            continue
        facts.raw_count += 1
        date_key = ctx.instant or ctx.end or ""
        candidates.setdefault(concept, []).append((date_key, value))

    for concept, items in candidates.items():
        items.sort(key=lambda x: x[0])
        date_key, value = items[-1]
        facts.values[concept] = value
        if date_key and (facts.period_end is None or date_key > facts.period_end):
            facts.period_end = date_key
    return facts
