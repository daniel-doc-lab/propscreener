# Roadmap

## Status 4. september 2026

* Statstidendes åbne JSON-API er verificeret og i drift (971 dekreter på 90 dage).
* Regnskabsdata (XBRL) virker for ca. 76 % af selskaberne.
* cvrapi.dk giver kun få opslag pr. dag fra GitHub-runnere (delt IP-kvote). Branchekode mangler
  derfor på de fleste boer indtil der sættes CVR system-til-system-adgang op.
* Ejerfortegnelsen afventer Datafordeler-login (secrets).
* Tvangsauktioner matches på "Skødehaver ifølge tingbogsattest"; 2 match i første kørsel.

## Næste skridt

1. **Verificér Statstidende-endpoint** i web-mode og lås payload-nøglerne (docs/DATA_SOURCES.md).
   Tilføj en optaget JSON-respons som fixture i `tests/fixtures/`.
2. **Kør første rigtige pipeline** i GitHub Actions (`demo=false`) og gennemgå 20 boer manuelt
   mod tingbogen for at kalibrere pointene i `detect.py`.
3. **Optag EJF- og VUR-svar** som fixtures og stram `_iter_ejerskaber`/`valuation`.

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
