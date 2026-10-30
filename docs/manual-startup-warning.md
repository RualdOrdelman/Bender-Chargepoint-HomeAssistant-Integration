# Manual-templatewaarschuwing tijdens HA-opstart

Status 30 oktober 2026: na apart akkoord op de server geïnstalleerd en met een
HA-herstart gecontroleerd. Eindstand 18:13:14 CET: Uit, HEMS 0 A, 0 W en gezonde
bewaking. De eerder geïnstalleerde heartbeat- en instellingenreparatie blijft behouden.
Node-RED en dashboard zijn ongewijzigd. De correctie, regressietests en testverslagen zijn in deze versie opgenomen.

## Oorzaak

Het vastgelegde log van de HA-herstart van 17:55:40 meldt:
`None has no attribute last_changed` in de variabele `manual_ceiling` van
`script.set_bender_hems_limit`.

De variabelen van die gezamenlijke schrijfroute worden ook berekend wanneer de
strategie Uit of Direct is. De Manual-gereedsensor kan tijdens het opbouwen van
de HA-entiteiten nog ontbreken. De oorspronkelijke directe toegang tot
`states.binary_sensor.bender_manual_increase_ready.last_changed` veroorzaakt dan
de waarschuwing, vóórdat `as_timestamp(..., 0)` een terugvalwaarde kan toepassen.

## Correctie

Lees eerst het sensorobject en gebruik `last_changed` alleen als het object niet
`none` is. Bij afwezigheid krijgt `ready_at` de waarde 0. De bestaande controle
dat de gereedsensor daadwerkelijk `on` moet zijn blijft staan. Een ontbrekende
sensor kan daardoor geen verhoging toestaan. De dertig seconden wachttijd,
feedbackcontroles, stoproute en gebruikerskeuze zijn niet veranderd.

Deze reparatie is beperkt tot de vastgestelde Manual-gereedsensor. Er is geen
algemene onderdrukking van templatewaarschuwingen toegevoegd.

## Tests

De nieuwe testmodule `tests/test_bender_manual_startup.py` voert de echte
YAML-scripts uit. Een ontbrekende entiteit levert in dit testmodel `None` op,
zoals bij HA, en elke poging om daarvan `last_changed` of `last_reported` te lezen
laat de test falen. Het eerdere algemene model gaf voor ontbrekende entiteiten
een object met lege attributen terug en maakte deze specifieke fout niet zichtbaar.

De acht nieuwe tests dekken:

- De vastgelegde situatie: Uit/0 A terwijl de Manual-gereedsensor ontbreekt.
- Geen starten of verhogen bij een ontbrekende sensor, met behoud van Manual-keuze.
- Geen verhogen bij `unknown`, `unavailable` of `off`.
- Verlagen van 12 A naar 10 A blijft mogelijk.
- Een storingsstop blijft mogelijk en bewaart de gekozen stroom.
- Na terugkeer van de sensor is eerst de gewone wachttijd nodig; hervatten begint op 6 A.
- Handmatige pauze tijdens afwezigheid blijft staan nadat de sensor terugkomt.
- Direct blijft werken zonder afhankelijkheid van de Manual-gereedsensor.

Vóór de reparatie reproduceerde deze suite de waarschuwing (negen falende
gevallen, inclusief subtests); na de reparatie slagen alle acht tests.
De volledige regressieset slaagt: **101 Python-tests en 8 Node-tests** in de
Bender-repository, plus **9 Python-tests** in HomeAssistant-config: **118 tests**
in totaal. YAML-templateparsing en `git diff --check` slagen ook.
Dit deel betreft lokale script- en tijdsimulaties; de later uitgevoerde HA-herstart staat hieronder.

## Bestanden en latere controle

De packagekopieën in HomeAssistant-config en BenderChargepointIntegration zijn
byte voor byte gelijk. Hun nieuwe SHA-256 is
`79d29c245ba3da89afafad72cf56c8a3fc03d4e04f6a731f9fa8b80045a6318e`.
De serverversie vóór installatie had SHA-256
`45a08ec1cc59303df09bbfdda7ddaa95195a58af2e76db18661ac60a6fc45b69`;
die was tijdens het lokale onderzoek niet aangepast. Bij de latere installatie is deze uitgangsversie opnieuw gecontroleerd; server en lokale packages hebben nu beide de nieuwe hash hierboven.

Het afgesproken invoerplan was: geen laden, Uit/HEMS 0 A,
verse herstelkopie en configuratiecontrole. Controleer bij een gepland herstartmoment
dat de waarschuwing wegblijft en Uit/0 A behouden blijft. Een toevallig ontbrekende
waarschuwing bij één herstart vervangt de lokale ontbrekende-entiteitstest niet.

## Serverinstallatie en herstartcontrole

- Vooraf: auto aangesloten zonder laden (CP 2), verse nulmetingen op alle fasen,
  0 W en HEMS 0 A. Instellingen 16 A, 1.000 W marge en 17.250 W aansluitvermogen.
- Verse herstelkopie: `/home/ruald/bender-backups/2026-10-30T171000Z-manual-startup`. Package, dashboard, flows en herstelopslag
  zijn gekopieerd en gecontroleerd. De uitgangsversie kwam overeen met de verwachting.
- Uit/0 A expliciet bevestigd. Uitsluitend het package is atomair vervangen,
  met behoud van eigenaar en rechten. De HA-configuratiecontrole slaagde.
- HA-herstart aangevraagd om 18:11:02 CET. Het gewijzigde
  HA-Pythonproces bevestigt de herstart; Node-RED en DSMR zijn niet herstart.
- Om 18:11:37 CET waren verse nulmetingen,
  Uit/0 A, de oorspronkelijke instellingen en gezonde bewaking bevestigd.
  Een nieuwe heartbeat was ontvangen. Daarna bleven deze waarden een volle minuut
  stabiel, zonder positieve laadopdrachten.
- Afgesloten op Uit/0 A; laatste verse controle om 18:13:14 CET.
  De oorspronkelijke instellingen zijn ook in de herstelopslag bevestigd.
- De logs vanaf installatie bevatten de onderzochte Manual-templatewaarschuwing
  niet. De logcontrole is beperkt tot deze herstart en observatieperiode;
  de lokale regressietest dekt expliciet de ontbrekende sensor.
- Hashes van het dashboard en Node-RED-flowbestand zijn ongewijzigd.

Bewijs: `snapshots/2026-10-30-manual-startup-deploy` in de werkmap en de genoemde
serverherstelmap. Tijdens de HA-onderbreking was er geen onafhankelijke continue
laadmeting; vóór en na de herstart waren verse nulmetingen aanwezig.
Andere opstartmeldingen van integraties buiten deze correctie zijn vastgelegd,
niet aangepast. De vergelijking vóór publicatie bevestigde gelijke actieve serverbestanden en lokale kopieën; de tests en verslagen worden als repositorybestanden beheerd.
