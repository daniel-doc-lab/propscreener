# Opsætning og drift

## Lokalt

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env         # udfyld det du har adgang til
propscreener probe           # hvilke kilder svarer?
propscreener run --days 90   # data/cases.json, data/cases.csv, site/index.html
```

Uden nogen hemmeligheder virker: Statstidende (web), cvrapi.dk, regnskabsindekset, DAWA.
Det giver score på branche, navn, regnskab og tvangsauktioner – men ingen BFE-numre.

## Adgange (alle valgfrie)

| Miljøvariabel | Hvor får man den | Effekt |
|---|---|---|
| `DATAFORDELER_USER` / `_PASSWORD` | datafordeler.dk → Selvbetjening → opret tjenestebruger (gratis) | Ejerfortegnelsen + vurdering → konfidens *høj* |
| `CVR_ES_USER` / `_PASSWORD` | datacvr.virk.dk → "System-til-system adgang til CVR-data" (aftale) | Bibrancher, ejere/ledelse, statushistorik; alternativ konkurskilde |
| `STATSTIDENDE_CERT_FILE` / `_KEY_FILE` | Aftale med Civilstyrelsen + OCES3-certifikat | Officielt API i stedet for web-søgning |
| `CVRAPI_USER_AGENT` | Din egen tekst med kontaktinfo | Krævet af cvrapi.dk's vilkår |

Øvrige knapper: `PROPSCREENER_DAYS_BACK`, `PROPSCREENER_MIN_SCORE`, `PROPSCREENER_CACHE_DIR`.

## GitHub Actions (daglig kørsel → repo + GitHub Pages)

Workflowet `scrape.yml` kører 04:15 UTC dagligt, på manuel start (Actions → *Scrape og publicér*
→ Run workflow; inputs `days`, `min_score`, `demo=true`) og på push til udviklingsbranchen
(kort vindue på 7 dage). Hver kørsel:

1. henter dekreter, beriger og scorer,
2. **committer** `data/cases.json`, `data/cases.csv` og `site/index.html` til branchen,
3. gemmer dem som Actions-artefakt (`cases`),
4. publicerer `site/` til GitHub Pages, hvis repo-variablen `ENABLE_PAGES` er `true`.

Opsætning af Pages (gratis på offentlige repos):

1. Settings → Pages → Source: **GitHub Actions**.
2. Settings → Secrets and variables → Actions → **Variables** → `ENABLE_PAGES` = `true`.
3. Pages-miljøet (`github-pages`) tillader som standard kun udrulning fra standardbranchen
   (`main`). Enten merges udviklingsbranchen til `main`, eller også tilføjes branchen under
   Settings → Environments → github-pages → *Deployment branches*.
4. Dashboardet ligger derefter på `https://<owner>.github.io/propscreener/`, data på
   `…/data/cases.json` og `…/data/cases.csv`.

Hemmeligheder lægges under **Secrets** (se tabellen ovenfor). Certifikater som PEM-tekst i
`STATSTIDENDE_CERT_PEM` / `STATSTIDENDE_KEY_PEM`.

HTTP-cachen gemmes mellem kørsler (`actions/cache`), så regnskaber og CVR-opslag ikke hentes igen.

## Fejlfinding

| Symptom | Årsag / løsning |
|---|---|
| `probe` melder fejl på `/api/messagesearch` | Statstidende har ændret sit interne API. Kør workflowet `discover.yml` (Actions) – det dumper sitets bundles og finder de nye stier |
| `cvrapi.dk kvote opbrugt` i `meta.stats.fejl` | Daglig kvote pr. IP. Pipelinen falder tilbage til statstidende.dk's CVR-opslag; sæt evt. `CVR_ES_USER/PASSWORD` for fuld dækning |
| `HTTP 403` fra cvrapi.dk | Manglende/anonym User-Agent. Sæt `CVRAPI_USER_AGENT` med kontaktinfo |
| `Ejerfortegnelsen kunne ikke slås op` i `noter` | Forkert login, eller tjenestebrugeren mangler adgang til EJF-tjenesten (tildel i selvbetjening) |
| Mange boer med `Ingen XBRL-årsrapport fundet` | Normalt for nye selskaber og holdingselskaber |
| Kørsel tager lang tid | 0,5 s pr. kald × ~5 kald pr. bo. 300 boer ≈ 15 min. Cache gør genkørsler hurtige |

## Kør tests

```bash
pytest -q          # 23 tests, ingen netværk
ruff check .       # lint
```
