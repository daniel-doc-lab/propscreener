# Arkitektur

## Overblik

```
                ┌──────────────────────────┐
                │  StatstidendeClient      │  konkurs_dekret, tvangsauktion_fast_ejendom
                │  (api | web)             │
                └────────────┬─────────────┘
                             │ RawMessage
                             ▼
                   parse_dekret_text()  ──►  BankruptcyCase (skyldner, kurator, skifteret, frister)
                             │
        ┌────────────────────┼─────────────────────┬──────────────────────┐
        ▼                    ▼                     ▼                      ▼
  enrich_with_cvr     enrich_with_regnskab   enrich_with_ejerfortegnelse   attach_auctions
  (cvrapi / CVR-ES)   (regnskabsindeks +     (Datafordeler EJF + VUR,      (Statstidende
                       XBRL-parser)           DAWA geokodning)              tvangsauktioner)
        └────────────────────┴─────────────────────┴──────────────────────┘
                             │
                             ▼
                        score_case()   ──►  signaler, score 0–100, konfidens, ejendomstype
                             │
                             ▼
              export: cases.json · cases.csv · site/index.html (data indlejret)
```

## Designprincipper

1. **Én kilde pr. modul, ét `Http`-objekt injiceret.** Alle kilder tager `(Settings, Http)`
   og kan derfor testes offline med `FakeHttp`. `tests/test_pipeline.py` kører hele kæden
   uden netværk.
2. **Tolerant parsing.** Statstidendes JSON-form er ikke kontraktfast; `normalize_message`
   accepterer flere nøglenavne, HTML eller ren tekst, og strukturerede felter når de findes.
   Selve dekretteksten er den stabile del (standardformuleringer fra skifteretterne) og
   parses med regex der er dækket af tests.
3. **Forklarlig scoring.** `detect.py` gemmer hvert bevis som et `Signal` med point og kilde,
   så dashboardet kan vise *hvorfor* et bo er med. Se PROPERTY_DETECTION.md.
4. **Degradér pænt.** Mangler credentials til Datafordeler eller CVR-ES, springes kilden over
   og `kilder_aktive` i metadata fortæller hvad der var slået til. Fejl pr. bo ender i
   `noter`, ikke i et crash.
5. **Cache og høflighed.** Disk-cache med TTL pr. kaldetype (regnskaber 30 dage, CVR 24 timer,
   søgninger 1 time), 0,5 s mellem kald, retry med eksponentiel backoff, beskrivende User-Agent.
6. **Statisk output.** Dashboardet er én HTML-fil med data indlejret ved build – kan åbnes lokalt,
   hostes på GitHub Pages eller publiceres som artifact. Ingen backend.

## Datamodel

Se DATA_SCHEMA.md. Kort: `BankruptcyCase` ⊃ `Company`, `Financials`, `Kurator`, `Skifteret`,
`[Property]`, `[Signal]`. Alle beløb i hele DKK, datoer ISO-8601.

## Kørselsflow (`Pipeline.run`)

1. `collect_cases(date_from)` – hent dekreter, dedupliker på CVR, drop personlige konkurser
   (ingen CVR og intet selskabsnavn).
2. `attach_auctions` – hent tvangsauktioner 180 dage bagud og match på CVR eller navn.
3. Pr. bo: CVR → regnskab → EJF/DAWA → `score_case` → `add_investor_links`.
4. Filtrér `score >= min_score`, sortér efter score, dekretdato.
5. `RunStats` rapporterer antal, berigelsesgrad og fejl; gemmes i `meta.stats`.

## Udvidelsespunkter

* Ny kilde: implementér en klasse i `sources/` med `(settings, http)` og en `enrich_with_*`-funktion,
  kald den fra `Pipeline.enrich`, tilføj et `Signal` i `detect.py`.
* Ny meddelelsestype (fx fordringsprøvelse, boafslutning): tilføj i `MESSAGE_TYPES` og en
  parser à la `parse_tvangsauktion`.
* Ny eksport: `export.py` har `build_dataset` som fælles indgang.
* Alternativ konkurskilde: `CvrElastic.recently_bankrupt` giver alle selskaber med status
  UNDER KONKURS inden for N dage (kræver system-til-system adgang) – kan bruges hvis
  Statstidende er utilgængelig.
