# Juridiske forhold og databrug

## Kildernes vilkår

* **Statstidende** er en offentlig, lovpligtig bekendtgørelse. Data må læses og genbruges;
  systematisk udtræk i stor skala bør ske via API-aftale med Civilstyrelsen. Vi henter én gang
  dagligt med lav frekvens og identificerer os med User-Agent.
* **CVR** er offentligt (CVR-loven § 18). cvrapi.dk kræver identificerbar User-Agent.
  Erhvervsstyrelsens system-til-system adgang har egne vilkår om videredistribution.
* **Regnskabsdata** fra Erhvervsstyrelsen er åbne data.
* **Ejerfortegnelsen** (åben variant) er grunddata uden CPR; vilkår for tjenestebrugere på
  datafordeler.dk gælder. Beskyttede adresser returneres ikke.
* **DAWA** er åbne data (CC0-lignende vilkår).

## Persondata (GDPR)

Registret indeholder navne på kuratorer (advokater i professionel rolle, offentliggjort i
Statstidende) og eventuelt navne på ejere/ledelse fra CVR (offentligt register). Behandlingen
sker i legitim interesse (screening af investeringsmuligheder) og med data der allerede er
offentligt tilgængelige. Alligevel:

* Personlige konkurser filtreres fra (ingen CVR → ikke relevant, og mere persondatafølsomt).
* Der gemmes ikke CPR-numre, fødselsdatoer eller beskyttede adresser.
* Data slettes/opdateres ved hver kørsel; ældre kørsler beholdes kun som Actions-artefakter
  i 90 dage.
* Publicerer du dashboardet offentligt, er du dataansvarlig. Overvej at fjerne ejere/ledelse
  fra visningen, eller at kræve login.

## Ansvarsfraskrivelse

Værktøjet er et hjælpemiddel til screening. Der gives ingen garanti for fuldstændighed eller
rigtighed. Frister, ejerforhold og hæftelser skal altid verificeres i primærkilderne
(Statstidende, tingbogen, kurator) inden der handles.
