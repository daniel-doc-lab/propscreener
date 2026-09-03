"""Deterministisk demodata.

Bruges til at udvikle dashboardet, køre tests og vise pipelinen uden
netværksadgang. ALT er fiktivt: selskabsnavne, CVR-numre (gyldige modulus-11
men tilfældige), kuratorer og adresser. Datasættet markeres `meta.demo = true`
og dashboardet viser et tydeligt banner.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from .detect import score_case
from .models import BankruptcyCase, Company, Financials, Kurator, Property, Skifteret
from .pipeline import RunStats, add_investor_links
from .sources.cvr import region_for_postnr
from .sources.regnskab import derive_ratios

CITIES = [
    ("1550", "København V", "København"), ("2100", "København Ø", "København"), ("2200", "København N", "København"),
    ("2300", "København S", "København"), ("2900", "Hellerup", "Gentofte"), ("2600", "Glostrup", "Glostrup"),
    ("3000", "Helsingør", "Helsingør"), ("3400", "Hillerød", "Hillerød"), ("4000", "Roskilde", "Roskilde"),
    ("4700", "Næstved", "Næstved"), ("4200", "Slagelse", "Slagelse"), ("4800", "Nykøbing F", "Guldborgsund"),
    ("5000", "Odense C", "Odense"), ("5700", "Svendborg", "Svendborg"), ("6000", "Kolding", "Kolding"),
    ("6700", "Esbjerg", "Esbjerg"), ("6200", "Aabenraa", "Aabenraa"), ("7100", "Vejle", "Vejle"),
    ("7400", "Herning", "Herning"), ("7500", "Holstebro", "Holstebro"), ("8000", "Aarhus C", "Aarhus"),
    ("8200", "Aarhus N", "Aarhus"), ("8600", "Silkeborg", "Silkeborg"), ("8700", "Horsens", "Horsens"),
    ("8900", "Randers C", "Randers"), ("9000", "Aalborg", "Aalborg"), ("9400", "Nørresundby", "Aalborg"),
    ("9800", "Hjørring", "Hjørring"), ("3700", "Rønne", "Bornholm"),
]
STREETS = ["Vestergade", "Nørregade", "Søndergade", "Østergade", "Havnegade", "Jernbanegade", "Kirkevej",
           "Strandvejen", "Industrivej", "Møllevej", "Bredgade", "Algade", "Torvegade", "Skolegade", "Parkvej"]
PREFIX = ["Nordhavn", "Amager", "Fjord", "Kyst", "Bakke", "Å", "Søndre", "Vestre", "Havne", "Bro", "Skov", "Eng",
          "Lund", "Holm", "Dal", "Mark", "Strand", "Kilde", "Kastel", "Port"]
SUFFIX_PROP = ["Ejendomme", "Ejendomsselskab", "Boliger", "Properties", "Ejendomsinvest", "Udlejning",
               "Erhvervsejendomme", "Projektudvikling", "Byg", "Invest", "Holding", "Development"]
SUFFIX_OTHER = ["Entreprise", "Consulting", "Trading", "Logistik", "Restaurant", "Fitness", "Auto", "IT", "Møbler",
                "Transport", "Rengøring", "Café"]
INDUSTRIES_PROP = [("682040", "Udlejning af erhvervsejendomme"), ("682030", "Anden udlejning af boliger"),
                   ("681000", "Køb og salg af egen fast ejendom"), ("411000", "Gennemførelse af byggeprojekter"),
                   ("682010", "Udlejning af erhvervsejendomme"), ("552010", "Hoteller")]
INDUSTRIES_OTHER = [("561010", "Restauranter"), ("433200", "Tømrer- og bygningssnedkervirksomhed"),
                    ("620100", "Computerprogrammering"), ("494100", "Vejgodstransport"), ("931300", "Fitnesscentre"),
                    ("451120", "Detailhandel med personbiler"), ("702200", "Virksomhedsrådgivning"),
                    ("812100", "Almindelig rengøring i bygninger")]
FORMS = ["ApS", "ApS", "ApS", "A/S", "K/S", "P/S", "IVS"]
COURTS = ["Sø- og Handelsrettens skifteret", "Skifteretten i Aarhus", "Skifteretten i Aalborg", "Skifteretten i Odense",
          "Retten i Roskilde", "Retten i Kolding", "Retten i Hillerød", "Retten i Herning", "Retten i Næstved",
          "Retten i Esbjerg", "Retten i Randers", "Retten i Viborg"]
LAW_FIRMS = ["Advokatfirmaet Nordlys", "Kammeradvokaten Demo", "Advokatpartnerselskabet Fjordbo", "Bystrøm Advokater",
             "Advokathuset Kystvejen", "Møller & Winther Advokater", "Lex Danica Advokatfirma", "Advokaterne Åhavnen"]
FIRST = ["Peter", "Mette", "Lars", "Anne", "Søren", "Camilla", "Henrik", "Louise", "Morten", "Charlotte", "Jens",
         "Kirsten", "Thomas", "Maria", "Niels", "Pernille", "Anders", "Signe", "Rasmus", "Julie"]
LAST = ["Nielsen", "Jensen", "Hansen", "Pedersen", "Andersen", "Christensen", "Larsen", "Sørensen", "Rasmussen",
        "Jørgensen", "Petersen", "Madsen", "Kristensen", "Olsen", "Thomsen", "Poulsen", "Johansen", "Møller"]


def cvr_number(rng: random.Random) -> str:
    """Gyldigt modulus-11 CVR-nummer (tilfældigt, ikke et rigtigt selskab)."""
    weights = [2, 7, 6, 5, 4, 3, 2]
    while True:
        digits = [rng.randint(1, 9)] + [rng.randint(0, 9) for _ in range(6)]
        s = sum(d * w for d, w in zip(digits, weights))
        rem = s % 11
        if rem == 1:
            continue
        check = 0 if rem == 0 else 11 - rem
        return "".join(map(str, digits + [check]))


def _dekret_tekst(c: BankruptcyCase) -> str:
    k, s = c.kurator, c.selskab
    return (
        f"Konkursdekret\nVed dekret afsagt den {_dk(c.dekretdato)} af {c.skifteret.navn} er\n{s.navn}\n"
        f"CVR-nr. {s.cvr}\n{s.adresse}\n{s.postnr} {s.by}\n"
        f"taget under konkursbehandling efter begæring modtaget den {_dk(c.fristdag)}.\n"
        f"Fristdag: {_dk(c.fristdag)}\n"
        f"Kurator: Advokat {k.navn}, {k.firma}, {k.adresse}, {k.postnr} {k.by}, tlf. {k.telefon}, e-mail: {k.email}\n"
        f"Sagsnummer: {c.skifteret.sagsnummer}\n"
        f"Krav mod boet skal anmeldes til kurator senest 4 uger efter denne bekendtgørelse.\n"
        f"Skiftesamling afholdes den {_dk(c.skiftesamling)} kl. 10.00 i skifteretten.\n"
        f"[DEMODATA – fiktivt selskab genereret af propscreener]"
    )


def _dk(iso: str | None) -> str:
    if not iso:
        return ""
    y, m, d = iso.split("-")
    return f"{d}.{m}.{y}"


def generate(n: int = 60, seed: int = 2026, days_back: int = 90) -> tuple[list[BankruptcyCase], RunStats]:
    rng = random.Random(seed)
    today = date.today()
    cases: list[BankruptcyCase] = []
    for i in range(n):
        is_prop = rng.random() < 0.62
        postnr, by, kommune = rng.choice(CITIES)
        form = rng.choice(FORMS)
        if is_prop:
            navn = f"{rng.choice(PREFIX)} {rng.choice(SUFFIX_PROP)} {form}"
            code, text = rng.choice(INDUSTRIES_PROP)
        else:
            navn = f"{rng.choice(PREFIX)}{rng.choice(['', 'gaard', 'lund', 'by'])} {rng.choice(SUFFIX_OTHER)} {form}"
            code, text = rng.choice(INDUSTRIES_OTHER)
        if rng.random() < 0.12:
            navn = f"{rng.choice(STREETS)} {rng.randint(1, 120)} {form}"
            code, text = rng.choice(INDUSTRIES_PROP[:3])
            is_prop = True
        cvr = cvr_number(rng)
        offentliggjort = today - timedelta(days=int(days_back * rng.random() ** 1.7))
        dekret = offentliggjort - timedelta(days=rng.randint(0, 3))
        fristdag = dekret - timedelta(days=rng.randint(3, 40))
        kur_post, kur_by, _ = rng.choice(CITIES)
        kur = Kurator(
            navn=f"{rng.choice(FIRST)} {rng.choice(LAST)}", firma=rng.choice(LAW_FIRMS),
            adresse=f"{rng.choice(STREETS)} {rng.randint(1, 60)}", postnr=kur_post, by=kur_by,
            telefon=f"{rng.randint(30, 99)} {rng.randint(10, 99)} {rng.randint(10, 99)} {rng.randint(10, 99)}",
        )
        kur.email = f"{kur.navn.split()[0][:2].lower()}{kur.navn.split()[1][:2].lower()}@{kur.firma.split()[-1].lower()}-demo.dk"
        kur.advokatsamfundet_url = "https://www.advokatsamfundet.dk/find-advokat/?q=" + kur.navn.replace(" ", "+")
        court = rng.choice(COURTS)
        case = BankruptcyCase(
            id=cvr, statstidende_id=f"demo-{seed}-{i:04d}",
            statstidende_url=f"https://www.statstidende.dk/messages/demo-{i:04d}",
            offentliggjort=offentliggjort.isoformat(), dekretdato=dekret.isoformat(), fristdag=fristdag.isoformat(),
            anmeldelsesfrist=(offentliggjort + timedelta(weeks=4)).isoformat(),
            skiftesamling=(dekret + timedelta(days=rng.randint(21, 45))).isoformat(),
            skifteret=Skifteret(navn=court, sagsnummer=f"SKS {rng.randint(10, 49)}-{rng.randint(100, 9999)}/{dekret.year}"),
            kurator=kur,
            selskab=Company(
                cvr=cvr, navn=navn, selskabsform=form, branchekode=code, branchetekst=text,
                adresse=f"{rng.choice(STREETS)} {rng.randint(1, 200)}", postnr=postnr, by=by, kommune=kommune,
                region=region_for_postnr(postnr), stiftet=(today - timedelta(days=rng.randint(400, 9000))).isoformat(),
                status="UNDER KONKURS", ansatte=rng.choice([0, 0, 1, 2, 3, 5, 8, 14, 25]),
                ejere=[f"{rng.choice(FIRST)} {rng.choice(LAST)}" for _ in range(rng.randint(1, 2))],
                ledelse=[f"{rng.choice(FIRST)} {rng.choice(LAST)}"],
                formaal="Selskabets formål er at eje og udleje fast ejendom samt hermed beslægtet virksomhed." if is_prop else
                        "Selskabets formål er at drive handel og service.",
            ),
            kilder=["demo"],
        )
        # regnskab
        if rng.random() < 0.85:
            if is_prop:
                prop_val = rng.randint(4, 180) * 1_000_000
                mort = int(prop_val * rng.uniform(0.55, 1.05))
                other = int(prop_val * rng.uniform(0.05, 0.35))
                assets = prop_val + rng.randint(1, 10) * 100_000
                fin = Financials(
                    regnskabsaar_slut=f"{dekret.year - 1}-12-31", aktiver=assets, egenkapital=assets - mort - other,
                    investeringsejendomme=prop_val if code != "411000" else None,
                    grunde_og_bygninger=prop_val if code == "411000" else (prop_val if rng.random() < 0.2 else None),
                    realkreditgaeld=mort, langfristet_gaeld=mort + other // 2, kortfristet_gaeld=other // 2,
                    omsaetning=int(prop_val * rng.uniform(0.03, 0.09)),
                    bruttofortjeneste=int(prop_val * rng.uniform(0.02, 0.06)),
                    aarets_resultat=int(prop_val * rng.uniform(-0.12, 0.03)), ansatte=case.selskab.ansatte,
                    kilde_url=f"https://regnskaber.virk.dk/demo/{cvr}.pdf",
                )
            else:
                assets = rng.randint(2, 60) * 100_000
                debt = int(assets * rng.uniform(0.6, 1.6))
                fin = Financials(
                    regnskabsaar_slut=f"{dekret.year - 1}-12-31", aktiver=assets, egenkapital=assets - debt,
                    materielle_anlaeg=int(assets * rng.uniform(0.05, 0.4)), kortfristet_gaeld=debt,
                    bruttofortjeneste=rng.randint(2, 40) * 100_000, aarets_resultat=-rng.randint(1, 30) * 100_000,
                    ansatte=case.selskab.ansatte, kilde_url=f"https://regnskaber.virk.dk/demo/{cvr}.pdf",
                )
            case.regnskab = derive_ratios(fin)
            case.kilder.append("regnskab-xbrl")
            case.links["aarsrapport"] = fin.kilde_url or ""
        # ejendomme
        if is_prop and rng.random() < 0.7:
            n_props = rng.choice([1, 1, 1, 2, 2, 3, 4, 6])
            book = case.regnskab.ejendomsvaerdi_bogfoert or rng.randint(4, 120) * 1_000_000
            for _ in range(n_props):
                p_post, p_by, p_kom = rng.choice(CITIES) if rng.random() < 0.3 else (postnr, by, kommune)
                ptype = rng.choice(["Samlet fast ejendom", "Samlet fast ejendom", "Ejerlejlighed", "Bygning på fremmed grund"])
                case.ejendomme.append(Property(
                    bfe_nummer=str(rng.randint(1_000_000, 9_999_999)),
                    adresse=f"{rng.choice(STREETS)} {rng.randint(1, 150)}", postnr=p_post, by=p_by, kommune=p_kom,
                    ejendomstype=ptype, ejerandel="1/1", kilde="ejerfortegnelsen",
                    offentlig_vurdering=int(book / n_props * rng.uniform(0.7, 1.15) / 100_000) * 100_000,
                    grundareal_m2=rng.randint(200, 6000), bygningsareal_m2=rng.randint(120, 4000),
                    lat=round(rng.uniform(54.6, 57.7), 4), lon=round(rng.uniform(8.1, 12.6), 4),
                ))
            case.kilder.append("ejerfortegnelsen")
        if is_prop and rng.random() < 0.18:
            case.ejendomme.append(Property(
                adresse=f"{rng.choice(STREETS)} {rng.randint(1, 150)}", postnr=postnr, by=by, kommune=kommune,
                ejendomstype="Samlet fast ejendom", kilde="tvangsauktion",
                offentlig_vurdering=rng.randint(15, 400) * 100_000,
                tvangsauktion_dato=(today + timedelta(days=rng.randint(7, 60))).isoformat(),
                tvangsauktion_url=f"https://www.statstidende.dk/messages/demo-auk-{i:04d}",
                lat=round(rng.uniform(54.6, 57.7), 4), lon=round(rng.uniform(8.1, 12.6), 4),
            ))
            case.kilder.append("tvangsauktion")
        case.raa_tekst = _dekret_tekst(case)
        case.links["statstidende"] = case.statstidende_url or ""
        score_case(case)
        add_investor_links(case)
        case.sidst_opdateret = today.isoformat()
        cases.append(case)

    stats = RunStats(dekreter=n, tvangsauktioner=sum(1 for c in cases for p in c.ejendomme if p.kilde == "tvangsauktion"),
                     beriget_cvr=n, beriget_regnskab=sum(1 for c in cases if c.regnskab.aktiver),
                     beriget_ejf=sum(1 for c in cases if any(p.kilde == "ejerfortegnelsen" for p in c.ejendomme)),
                     kilder_aktive=["demo"], min_score=0)
    return cases, stats
