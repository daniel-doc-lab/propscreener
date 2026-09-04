"""Ejendomsdetektion: hvilke konkursboer ejer (sandsynligvis) fast ejendom?

Vi kombinerer flere uafhængige signaler og summerer til en score 0–100.
Begrundelsen for hvert point gemmes som `Signal`, så en investor kan se
*hvorfor* et bo er med – og så falske positiver kan afvises manuelt.

Signalhierarki (stærkest først):
  1. Ejerfortegnelsen (Datafordeler) matcher CVR-nr  -> direkte bevis
  2. Tvangsauktion i Statstidende på samme skyldner  -> direkte bevis
  3. Årsrapport: InvestmentProperty / LandAndBuildings > 0 -> stærkt bevis
  4. Branchekode 68.xx (fast ejendom) / 41.10 (byggeprojekter) -> indikation
  5. Navn indeholder "Ejendom", "Bolig", "Properties" ...      -> svag indikation
  6. Realkreditgæld i regnskab                                  -> svag indikation
"""
from __future__ import annotations

import re

from .models import BankruptcyCase, Signal

# DB07 branchekoder for fast ejendom (6 cifre uden punktum)
PROPERTY_INDUSTRY: dict[str, str] = {
    "681000": "Køb og salg af egen fast ejendom",
    "682010": "Udlejning af erhvervsejendomme",
    "682020": "Almennyttige boligselskaber",
    "682030": "Anden udlejning af boliger",
    "682040": "Udlejning af erhvervsejendomme (egne/leasede)",
    "683100": "Ejendomsmæglere mv.",
    "683210": "Administration af fast ejendom på kontraktbasis",
    "683220": "Ejerforeninger",
    "411000": "Gennemførelse af byggeprojekter",
    "552010": "Hoteller",
    "552020": "Konferencecentre og kursusejendomme",
    "553000": "Campingpladser",
    "931100": "Drift af sportsanlæg",
}

# koder hvor ejendom typisk ligger i eget selskab (ikke ejendomsselskab men egen ejendom)
SECONDARY_INDUSTRY_PREFIX = ("41", "55", "01", "10", "25", "46", "47", "49", "52", "86", "87", "93")

NAME_STRONG = re.compile(
    r"\b(ejendom(me|s|men)?|ejendomsselskab|ejendomsinvest|boliger|bolig|properties|property|"
    r"real\s?estate|estate|udlejning|ejendomsudvikling|development|projektudvikling|byg(geri)?|"
    r"grund(e|salg)?|ejerlejlighed|ejerlejligheder)\b",
    re.IGNORECASE,
)
NAME_WEAK = re.compile(r"\b(invest|holding|kapital|capital|partners|gruppen|group|park|gaard|gård)\b", re.IGNORECASE)

# Adresse-mønstre der ofte bruges som selskabsnavn for ejendomsselskaber: "Vestergade 12 ApS", "Matr. 4a ..."
NAME_ADDRESS = re.compile(r"\b[A-ZÆØÅ][a-zæøå]+(vej|gade|allé|alle|plads|torv|boulevard|vænget|stræde)\s+\d+", re.IGNORECASE)
NAME_MATRIKEL = re.compile(r"\bmatr\.?\s*(nr\.?)?\s*\d+", re.IGNORECASE)


def score_case(case: BankruptcyCase) -> BankruptcyCase:
    """Beregn signaler, score, konfidens og ejendomstype. Muterer og returnerer casen."""
    signals: list[Signal] = []
    c = case.selskab
    f = case.regnskab

    # --- 1. Ejerfortegnelsen -------------------------------------------------
    ejf_props = [p for p in case.ejendomme if p.kilde == "ejerfortegnelsen"]
    if ejf_props:
        signals.append(Signal(
            kode="ejf_match",
            beskrivelse=f"Registreret som ejer af {len(ejf_props)} ejendom(me) i Ejerfortegnelsen",
            point=60, kilde="Datafordeler/EJF",
        ))

    # --- 2. Tvangsauktion -----------------------------------------------------
    auk = [p for p in case.ejendomme if p.kilde == "tvangsauktion"]
    if auk:
        signals.append(Signal(
            kode="tvangsauktion",
            beskrivelse=f"{len(auk)} tvangsauktion(er) bekendtgjort i Statstidende på skyldneren",
            point=50, kilde="Statstidende",
        ))

    # --- 3. Regnskab ----------------------------------------------------------
    inv = f.investeringsejendomme or 0
    lab = f.grunde_og_bygninger or 0
    if inv > 0:
        signals.append(Signal(
            kode="xbrl_investeringsejendomme",
            beskrivelse=f"Investeringsejendomme bogført til {inv:,.0f} kr.".replace(",", "."),
            point=45, kilde="Årsrapport (XBRL)",
        ))
    if lab > 0:
        signals.append(Signal(
            kode="xbrl_grunde_bygninger",
            beskrivelse=f"Grunde og bygninger bogført til {lab:,.0f} kr.".replace(",", "."),
            point=40, kilde="Årsrapport (XBRL)",
        ))
    if (f.realkreditgaeld or 0) > 0:
        signals.append(Signal(
            kode="xbrl_realkredit",
            beskrivelse=f"Realkreditgæld {f.realkreditgaeld:,.0f} kr. (kræver pant i fast ejendom)".replace(",", "."),
            point=25, kilde="Årsrapport (XBRL)",
        ))
    if inv == 0 and lab == 0 and (f.materielle_anlaeg or 0) > 5_000_000 and f.aktiver and \
            f.materielle_anlaeg / f.aktiver > 0.5:
        signals.append(Signal(
            kode="xbrl_materielle_anlaeg",
            beskrivelse="Store materielle anlægsaktiver (>50 % af balancen) – kan være ejendom",
            point=15, kilde="Årsrapport (XBRL)",
        ))

    # --- 4. Branchekode -------------------------------------------------------
    code = (c.branchekode or "").replace(".", "")
    if code in PROPERTY_INDUSTRY:
        pts = 30 if code.startswith("68") or code == "411000" else 15
        signals.append(Signal(
            kode="branche_ejendom",
            beskrivelse=f"Hovedbranche {code[:2]}.{code[2:4]}.{code[4:]} {PROPERTY_INDUSTRY[code]}",
            point=pts, kilde="CVR",
        ))
    for bi in c.bibrancher:
        bic = bi.replace(".", "")[:6]
        if bic in PROPERTY_INDUSTRY and bic.startswith("68"):
            signals.append(Signal(kode="bibranche_ejendom", beskrivelse=f"Bibranche {bi}", point=10, kilde="CVR"))
            break

    # --- 5. Navn --------------------------------------------------------------
    navn_all = " ".join([c.navn or ""] + list(c.binavne))
    if NAME_STRONG.search(navn_all):
        signals.append(Signal(kode="navn_ejendom", beskrivelse="Selskabsnavn indikerer ejendom", point=15, kilde="CVR"))
    elif NAME_ADDRESS.search(navn_all) or NAME_MATRIKEL.search(navn_all):
        signals.append(Signal(kode="navn_adresse", beskrivelse="Selskabsnavn er en adresse/matrikel", point=15, kilde="CVR"))
    elif NAME_WEAK.search(navn_all):
        signals.append(Signal(kode="navn_invest", beskrivelse="Selskabsnavn indikerer investering/holding", point=5, kilde="CVR"))

    if c.selskabsform and c.selskabsform.upper() in ("K/S", "P/S"):
        signals.append(Signal(kode="form_ks", beskrivelse=f"Selskabsform {c.selskabsform} (typisk ejendomsprojekt)",
                              point=10, kilde="CVR"))
    if c.formaal and re.search(r"ejendom|udlej|fast ejendom|bolig", c.formaal, re.IGNORECASE):
        signals.append(Signal(kode="formaal_ejendom", beskrivelse="Vedtægtsformål nævner fast ejendom", point=10, kilde="CVR"))

    # --- score ----------------------------------------------------------------
    score = min(100, sum(s.point for s in signals))
    case.signaler = signals
    case.score = score

    direct = any(s.kode in ("ejf_match", "tvangsauktion") for s in signals)
    strong = any(s.kode in ("xbrl_investeringsejendomme", "xbrl_grunde_bygninger") for s in signals)
    if direct or (strong and score >= 70):
        case.konfidens = "høj"
    elif strong or score >= 45:
        case.konfidens = "middel"
    else:
        case.konfidens = "lav"

    case.ejendomstype_hoved = classify_property_type(case)
    return case


def classify_property_type(case: BankruptcyCase) -> str:
    types = {(p.ejendomstype or "").lower() for p in case.ejendomme}
    code = (case.selskab.branchekode or "").replace(".", "")
    navn = (case.selskab.navn or "").lower()
    f = case.regnskab
    if any("ejerlejlighed" in t for t in types) or code in ("682030", "682020") or "bolig" in navn:
        if code in ("682010", "682040"):
            return "Blandet"
        return "Bolig"
    if code in ("682010", "682040", "552010", "552020") or re.search(r"erhverv|kontor|lager|hotel", navn):
        return "Erhverv"
    if code in ("681000", "411000") or re.search(r"grund|projekt|byg\b|byg |development|entrepren", navn):
        return "Grund/Projekt"
    if case.ejendomme or NAME_ADDRESS.search(navn) or re.search(r"ejendom|estate|properties|udlejning", navn):
        return "Blandet"
    if (f.investeringsejendomme or 0) > 0:
        return "Blandet"  # investeringsejendomme uden nærmere angivelse
    if (f.grunde_og_bygninger or 0) > 0:
        return "Egen domicil"  # grunde og bygninger i driftsselskab: typisk egen ejendom
    return "Ukendt"
