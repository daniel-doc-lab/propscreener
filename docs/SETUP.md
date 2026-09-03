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

## GitHub Actions (daglig kørsel → GitHub Pages)

1. Repository → Settings → Pages → Source: **GitHub Actions**.
2. Settings → Secrets and variables → Actions: læg de hemmeligheder ind du har (se ovenfor).
   Certifikater lægges som PEM-tekst i `STATSTIDENDE_CERT_PEM` / `STATSTIDENDE_KEY_PEM`.
3. Workflowet `scrape.yml` kører 04:15 UTC dagligt og kan startes manuelt (Actions → *Scrape og
   publicér* → Run workflow). Inputs: `days`, `min_score`, `demo=true` for at publicere demodata.
4. Output: `https://<owner>.github.io/propscreener/` (dashboard), `…/data/cases.json`, `…/cases.csv`.
   Data-artefaktet gemmes desuden på hver kørsel under Actions → Artifacts.

HTTP-cachen gemmes mellem kørsler (`actions/cache`), så regnskaber og CVR-opslag ikke hentes igen.

## Fejlfinding

| Symptom | Årsag / løsning |
|---|---|
| `Kunne ikke finde et fungerende søge-endpoint på statstidende.dk` | Endpointet er ændret. Følg proceduren i DATA_SOURCES.md → *Offentlig søgning* |
| `HTTP 403` fra cvrapi.dk | Manglende/anonym User-Agent. Sæt `CVRAPI_USER_AGENT` med kontaktinfo |
| `Ejerfortegnelsen kunne ikke slås op` i `noter` | Forkert login, eller tjenestebrugeren mangler adgang til EJF-tjenesten (tildel i selvbetjening) |
| Mange boer med `Ingen XBRL-årsrapport fundet` | Normalt for nye selskaber og holdingselskaber |
| Kørsel tager lang tid | 0,5 s pr. kald × ~5 kald pr. bo. 300 boer ≈ 15 min. Cache gør genkørsler hurtige |

## Kør tests

```bash
pytest -q          # 23 tests, ingen netværk
ruff check .       # lint
```
