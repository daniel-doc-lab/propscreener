# Roadmap

## Status 4. september 2026

* Statstidendes åbne JSON-API er verificeret og i drift (971 dekreter på 90 dage).
* CVR: apicvr.dk (gratis, open source, REST + MCP) er primær kilde og dækker 99,8 % af boerne.
* Regnskabsdata (XBRL) virker for ca. 76 % af selskaberne.
* Ejerfortegnelsen: API-nøgle er sat; parameternavn og svarformat verificeres af `discover.yml`.
* Tvangsauktioner matches på "Skødehaver ifølge tingbogsattest".
* Dashboard publiceres på GitHub Pages fra `main` efter hver daglig kørsel; data flettes inkrementelt
  (180 dages retention).

## Faser

### Fase 1 – Datakvalitet (uge 1–2)

| # | Leverance | Effekt | Afhængighed |
|---|---|---|---|
| 1.1 | Ejerfortegnelsen aktiv: BFE-numre, ejerandel, adresse pr. bo | "Sandsynligt" → "bekræftet" ejerskab; ejendomsliste på alle relevante boer | Datafordeler API-nøgle (sat) |
| 1.2 | Offentlig vurdering (VUR) og BBR-arealer pr. BFE | Værdi og m² pr. ejendom; LTV på vurdering, ikke kun bogført værdi | 1.1 |
| 1.3 | Kalibrering af scoring mod 20 manuelt verificerede boer | Færre falske positive i "Egen domicil"; dokumenteret præcision | 1.1 |
| 1.4 | Skiftesamlinger, fordringsprøvelser og boafslutning som opdateringer | Boets forløb vises; afsluttede boer arkiveres automatisk | – |
| 1.5 | Ophævelse af dekret markerer boet som lukket | Ingen døde poster i registret | – |

### Fase 2 – Investorværktøj (uge 3–5)

| # | Leverance | Effekt | Afhængighed |
|---|---|---|---|
| 2.1 | Ændringsfeed: dagligt e-mail/Slack-resumé med nye boer og ændringer | Investoren behøver ikke åbne dashboardet hver dag | – |
| 2.2 | Watchlist og noter pr. bo (gemmes i browser, senere delt) | Arbejdsflow: "set", "kontaktet", "bud afgivet" | – |
| 2.3 | Kort over ejendomme med klynge-visning | Geografisk screening; se porteføljer i ét blik | 1.1 |
| 2.4 | Reelle ejere, ledelse og koncernstruktur via CVR system-til-system | Ejendomme i datterselskaber; gengangere blandt ejere | Aftale hos Erhvervsstyrelsen |
| 2.5 | Tvangsauktioner uden konkurs som separat register | Panthaverdrevne salg, ofte bedre prissat | – |

### Fase 3 – Analyse og skalering (uge 6+)

| # | Leverance | Effekt |
|---|---|---|
| 3.1 | Lejeindtægt/afkast-estimat fra bruttofortjeneste og areal | Sortering på estimeret afkast |
| 3.2 | Historik og statistik: boer pr. måned, region, type; medianværdier | Markedsindsigt, ikke kun enkeltsager |
| 3.3 | Eksport til Excel med pivot-klar struktur og PDF-faktaark pr. bo | Deling internt og med banker/partnere |
| 3.4 | API/JSON-feed med nøgle (statisk `data/cases.json` er allerede tilgængelig) | Integration i egne systemer |
| 3.5 | Officielt Statstidende-API med OCES3-certifikat | Robust mod ændringer i sitets interne API |

## 15 konkrete forbedringsforslag

### Features

1. **Ændringsfeed pr. e-mail/Slack.** En daglig besked med "nye boer siden i går" (navn, region,
   ejendomstype, bogført værdi, kurator, frist) og ændringer på eksisterende (ny skiftesamling,
   ophævet dekret). Implementeres som et ekstra trin i `scrape.yml`, der diffe'r mod forrige
   `cases.json` og sender via SMTP/Slack-webhook.
2. **Watchlist med status.** Marker et bo som "Interessant", "Kontaktet", "Bud afgivet", "Afvist"
   med dato og note. Gemmes lokalt i browseren i første version; senere som delt liste i repoet.
3. **Kort med ejendomme.** Når Ejerfortegnelsen leverer BFE-numre og DAWA koordinater, vises alle
   ejendomme på et Danmarkskort med klynger, filtre og klik til boet. Kræver kortfliser (fx
   Dataforsyningens gratis WMTS) eller et inlinet Danmarks-omrids.
4. **Afkast-estimat.** Bruttofortjeneste fra årsrapporten divideret med bogført/offentlig
   ejendomsværdi giver et groft direkte afkast. Vis som interval med forbehold, og gør det sortérbart.
5. **Kurator-profil.** Saml alle boer pr. kurator/advokatfirma: antal aktive boer, typisk
   sagsbehandlingstid, kontaktoplysninger. Investorer arbejder ofte tættere med få kuratorer.
6. **Koncern-visning.** Når moderselskabet går konkurs, slå datterselskaber op og vis deres
   ejendomme samlet (kræver CVR system-til-system for deltagerrelationer).
7. **Tvangsauktioner som selvstændigt register.** Samme dashboard-mønster for alle auktioner over fast
   ejendom (ikke kun dem der matcher et konkursbo): adresse, vurdering, auktionsdato, rekvirent.
8. **Faktaark pr. bo (PDF/print).** Én side med nøgletal, ejendomme, kurator, frister og kildelinks,
   klar til at sende til en partner eller bank. Print-CSS findes allerede; tilføj "Gem som PDF"-flow.

### Design, UX og UI

9. **Sammenlign boer side om side.** Vælg 2–4 boer og se nøgletal i kolonner (værdi, LTV, soliditet,
   ejendomstype, frist). Gør prioritering mellem lignende sager hurtigere.
10. **Mikro-grafer i registret.** En lille "balance-stribe" (ejendom vs. gæld vs. egenkapital) direkte
    i hver række, så friværdi kan aflæses uden at åbne panelet.
11. **Frist-kalender.** En ugevisning af anmeldelsesfrister, skiftesamlinger og auktionsdatoer på
    tværs af boer; klik åbner boet. Eksport som iCal.
12. **Gemte filtre og delbare links.** Filtertilstand skrives i URL'en (`?region=Midtjylland&type=Bolig&min=60`),
    så en kollega kan åbne præcis samme udsnit. Gem favoritter som chips over registret.
13. **Forklaret score med "hvad mangler".** Ud over signalerne vises hvad der ville løfte konfidensen
    ("Ejerfortegnelsen ikke slået op", "ingen årsrapport"), så brugeren ved om lav score skyldes
    manglende data eller manglende ejendom.
14. **Tættere register-tilstand og kolonnevalg.** Skift mellem "kort" (nuværende) og "tabel" med valgbare
    kolonner og fast header; tastaturnavigation (piltaster, Enter åbner, Esc lukker) for hurtig gennemgang.
15. **Datakvalitets-indikator pr. bo.** Et lille "dæknings-mærke" (fx 4/5: Statstidende, CVR,
    regnskab, Ejerfortegnelsen, vurdering) i rækken og panelet, plus regnskabets alder i måneder,
    så brugeren ser hvor friske og komplette tallene er.

## Teknisk gæld

* `normalize_message` gætter feltnavne for det officielle API (mode=api) – erstat med fast mapping når
  certifikatadgang er etableret.
* `parse_kurator` håndterer ikke flere kuratorer ("kuratorer: advokat A og advokat B").
* Region afledes af postnummerintervaller; brug DAWA's kommune → region for præcision.
* Auktionsmatch på navn er følsomt for stavevarianter; supplér med adresse-match mod selskabets adresse.
