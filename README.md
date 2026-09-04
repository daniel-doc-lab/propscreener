# propscreener

**Screener for danske konkursboer der ejer fast ejendom.**
Scraper konkursdekreter fra Statstidende, beriger hvert bo med CVR-data, seneste
XBRL-årsrapport og Ejerfortegnelsen, scorer sandsynligheden for ejendomsejerskab
og præsenterer resultatet i et dashboard for investorer: nøgletal, kuratorkontakt,
frister og links til kilderne.

```
Statstidende ──► CVR ──► Årsrapport (XBRL) ──► Ejerfortegnelsen ──► Scoring ──► JSON / CSV / Dashboard
 (dekreter)     (branche,   (ejendomme, gæld,      (BFE-numre,         (0–100,
  kurator)       ejere)      egenkapital)           vurdering)          konfidens)
```

| | |
|---|---|
| **Dashboard** | `propscreener demo` bygger `site/index.html` (offline demodata) – i produktion publiceres det dagligt til GitHub Pages af `scrape.yml` |
| **Data** | `data/cases.json` (kanonisk), `data/cases.csv` (regneark, `;`-separeret) |
| **Dokumentation** | [docs/](docs/) – arkitektur, datakilder, scoring, investorguide, opsætning, datamodel, jura |
| **Status** | Kører dagligt i GitHub Actions mod Statstidendes åbne JSON-API (verificeret 4. sep. 2026). 24 offline tests. Ejerfortegnelsen aktiveres med en gratis Datafordeler-bruger – se [docs/SETUP.md](docs/SETUP.md) |

## Hurtig start

```bash
git clone https://github.com/daniel-doc-lab/propscreener && cd propscreener
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

propscreener demo            # fiktivt datasæt + dashboard i site/index.html
propscreener probe           # tjek hvilke kilder der kan nås fra din maskine
propscreener run --days 90   # rigtig kørsel (kræver netværk, se docs/SETUP.md)
propscreener show 12345678   # dump ét bo som JSON
pytest -q
```

Åbn `site/index.html` direkte i en browser – data er indlejret, ingen server nødvendig.

## Hvad dashboardet viser

* **Register** over boer sorteret efter score, med dekretdato, region, ejendomstype,
  bogført ejendomsværdi, belåningsgrad og kurator + anmeldelsesfrist.
* **Detaljepanel** pr. bo: kuratorens kontaktoplysninger (mail/telefon/Advokatsamfundet),
  tidslinje (fristdag → dekret → bekendtgørelse → anmeldelsesfrist → skiftesamling),
  12 nøgletal fra seneste årsrapport, balancevisualisering, liste over kendte ejendomme
  med BFE-nummer og offentlig vurdering, signalerne bag scoren, og links til Statstidende,
  CVR, årsrapport, tinglysning, OIS og kort.
* **Filtre**: fritekst, region, ejendomstype, konfidens, mindste score, kun med kendte
  ejendomme, kun åbne frister, med tvangsauktion. Udvalget kan kopieres som CSV.

## Datakilder (kort)

| Kilde | Bruges til | Adgang |
|---|---|---|
| [Statstidende](https://www.statstidende.dk) | Konkursdekreter, kurator, skifteret, tvangsauktioner | Offentlig søgning, eller REST-API med OCES3-certifikat |
| [cvrapi.dk](https://cvrapi.dk) / [CVR system-til-system](https://datacvr.virk.dk/artikel/system-til-system-adgang-til-cvr-data) | Branche, adresse, ejere, status | Gratis (User-Agent) / aftale |
| [Regnskabsdata](https://datacvr.virk.dk/artikel/system-til-system-adgang-til-regnskabsdata) | XBRL-årsrapporter: investeringsejendomme, grunde og bygninger, realkreditgæld, egenkapital | Åben, ingen login |
| [Ejerfortegnelsen (Datafordeler)](https://datafordeler.dk/dataoversigt/ejerfortegnelsen-ejf/ejerfortegnelsen/) | Ejendomme (BFE) ejet af CVR-nummer | Gratis tjenestebruger |
| [DAWA](https://dawadocs.dataforsyningen.dk) | Adresser, koordinater | Åben |

Detaljer, endpoints og forbehold: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Projektstruktur

```
propscreener/
  cli.py            kommandoer: run · demo · build-site · probe · show
  pipeline.py       orkestrering + RunStats
  models.py         BankruptcyCase, Company, Financials, Property, Kurator, Signal
  detect.py         ejendomsscoring (signaler → score/konfidens/ejendomstype)
  xbrl.py           XBRL/iXBRL-parser (stdlib)
  http.py           HTTP med cache, rate-limit, retry; FakeHttp til tests
  export.py         JSON, CSV, dashboard-build
  demo.py           deterministisk fiktivt datasæt
  sources/          statstidende · cvr · regnskab · ejerfortegnelse
  templates/        dashboard.html (indlejrer data ved build)
tests/              24 tests, fixtures for dekret (tekst + rigtigt API-format), XBRL og iXBRL
docs/               dokumentation
.github/workflows/  ci.yml (tests) · scrape.yml (daglig kørsel → repo + Pages) · discover.yml (API-opdagelse)
```

## Vigtige forbehold

* Værktøjet er en **screening**, ikke rådgivning. Nøgletal stammer fra seneste
  *indberettede* årsrapport, som kan være 6–18 måneder gammel og ikke afspejle boets aktiver.
* Ejendomsejerskab er kun **bekræftet** når Ejerfortegnelsen eller en tvangsauktion matcher;
  ellers er det en sandsynlighed baseret på branche, navn og regnskab.
* Statstidendes interne søge-endpoint er ikke officielt dokumenteret og kan ændre sig; workflowet
  `discover.yml` genfinder det. Det officielle API kræver OCES3-certifikat – se [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).
* cvrapi.dk har en lille daglig kvote; uden CVR-adgang mangler branchekode på en del boer.
* Persondata: kuratorer optræder i deres professionelle rolle som offentliggjort i
  Statstidende. Se [docs/LEGAL.md](docs/LEGAL.md).

Licens: MIT.
