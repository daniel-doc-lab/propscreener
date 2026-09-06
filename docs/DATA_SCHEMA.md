# Datamodel (`data/cases.json`)

```json
{
  "meta": {
    "genereret": "2026-09-03T06:20:11+00:00",
    "version": "0.1.0",
    "antal": 42,
    "demo": false,
    "kilder_aktive": ["statstidende:web", "cvrapi", "regnskab-xbrl", "dawa", "ejerfortegnelsen"],
    "stats": { "dekreter": 311, "tvangsauktioner": 9, "beriget_cvr": 298, "beriget_regnskab": 240,
               "beriget_ejf": 37, "over_min_score": 42, "min_score": 40, "fejl": [] }
  },
  "cases": [ { …BankruptcyCase… } ]
}
```

## BankruptcyCase

| Felt | Type | Beskrivelse |
|---|---|---|
| `id` | str | CVR-nr, ellers `st-<statstidende_id>` |
| `statstidende_id`, `statstidende_url` | str | Meddelelsen |
| `meddelelsestype` | str | `Konkursdekret` |
| `offentliggjort` | date | Bekendtgørelsesdato i Statstidende |
| `dekretdato`, `fristdag` | date | Fra dekretteksten |
| `anmeldelsesfrist` | date | `offentliggjort` + 28 dage |
| `skiftesamling`, `fordringsproevelse` | date | Hvis nævnt |
| `skifteret` | `{navn, sagsnummer}` | |
| `kurator` | Kurator | se nedenfor |
| `selskab` | Company | se nedenfor |
| `regnskab` | Financials | se nedenfor |
| `ejendomme` | Property[] | |
| `signaler` | Signal[] | `{kode, beskrivelse, point, kilde}` |
| `score` | int 0–100 | |
| `konfidens` | `høj` / `middel` / `lav` | |
| `ejendomstype_hoved` | `Bolig` / `Erhverv` / `Blandet` / `Grund/Projekt` / `Ukendt` | |
| `raa_tekst` | str | Meddelelsestekst |
| `links` | dict | `statstidende`, `cvr`, `regnskaber`, `aarsrapport`, `tvangsauktion`, `tinglysning`, `ois`, `kort`, `kurator_opslag` |
| `kilder` | str[] | Hvilke kilder der bidrog |
| `noter` | str[] | Advarsler pr. bo |
| `relationer` | Relation[] | Mulige koncernforbundne boer, se nedenfor |
| `sidst_opdateret` | datetime | |

## Kurator

`navn`, `firma`, `adresse`, `postnr`, `by`, `telefon`, `email`, `advokatsamfundet_url`.

## Company

`cvr`, `navn`, `binavne[]`, `selskabsform`, `branchekode` (6 cifre), `branchetekst`, `bibrancher[]`,
`adresse`, `postnr`, `by`, `kommune`, `region`, `stiftet`, `status`, `ansatte`, `ejere[]`, `ledelse[]`,
`cvr_url`, `formaal`, `lat`, `lon` (hjemstedsadresse geokodet via DAWA – bruges af kortet).

## Financials (DKK, seneste årsrapport)

| Felt | XBRL-begreb |
|---|---|
| `regnskabsaar_slut`, `kilde_url` | kontekst / dokument |
| `aktiver` | `fsa:Assets` |
| `egenkapital` | `fsa:Equity` |
| `investeringsejendomme` | `fsa:InvestmentProperty` |
| `grunde_og_bygninger` | `fsa:LandAndBuildings` |
| `materielle_anlaeg` | `fsa:PropertyPlantAndEquipment` |
| `realkreditgaeld` | `fsa:MortgageDebt` / `fsa:LongtermMortgageDebt` |
| `langfristet_gaeld` | `fsa:LongtermLiabilitiesOtherThanProvisions` |
| `kortfristet_gaeld` | `fsa:ShorttermLiabilitiesOtherThanProvisions` |
| `omsaetning` | `fsa:Revenue` |
| `bruttofortjeneste` | `fsa:GrossProfitLoss` |
| `aarets_resultat` | `fsa:ProfitLoss` |
| `ansatte` | `fsa:AverageNumberOfEmployees` |
| `ejendomsvaerdi_bogfoert` | max(investeringsejendomme, grunde_og_bygninger) |
| `ejendomsandel_pct` | ejendomsværdi / aktiver |
| `soliditet_pct` | egenkapital / aktiver |
| `ltv_pct` | realkreditgæld / ejendomsværdi |
| `samlet_gaeld` | lang + kort gæld, ellers aktiver − egenkapital |

## Property

`bfe_nummer`, `adresse`, `postnr`, `by`, `kommune`, `ejendomstype`, `ejerandel`, `matrikel`,
`kilde` (`ejerfortegnelsen` / `tvangsauktion` / `regnskab` / `demo`), `offentlig_vurdering`,
`grundareal_m2`, `bygningsareal_m2`, `tvangsauktion_dato`, `tvangsauktion_url`, `lat`, `lon`.

## Relation (`relationer[]`)

Afledt af alle dekreter i perioden (også boer under `min_score`) i `propscreener/relations.py`:

| Felt | Beskrivelse |
|---|---|
| `id`, `cvr`, `navn` | Det relaterede bo |
| `score`, `konfidens`, `dekretdato`, `branchetekst`, `by`, `ejendomsvaerdi`, `antal_ejendomme` | Nøgletal på det relaterede bo |
| `statstidende_url` | Dekretet |
| `i_registret` | `true` hvis boet selv er med i `cases` (score ≥ min_score) |
| `grund` | str[] – fx `samme hjemstedsadresse`, `samme ejer/ledelse (…)`, `fælles navnestamme »kyst« og samme kurator`, `samme kurator og dekret samme dage` |

## Auction (`data/auktioner.json`)

Selvstændigt register over alle tvangsauktioner over fast ejendom bekendtgjort i Statstidende i
perioden (rubrik *Tvangsauktioner → Fast ejendom*). Filen har formen `{genereret, antal, auktioner[]}`
og indlejres i dashboardet under `auktioner`.

| Felt | Beskrivelse |
|---|---|
| `id`, `statstidende_url`, `offentliggjort` | Meddelelsen |
| `auktionsdato`, `tidspunkt`, `auktionsnummer` | Afholdelse; `auktionsnummer` er 1 eller 2 |
| `fogedret` | fx `Retten i Odense` |
| `adresse`, `postnr`, `by`, `region`, `matrikel`, `ejendomstype` | Ejendommen (`Beboelse`, `Ejerlejlighed`, `Erhvervsejendom`, `Landbrug`, `Grund`, `Samlet fast ejendom`) |
| `beskrivelse` | Første 600 tegn af auktionsbekendtgørerens beskrivelse |
| `offentlig_vurdering`, `grundvaerdi`, `vurderingsdato` | Fra feltet *Ejendomsværdi* (`Pr. 01.01.2022 kr. 461.000 heraf grundværdi kr. 108.000`) |
| `skoedehaver`, `skyldner_cvr` | Ejer ifølge tingbogsattest og evt. CVR-nr |
| `rekvirent`, `rekvirent_telefon`, `besigtigelse` | Begæreren af auktionen og kontakt for besigtigelse |
| `konkursbo_id` | `id` på boet i `cases` hvis skyldneren er et konkursbo i registret |
| `lat`, `lon` | Geokodet via DAWA |

## CSV

`data/cases.csv` er `;`-separeret med UTF-8 BOM (åbner korrekt i dansk Excel). Kolonner i
`export.CSV_COLUMNS` – én række pr. bo, ejendomme aggregeret (antal + summer).
