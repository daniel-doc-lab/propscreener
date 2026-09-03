# Datakilder

Alle kilder er danske, offentlige registre. Tabellen viser hvad vi henter, hvordan, og
hvad der kræves. Kolonnen *verificeret* angiver om endpoint-formatet er bekræftet i
dette projekt eller er skrevet efter offentlig dokumentation uden live-test.

| # | Kilde | Data | Adgang | Verificeret |
|---|---|---|---|---|
| 1 | Statstidende – konkursdekreter | skyldner, CVR, dekretdato, fristdag, skifteret, sagsnr, kurator | offentlig søgning / REST-API m. certifikat | parser: ja (fixtures) · endpoint: **nej** |
| 2 | Statstidende – tvangsauktioner | ejendom, matrikel, ejendomsværdi, auktionsdato, ejer | som 1 | parser: ja · endpoint: nej |
| 3 | cvrapi.dk | navn, branche, adresse, status, ejere, ansatte | gratis, User-Agent | feltnavne: dokumenteret |
| 4 | CVR system-til-system (Elasticsearch) | fuld virksomhedsprofil, bibrancher, deltagere, statushistorik | aftale m. Erhvervsstyrelsen | feltnavne: dokumenteret |
| 5 | Regnskabsindeks `distribution.virk.dk/offentliggoerelser` | dokument-URL'er til XBRL/PDF | åben | feltnavne: dokumenteret |
| 6 | XBRL-årsrapport | Assets, Equity, InvestmentProperty, LandAndBuildings, MortgageDebt, ProfitLoss … | åben | parser: ja (XBRL + iXBRL fixtures) |
| 7 | Datafordeler – Ejerfortegnelsen | BFE-numre ejet af CVR-nr, ejerandel, ejendomstype | gratis tjenestebruger | metode-navn dokumenteret · svarform: tolerant |
| 8 | Datafordeler – Vurdering (VUR) | offentlig ejendomsvurdering pr. BFE | som 7 | tolerant |
| 9 | DAWA / Dataforsyningen | adresse for BFE, koordinater | åben | dokumenteret |

## 1–2. Statstidende

Statstidende er den *retligt bindende* bekendtgørelse af konkursdekreter (konkurslovens § 109).
Meddelelsestyper vi bruger: **Konkursboer → Dekret** og **Tvangsauktioner → Fast ejendom**.
Andre typer (skiftesamling, fordringsprøvelse, boafslutning) er registreret i `MESSAGE_TYPES`
til senere brug.

### Officielt API (`STATSTIDENDE_MODE=api`)

* Base: `https://api.statstidende.dk`, dokumentation på `/docs/index.html`.
* Kræver aftale med Civilstyrelsen og et **OCES3-virksomhedscertifikat** (mutual TLS).
  Sæt `STATSTIDENDE_CERT_FILE` / `STATSTIDENDE_KEY_FILE` (PEM).
* Klienten kalder `GET /v1/messages` med `messageCategory`, `messageType`, `publishedFrom`,
  `publishedTo`, `page`, `pageSize`. **Parameternavnene skal afstemmes med den udleverede
  dokumentation** – de er konfigureret ét sted (`_search_api`).

### Offentlig søgning (`STATSTIDENDE_MODE=web`, standard)

statstidende.dk er en single-page-app der henter JSON fra et internt endpoint. Det er ikke
dokumenteret og kan ændre sig. Derfor:

1. `propscreener probe` afprøver kandidaterne i `WEB_SEARCH_CANDIDATES`
   (`POST /api/messages/search`, `GET /api/messages`, `GET /api/v1/messages`, …) og
   rapporterer hvilke der svarer med en meddelelsesliste.
2. Kan intet endpoint findes: åbn statstidende.dk → søg på *Konkursboer / Dekret* →
   DevTools → Network → filtrér XHR. Notér URL, metode og request-body. Tilføj den som første
   kandidat i `WEB_SEARCH_CANDIDATES` og tilpas payload-nøglerne i `_search_web`.
3. `normalize_message` er bevidst tolerant over for feltnavne (`id`/`messageId`,
   `text`/`body`/`content`, `publicationDate`/`publishedDate` …), så mindre ændringer ikke
   kræver kodeændring.

**Vilkår**: Statstidendes data er offentlige, men brug rimelig frekvens (én daglig kørsel,
0,5 s mellem kald). Hvis I skal bruge det kommercielt i stor skala, indgå aftale om API-adgang.

### Dekretteksten

Skifteretterne bruger standardformuleringer. `parse_dekret_text` udtrækker:

```
Ved dekret afsagt den 25.08.2026 af Skifteretten i Aarhus er        → dekretdato, skifteret
Fjord Ejendomme ApS                                                   → navn, selskabsform
CVR-nr. 12 34 56 78                                                   → cvr
Vestergade 12, 2. th. / 8000 Aarhus C                                 → adresse, postnr, by
Fristdag: 10.08.2026                                                  → fristdag
Kurator: Advokat Peter Hansen, Advokatfirmaet Nordlys, Åboulevarden 1,
        8000 Aarhus C, tlf. 86 12 34 56, e-mail: ph@…                 → kurator (navn, firma, adresse, tlf, mail)
Sagsnummer: SKS 41-1234/2026                                          → sagsnummer
Skiftesamling afholdes den 22. september 2026                         → skiftesamling
```

Anmeldelsesfristen beregnes som bekendtgørelsesdato + 4 uger (konkurslovens § 128).

## 3–4. CVR

* **cvrapi.dk**: `GET https://cvrapi.dk/api?vat=<cvr>&country=dk&format=json`.
  Kræver en beskrivende `User-Agent` med kontaktoplysning (`CVRAPI_USER_AGENT`). Rate-limit er
  uofficielt; vi holder 0,5 s mellem kald og cacher 24 timer.
* **System-til-system**: `POST http://distribution.virk.dk/cvr-permanent/virksomhed/_search`
  med Basic auth. Giver `virksomhedMetadata.nyesteHovedbranche`, `nyesteBibranche1-3`,
  `deltagerRelation` (ejere/ledelse), `virksomhedsstatus` med gyldighedsperioder. Samme klient
  kan hente *alle* selskaber der er gået konkurs inden for N dage (`recently_bankrupt`).

## 5–6. Regnskaber (XBRL)

* Indeks: `POST http://distribution.virk.dk/offentliggoerelser/_search` med
  `{"query":{"bool":{"must":[{"term":{"cvrNummer":12345678}}]}},"sort":[{"offentliggoerelsesTidspunkt":{"order":"desc"}}]}`.
  Hvert hit har `dokumenter[]` med `dokumentUrl` og `dokumentMimeType`
  (`application/xml` = XBRL, `application/xhtml+xml` = Inline XBRL fra 2025, `application/pdf`).
* Parseren (`xbrl.py`) læser begreberne i `CONCEPTS` fra Erhvervsstyrelsens `fsa`-taksonomi,
  vælger seneste kontekst uden dimensioner, og håndterer iXBRL-`scale`/`sign`/`format`
  (dansk `numcommadecimal`).
* Bemærk: holdingselskaber uden aktivitet og nystiftede selskaber har ofte ingen rapport.
  Regnskabsklasse B-selskaber viser sjældent `Revenue` (kun bruttofortjeneste).

## 7–8. Ejerfortegnelsen og vurdering (Datafordeler)

* Opret gratis tjenestebruger på datafordeler.dk (Selvbetjening → Brugere → Tjenestebruger,
  adgang med brugernavn/adgangskode). Sæt `DATAFORDELER_USER`/`DATAFORDELER_PASSWORD`.
* REST: `GET https://services.datafordeler.dk/EJERFORTEGNELSE/Ejerfortegnelsen/1/REST/EjendommeMedSammeEjer?CVRnr=…&format=json&username=…&password=…`
  Metoden returnerer ejerskaber med `bestemtFastEjendomBFENr`, ejerandel og ejendomstype.
  Datafordeleren har varslet at REST-varianten udfases ultimo 2026; basis-URL og sti er derfor
  konfigurerbare (`EJF_PATH`).
* Vurdering: `VUR/VUR/1/REST/BFEejendomsvurdering?BFEnummer=…` – seneste offentlige
  ejendomsværdi. Bemærk at de nye 2020-vurderinger for erhverv stadig udrulles; feltet kan mangle.
* Ejerfortegnelsen indeholder **ikke** CPR-numre i den åbne variant, og vi bruger kun CVR-opslag.

## 9. DAWA

`GET https://api.dataforsyningen.dk/adresser?bfe=<bfe>&struktur=mini` → adresse og koordinater
for en BFE. `?q=<adresse>` til geokodning. Åben, ingen nøgle.

## Kilder vi bevidst ikke bruger

* **auktioner.dk / tvangsauktioner.dk** – kommercielle sammenstillinger af Statstidendes
  auktionsmeddelelser. Vi går til kilden i stedet.
* **tinglysning.dk** – kræver MitID/NemLog-in for opslag; vi linker i stedet til tingbogen så
  investoren selv kan hente hæftelser og servitutter.
* **CPR-baserede opslag** – personlige konkurser filtreres fra (ingen CVR).
