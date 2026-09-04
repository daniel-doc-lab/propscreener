# Datakilder

Alle kilder er danske, offentlige registre. Tabellen viser hvad vi henter, hvordan, og
hvad der kræves. Kolonnen *verificeret* angiver om endpoint-formatet er bekræftet i
dette projekt eller er skrevet efter offentlig dokumentation uden live-test.

| # | Kilde | Data | Adgang | Verificeret |
|---|---|---|---|---|
| 1 | Statstidende – konkursdekreter | skyldner, CVR, dekretdato, fristdag, skifteret, sagsnr, kurator | offentlig søgning / REST-API m. certifikat | **ja** – endpoint og format verificeret 4. sep. 2026 |
| 2 | Statstidende – tvangsauktioner | ejendom, matrikel, ejendomsværdi, auktionsdato, ejer | som 1 | endpoint: ja · feltformat: under kalibrering |
| 3 | cvrapi.dk | navn, branche, adresse, status, ejere, ansatte | gratis, User-Agent, lille daglig kvote | feltnavne: dokumenteret |
| 3b | apicvr.dk (REST + MCP) | samme felter som cvrapi.dk + status/bankrupt | gratis, open source, ingen login | REST og MCP verificeret 4. sep. 2026 – **primær** |
| 4 | CVR system-til-system (Elasticsearch) | fuld virksomhedsprofil, bibrancher, deltagere, statushistorik | aftale m. Erhvervsstyrelsen | feltnavne: dokumenteret |
| 5 | Regnskabsindeks `distribution.virk.dk/offentliggoerelser` | dokument-URL'er til XBRL/PDF | åben | feltnavne: dokumenteret |
| 6 | XBRL-årsrapport | Assets, Equity, InvestmentProperty, LandAndBuildings, MortgageDebt, ProfitLoss … | åben | parser: ja (XBRL + iXBRL fixtures) |
| 7 | Datafordeler – Ejerfortegnelsen | BFE-numre ejet af CVR-nr, ejerandel, ejendomstype | OAuth + godkendt anmodning (fildownload/GraphQL) | endpoints dokumenteret; adgang afventer godkendelse |
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

### Offentlig søgning (`STATSTIDENDE_MODE=web`, standard) – verificeret

statstidende.dk er en React-SPA, der taler med et internt JSON-API på samme host. API'et
kræver ikke login for læsning. Endpoints og parametre er verificeret 4. september 2026 ved
at læse sitets JavaScript-bundles fra en GitHub Actions-runner (workflowet `discover.yml`):

| Endpoint | Formål |
|---|---|
| `GET /api/section` | Alle sektioner og rubrikker med `id`, `name`, `publicKey` |
| `GET /api/messagesearch?m=<pk>&s=8&fromDate=YYYY-MM-DD&toDate=YYYY-MM-DD&page=0&ps=100` | Søgning. `m` = rubrikkens publicKey **uden bindestreger** (kan gentages), `s=8` = kundgjorte, `page` er 0-baseret. Svar: `{pageCount, resultCount, results:[{messageNumber, published, title, summary:[{name,value}], sectionName, messageTypeName}]}` |
| `GET /api/messagesearch/messagetypecount?…` | Antal pr. rubrik for samme parametre |
| `GET /api/message/{messageNumber}` | Hele meddelelsen: `document` (JSON-streng med `fieldgroups[].fields[].{name,value,type}`), `title`, `publicationDate`, `summaryFields` |
| `GET /api/Publication/GetLatestPublication` | Dagens udgave: `date`, `fileId`, `sectionCounts`, `topMessageTypeCounts` |
| `GET /api/publicationfile/{fileId}/pdf` | Dagens samlede PDF-udgave (plan B til parsing) |
| `GET /api/cvr/{cvr}` | Sitets eget CVR-opslag (bruges som fallback når cvrapi.dk's kvote er brugt) |

Rubrikker vi bruger (fra `/api/section`):

| Rubrik | messageTypeId | publicKey |
|---|---|---|
| Konkursboer → Dekret | 13048120 | `14a1d71d-f215-58e5-ade0-214f90482cdc` |
| Konkursboer → Ophævelse af dekret | 3605286 | `383f1800-1b39-5f39-8250-61a5c0798fad` |
| Konkursboer → Regnskab og boafslutning | 3625429 | `018d0141-0efb-5472-a698-9328817df00a` |
| Tvangsauktioner → Fast ejendom | 790596 | `2aa7d6a1-b250-51a8-88a6-3f6c18574526` |
| Tvangsauktioner → Andelsbolig | 13048125 | `84aba03b-79ab-48ca-b318-8f8d90f0b095` |

Meddelelsesnumre har formen `S02092026-87` (S + dato + løbenummer), og den offentlige side er
`https://www.statstidende.dk/messages/{messageNumber}`.

**Vilkår og høflighed**: robots.txt på statstidende.dk tillader kun forsiden og enkelte
info-sider for crawlere. Vi crawler ikke sider – vi kalder det JSON-API sitet selv bruger, én
gang i døgnet, med 0,5 s mellem kald og en User-Agent med kontaktlink. Til systematisk,
kommerciel høst bør man tegne den officielle API-aftale hos Civilstyrelsen (se ovenfor).

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
  Kræver en beskrivende `User-Agent` med kontaktoplysning (`CVRAPI_USER_AGENT`). Der er en
  **daglig kvote pr. IP** (i praksis under 20 opslag fra en GitHub-runner, observeret 4. sep.
  2026). Pipelinen prioriterer derfor CVR-opslag efter foreløbig score (regnskab + navn) og
  falder tilbage til statstidende.dk's `api/cvr/{cvr}`. Resultater caches 24 timer.
* **apicvr.dk** (primær, aktiv som standard): gratis open source CVR-API uden login.
  REST: `GET https://apicvr.dk/api/v1/{cvr}` (OpenAPI på `/openapi.json`; også navnesøgning
  `/api/v1/search/company/{navn}` og adressesøgning). Svaret følger cvrapi.dk's feltnavne plus
  `bankrupt`, `status`, `companytypeshort`, `p_units`. MCP-serveren `https://mcp.apicvr.dk/mcp`
  (JSON-RPC, SSE-svar, værktøj `lookup_company`) bruges som fallback. Slås fra med tomme
  `APICVR_REST_BASE` / `APICVR_MCP_URL`. Vær høflig: én kørsel om dagen, 0,5 s mellem kald.
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

Datafordeleren har to generationer af adgang (undersøgt 4. september 2026 fra en Actions-runner):

| | Gammel platform (udfases 15. jan. 2027) | Ny platform (Datafordeler Administration) |
|---|---|---|
| Host | `services.datafordeler.dk` (REST) | `api.datafordeler.dk` (GraphQL + Fildownload) |
| Login | *Tjenestebruger* (brugernavn/adgangskode) fra Selvbetjeningen | *IT-system* med API-Key (frie data) eller OAuth Shared Secret/Certifikat |
| Ejerfortegnelsen | REST: `Ejerskab?BFEnr=` i den åbne tjeneste; **opslag pr. CVR (`EjendommeMedSammeEjer?CVRnr=`) findes kun i den fortrolige tjeneste** | Fildownload (`/FileDownloads/GetAvailableFileDownloads?Register=EJF`, `/FileDownloads/GetFile?…`) og GraphQL. **Kræver OAuth og godkendt "Anmodning om adgang til EJF"** – også for de åbne entiteter |
| Status i projektet | REST-klient findes (`EJF_PATH`), men uden tjenestebruger svarer hosten 404 | API-Key accepteres (401 → 404) men giver ikke adgang til EJF; OAuth + anmodning mangler |

**Anbefalet vej** (implementeres når adgangen er godkendt): ugentligt *totaldownload aktuel* af
entiteten `Ejerskab` (JSON/CSV, genereres natten til mandag) → filtrér til virksomhedsejere → byg et
kompakt indeks CVR → [BFE, ejerandel] → slå alle boer op lokalt. Deltadownload dagligt til
vedligehold. Det er hurtigere og mere robust end enkeltopslag, og det giver også *historiske* ejere
(selskaber der solgte kort før konkursen).

Sådan søger du adgang (Datafordeler Administration, gratis for åbne entiteter):

1. IT-system → **OAuth Shared Secret → Opret** (gem client id og secret som `DATAFORDELER_CLIENT_ID` /
   `DATAFORDELER_CLIENT_SECRET` i GitHub Secrets).
2. **Anmodning om adgang** → Ejerfortegnelsen (EJF) → Fildownload (og gerne GraphQL) → vælg de
   åbne entiteter `Ejerskab`, `Ejerskifte`, `Handelsoplysninger`, `PersonVirksomhedsoplysninger`.
   Fortrolige entiteter (CPR) er kun for offentlige myndigheder.
3. Registrér evt. IP-adresser kun hvis der anmodes om fortrolige data (ikke nødvendigt her).
4. Vurdering (VUR) og BBR: samme mønster (anmodning pr. register); BBR og Matriklen er frie data.

Bemærk: `EjendommeMedSammeEjer` i den gamle REST-tjeneste og GraphQL-varianten er klassificeret
fortrolig fordi metoden også tager CPR; for CVR-opslag er fildownload-indekset den åbne løsning.

### Fildownload – verificeret med API-Key (4. september 2026)

`propscreener probe-files --headers …` henter det mindste delta-udtræk og viser kolonnenavne.
Konstateret fra `.github/workflows/index.yml`:

| Register | Entitet | Udtræk | Størrelse | Nøglekolonner |
|---|---|---|---|---|
| EBR | `Ejendomsbeliggenhed` | TotalDownload/Current/csv | 202 MB, 2,70 mio. rækker | `bestemtFastEjendomBFENr`, `betegnelse`, `kommuneinddelingKommunekode`, `adresseLokalId`, `status` |
| VUR | `Ejendomsvurdering` | kun TotalDownload/**Bitemporal**/csv | 2,2 GB (~85 min. download) | `id`, `ejendomværdiBeløb`, `grundværdiBeløb`, `år`, `benyttelseKode`, `fkVurderingsejendomID` (ingen BFE) |
| VUR | `BFEKrydsreference` | kun Bitemporal | 1,9 GB (~75 min.) | `fkEjendomsvurderingID` → `BFEnummer` |
| VUR | `Vurderingsejendom` | kun Bitemporal | – | `vurderingsejendomID`, `VURejendomsid`, `ESRejendomsnummer` |
| EJF | `Ejerskab` m.fl. | – | – | listen er tom indtil anmodningen er godkendt (OAuth) |

Konsekvenser for pipelinen: EBR-indekset (BFE → adresse/kommune) bygges hver uge med API-Key.
VUR-indekset bygges først, når EJF-indekset findes, fordi vurderingerne kun kan kobles til et bo via
CVR → BFE, og fordi de to VUR-filer tager knap tre timer at hente (`--force-vur` tvinger det).
Delta-udtræk uden ændringer er ~350–500 bytes (kun kolonnelinje).

## 9. DAWA

`GET https://api.dataforsyningen.dk/adresser?bfe=<bfe>&struktur=mini` → adresse og koordinater
for en BFE. `?q=<adresse>` til geokodning. Åben, ingen nøgle.

## Kilder vi bevidst ikke bruger

* **auktioner.dk / tvangsauktioner.dk** – kommercielle sammenstillinger af Statstidendes
  auktionsmeddelelser. Vi går til kilden i stedet.
* **tinglysning.dk** – kræver MitID/NemLog-in for opslag; vi linker i stedet til tingbogen så
  investoren selv kan hente hæftelser og servitutter.
* **CPR-baserede opslag** – personlige konkurser filtreres fra (ingen CVR).
