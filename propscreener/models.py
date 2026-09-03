"""Datamodel for et konkursbo set fra en ejendomsinvestors synsvinkel.

Alle beløb er i DKK (heltal). Datoer er ISO-8601 strenge (YYYY-MM-DD) så
modellen kan serialiseres direkte til JSON uden konverteringslag.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Kurator:
    """Kontaktoplysninger på kurator (bobestyrer) som angivet i dekretet."""

    navn: str | None = None
    firma: str | None = None
    adresse: str | None = None
    postnr: str | None = None
    by: str | None = None
    telefon: str | None = None
    email: str | None = None
    advokatsamfundet_url: str | None = None  # opslag i "Find advokat"


@dataclass
class Skifteret:
    navn: str | None = None            # fx "Sø- og Handelsrettens skifteret"
    sagsnummer: str | None = None      # fx "SKS 41-1234/2026"


@dataclass
class Financials:
    """Nøgletal fra seneste offentliggjorte årsrapport (XBRL, Erhvervsstyrelsen)."""

    regnskabsaar_slut: str | None = None
    kilde_url: str | None = None                   # PDF/XBRL-dokument
    aktiver: int | None = None                     # fsa:Assets
    egenkapital: int | None = None                 # fsa:Equity
    investeringsejendomme: int | None = None       # fsa:InvestmentProperty
    grunde_og_bygninger: int | None = None         # fsa:LandAndBuildings
    materielle_anlaeg: int | None = None           # fsa:PropertyPlantAndEquipment
    realkreditgaeld: int | None = None             # fsa:MortgageDebt / LongtermMortgageDebt
    langfristet_gaeld: int | None = None           # fsa:LongtermLiabilitiesOtherThanProvisions
    kortfristet_gaeld: int | None = None           # fsa:ShorttermLiabilitiesOtherThanProvisions
    omsaetning: int | None = None                  # fsa:Revenue
    bruttofortjeneste: int | None = None           # fsa:GrossProfitLoss
    aarets_resultat: int | None = None             # fsa:ProfitLoss
    ansatte: int | None = None                     # fsa:AverageNumberOfEmployees

    # --- afledte nøgletal (beregnes i pipeline.derive_ratios) ---
    ejendomsvaerdi_bogfoert: int | None = None     # max(investeringsejendomme, grunde_og_bygninger)
    ejendomsandel_pct: float | None = None         # ejendomsvaerdi / aktiver
    soliditet_pct: float | None = None             # egenkapital / aktiver
    ltv_pct: float | None = None                   # realkreditgaeld / ejendomsvaerdi
    samlet_gaeld: int | None = None


@dataclass
class Property:
    """Én fast ejendom knyttet til selskabet (Ejerfortegnelsen / tvangsauktion / regnskab)."""

    bfe_nummer: str | None = None
    adresse: str | None = None
    postnr: str | None = None
    by: str | None = None
    kommune: str | None = None
    ejendomstype: str | None = None      # "Samlet fast ejendom", "Ejerlejlighed", "Bygning på fremmed grund"
    ejerandel: str | None = None         # fx "1/1"
    matrikel: str | None = None
    kilde: str | None = None             # "ejerfortegnelsen" | "tvangsauktion" | "regnskab" | "demo"
    offentlig_vurdering: int | None = None
    grundareal_m2: int | None = None
    bygningsareal_m2: int | None = None
    tvangsauktion_dato: str | None = None
    tvangsauktion_url: str | None = None
    lat: float | None = None
    lon: float | None = None


@dataclass
class Signal:
    """Ét bevis for/imod at selskabet ejer fast ejendom. Summeres til en score."""

    kode: str          # fx "branche_68", "ejf_match", "xbrl_investeringsejendomme"
    beskrivelse: str
    point: int
    kilde: str


@dataclass
class Company:
    cvr: str | None = None
    navn: str | None = None
    binavne: list[str] = field(default_factory=list)
    selskabsform: str | None = None      # "ApS", "A/S", "K/S", "P/S", "I/S"
    branchekode: str | None = None       # 6-cifret DB07
    branchetekst: str | None = None
    bibrancher: list[str] = field(default_factory=list)
    adresse: str | None = None
    postnr: str | None = None
    by: str | None = None
    kommune: str | None = None
    region: str | None = None
    stiftet: str | None = None
    status: str | None = None            # "UNDER KONKURS"
    ansatte: int | None = None
    ejere: list[str] = field(default_factory=list)     # reelle ejere / legale ejere (navne)
    ledelse: list[str] = field(default_factory=list)
    cvr_url: str | None = None
    formaal: str | None = None


@dataclass
class BankruptcyCase:
    """Ét konkursbo = én Statstidende-meddelelse af typen konkursdekret + berigelse."""

    id: str                                       # stabil nøgle: cvr eller statstidende-id
    statstidende_id: str | None = None
    statstidende_url: str | None = None
    meddelelsestype: str = "Konkursdekret"
    offentliggjort: str | None = None            # dato meddelelsen blev offentliggjort
    dekretdato: str | None = None
    fristdag: str | None = None
    anmeldelsesfrist: str | None = None          # dekretdato/offentliggjort + 4 uger
    skiftesamling: str | None = None
    fordringsproevelse: str | None = None
    skifteret: Skifteret = field(default_factory=Skifteret)
    kurator: Kurator = field(default_factory=Kurator)
    selskab: Company = field(default_factory=Company)
    regnskab: Financials = field(default_factory=Financials)
    ejendomme: list[Property] = field(default_factory=list)
    signaler: list[Signal] = field(default_factory=list)
    score: int = 0                               # 0–100
    konfidens: str = "lav"                       # "lav" | "middel" | "høj"
    ejendomstype_hoved: str | None = None        # "Bolig", "Erhverv", "Blandet", "Grund", "Ukendt"
    raa_tekst: str | None = None                 # meddelelsestekst (til søgning/debug)
    links: dict[str, str] = field(default_factory=dict)
    kilder: list[str] = field(default_factory=list)
    noter: list[str] = field(default_factory=list)
    sidst_opdateret: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BankruptcyCase":
        return cls(
            id=d["id"],
            statstidende_id=d.get("statstidende_id"),
            statstidende_url=d.get("statstidende_url"),
            meddelelsestype=d.get("meddelelsestype", "Konkursdekret"),
            offentliggjort=d.get("offentliggjort"),
            dekretdato=d.get("dekretdato"),
            fristdag=d.get("fristdag"),
            anmeldelsesfrist=d.get("anmeldelsesfrist"),
            skiftesamling=d.get("skiftesamling"),
            fordringsproevelse=d.get("fordringsproevelse"),
            skifteret=Skifteret(**d.get("skifteret", {})),
            kurator=Kurator(**d.get("kurator", {})),
            selskab=Company(**d.get("selskab", {})),
            regnskab=Financials(**d.get("regnskab", {})),
            ejendomme=[Property(**p) for p in d.get("ejendomme", [])],
            signaler=[Signal(**s) for s in d.get("signaler", [])],
            score=d.get("score", 0),
            konfidens=d.get("konfidens", "lav"),
            ejendomstype_hoved=d.get("ejendomstype_hoved"),
            raa_tekst=d.get("raa_tekst"),
            links=d.get("links", {}),
            kilder=d.get("kilder", []),
            noter=d.get("noter", []),
            sidst_opdateret=d.get("sidst_opdateret"),
        )
