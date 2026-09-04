# Roadmap

## Status 4. september 2026

* Statstidendes åbne JSON-API er verificeret og i drift (971 dekreter på 90 dage).
* Regnskabsdata (XBRL) virker for ca. 76 % af selskaberne.
* cvrapi.dk giver kun få opslag pr. dag fra GitHub-runnere (delt IP-kvote). Branchekode mangler
  derfor på de fleste boer indtil der sættes CVR system-til-system-adgang op.
* Ejerfortegnelsen afventer Datafordeler-login (secrets).
* Tvangsauktioner matches på "Skødehaver ifølge tingbogsattest"; 2 match i første kørsel.

## Næste skridt

1. **Merge til `main`** så GitHub Pages-deploy virker (miljøet `github-pages` tillader kun `main`).
2. **Datafordeler-secrets** (`DATAFORDELER_USER/PASSWORD`) → bekræftet ejerskab med BFE-numre.
   Optag EJF- og VUR-svar som fixtures og stram `_iter_ejerskaber`/`valuation`.
3. **CVR-adgang**: ansøg om system-til-system adgang hos Erhvervsstyrelsen (gratis) og sæt
   `CVR_ES_USER/PASSWORD` – fjerner afhængigheden af cvrapi.dk's kvote.
4. **Kalibrering**: gennemgå 20 boer manuelt mod tingbogen og justér pointene i `detect.py`.

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
