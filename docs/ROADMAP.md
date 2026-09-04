# Roadmap

## Status 4. september 2026

* Statstidendes åbne JSON-API er verificeret og i drift (971 dekreter på 90 dage).
* Regnskabsdata (XBRL) virker for ca. 76 % af selskaberne.
* CVR: apicvr.dk (gratis, open source, REST + MCP) er primær kilde og dækker 99,8 % af boerne;
  cvrapi.dk er sekundær (lille daglig kvote pr. IP på GitHub-runnere).
* Ejerfortegnelsen afventer Datafordeler API-nøgle (secret `DATAFORDELER_API_KEY`).
* Tvangsauktioner matches på "Skødehaver ifølge tingbogsattest"; 2 match i første kørsel.
* Dashboard publiceres på GitHub Pages fra `main` efter hver daglig kørsel.

## Næste skridt

1. **Datafordeler API-nøgle** som secret `DATAFORDELER_API_KEY` → kør `discover.yml` (verificerer
   parameternavn) → bekræftet ejerskab med BFE-numre og offentlig vurdering. Optag EJF- og VUR-svar
   som fixtures og stram `_iter_ejerskaber`/`valuation`.
2. **Kalibrering**: gennemgå 20 boer manuelt mod tingbogen og justér pointene i `detect.py`.
3. **Reelle ejere / ledelse**: apicvr.dk leverer ikke deltagere; kræver CVR system-til-system
   (`CVR_ES_USER/PASSWORD`, gratis aftale hos Erhvervsstyrelsen) – giver også koncernstruktur.
4. **Ændringsfeed**: e-mail/Slack med nye boer siden i går.

## Funktioner

* Følg **koncernstruktur**: opslag på datterselskaber (deltagerRelation) så ejendomme i
  datterselskaber tælles med for moderselskabets konkurs.
* **Skiftesamlinger og fordringsprøvelser** som opdateringer på eksisterende boer
  (`MESSAGE_TYPES` er forberedt).
* **Tvangsauktioner uden konkurs** som separat visning (panthaverdrevne salg).
* **Kort** over ejendomme (koordinater findes allerede via DAWA) – kræver kortfliser eller
  et inlinet Danmarks-omrids.
* **Ændringsfeed**: diff mod forrige kørsel → "nye boer siden i går" (RSS/e-mail/Slack).
* **Lejeindtægt/afkast-estimat** fra bruttofortjeneste og ejendomsværdi.
* **Historik**: gem hver kørsel i `data/history/` og vis boets forløb.
* **Engelsk UI**.

## Teknisk gæld

* `normalize_message` gætter feltnavne – erstat med en fast mapping når endpointet er verificeret.
* `parse_kurator` håndterer ikke flere kuratorer ("kuratorer: advokat A og advokat B").
* Region afledes af postnummerintervaller; brug DAWA's kommune → region for præcision.
