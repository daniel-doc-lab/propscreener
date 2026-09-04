# Ejendomsdetektion og scoring

Målet er at vise **kun** konkursboer der ejer fast ejendom – uden at tabe boer hvor vi ikke
har direkte adgang til Ejerfortegnelsen. Derfor summerer vi uafhængige beviser til en score
og viser beviserne i dashboardet.

## Signaler

| Kode | Bevis | Point | Kilde | Styrke |
|---|---|---|---|---|
| `ejf_match` | CVR-nr er registreret ejer af ≥1 ejendom | 60 | Ejerfortegnelsen | direkte |
| `tvangsauktion` | Tvangsauktion bekendtgjort på skyldneren | 50 | Statstidende | direkte |
| `xbrl_investeringsejendomme` | `fsa:InvestmentProperty` > 0 | 45 | Årsrapport | stærk |
| `xbrl_grunde_bygninger` | `fsa:LandAndBuildings` > 0 | 40 | Årsrapport | stærk |
| `branche_ejendom` | Hovedbranche 68.xx eller 41.10 (30) · hotel/camping mv. (15) | 30 / 15 | CVR | indikation |
| `xbrl_realkredit` | Realkreditgæld > 0 (kræver pant i fast ejendom) | 25 | Årsrapport | indikation |
| `xbrl_materielle_anlaeg` | Materielle anlæg > 5 mio. og > 50 % af balancen, uden ejendomspost | 15 | Årsrapport | svag |
| `navn_ejendom` | Navn indeholder ejendom/bolig/properties/udlejning/byg/grund … | 15 | CVR | svag |
| `navn_adresse` | Navnet er en adresse eller matrikel ("Vestergade 12 ApS") | 15 | CVR | svag |
| `bibranche_ejendom` | Bibranche 68.xx | 10 | CVR | svag |
| `form_ks` | Selskabsform K/S eller P/S (typisk ejendomsprojekter) | 10 | CVR | svag |
| `formaal_ejendom` | Vedtægtsformål nævner fast ejendom | 10 | CVR | svag |
| `navn_invest` | Navn indeholder invest/holding/kapital … | 5 | CVR | meget svag |

Score = min(100, sum af point).

## Konfidens

* **høj** – direkte bevis (`ejf_match` eller `tvangsauktion`), eller stærkt bevis fra regnskab
  *og* score ≥ 70.
* **middel** – stærkt regnskabsbevis, eller score ≥ 45 uden direkte bevis.
* **lav** – alt andet.

Standardfilter i dashboardet og `run` er score ≥ 40, hvilket kræver mindst ét stærkt bevis
eller branche 68 + navn. Sæt `--min-score 0`/`--all` for at se alle boer.

## Ejendomstype

Afledes i `classify_property_type`:

| Type | Regel |
|---|---|
| Bolig | ejerlejligheder i ejendomslisten, branche 68.20.20/68.20.30, eller "bolig" i navnet |
| Erhverv | branche 68.20.10/68.20.40, hoteller, konferencecentre |
| Grund/Projekt | branche 68.10.00 eller 41.10.00, "grund"/"projekt" i navnet |
| Blandet | både bolig- og erhvervsindikationer, eller ejendomme uden nærmere type |
| Ukendt | ingen indikation |

## Kendte fejlkilder

* **Falske positive**: ejendomsmæglere (68.31), administratorer (68.32) og ejerforeninger
  (68.32.20) får branchepoint uden at eje ejendom. De når sjældent ≥ 40 uden regnskabsbevis.
  Konferencecentre/hoteller kan leje deres bygning.
* **Falske negative**: ejendomme ejet via datterselskab (koncernstruktur) – moderselskabets
  konkurs viser ingen EJF-match. Koncernregnskaber hjælper delvist (`InvestmentProperty` i
  koncernen); en kommende udvidelse er at følge `deltagerRelation` til datterselskaber.
* **Regnskabsalder**: årsrapporten kan være op til 18 måneder gammel. Ejendommen kan være
  solgt eller tvangsrealiseret inden dekretet.
* **Bygning på fremmed grund** og **andelsboliger** håndteres som ejendomme, men er
  sværere at prissætte.

## Kalibrering

Signalpointene er sat efter hvor ofte beviset i praksis betyder ejerskab (direkte registre
> regnskabsposter > klassifikationer > navne). Justér i `detect.py` – tests i
`tests/test_detect.py` låser grænserne: et ejendomsselskab uden regnskab lander på 45 (middel),
et selskab med investeringsejendomme og realkredit på ≥ 70 (høj), et pizzeria på 0.
