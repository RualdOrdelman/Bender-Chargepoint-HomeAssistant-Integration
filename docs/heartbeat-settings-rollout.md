# Heartbeat-tijd en bewaarde instellingen

Status: 30 oktober 2026, op de server geïnstalleerd en HA-herstarttest geslaagd.
Eindcontrole 18:00 CET: Uit, HEMS 0 A, 0 W, gezonde bewaking en oorspronkelijke
instellingen teruggezet. Bij afronding van deze uitrol waren server en beide lokale packages gelijk. De correcties en testverslagen zijn in deze versie opgenomen.
De aanvullende [Manual-opstartcorrectie](manual-startup-warning.md) is daarna lokaal getest, geïnstalleerd en met een HA-herstart gecontroleerd.

## Wijziging

- Gebruik het Unix-tijdstempelattribuut voor de heartbeatleeftijd. Het zichtbare
  tijdstip mist de tijdzone en onderscheidt het dubbele wintertijduur niet.
- Een heartbeat meer dan vijf seconden in de toekomst of zonder geldig tijdstempel
  is ongezond. De bestaande leeftijdsgrens blijft 30 seconden.
- Zet uitsluitend de heartbeathelper bij opstart op een oude datum. Een nieuwe
  Node-RED-heartbeat is vereist; oude herstelde lokale tijd is geen bewijs van verbinding.
- Verwijder `initial` voor strategielimiet, veiligheidsmarge en aansluitvermogen.
  HA herstelt geldige opgeslagen keuzes binnen de bestaande grenzen. De Manual-keuze
  blijft herstelbaar en tijdelijke opdrachten blijven bij opstart 0 A.
- Node-RED verstuurt al `timestamp` en behoeft geen aanpassing.

Zonder geldige herstelgegevens gebruikt HA de minimumwaarden: 6 A, 0 W marge,
5.000 W aansluitvermogen. Een nieuwe installatie moet deze waarden vóór laden
bewust configureren; er is geen opstartautomation die gebruikerskeuzes overschrijft.

## Lokale verificatie

`tests/test_bender_heartbeat_settings.py` voert de werkelijke YAML-templates uit:
beide 02:30-uren op 25 oktober 2026, veroudering tussen die uren, winter- en
zomertijdgrens, middernacht, leeftijd 30/31 seconden, ontbrekende/ongeldige gegevens,
toekomstige klokwaarden en de vereiste nieuwe heartbeat na opstart. De tests bewaken
ook herstelbare configuratie, ongewijzigde grenzen en het bestaande Node-RED-contract.

Vóór de reparatie is de wintertijdfout gereproduceerd: 10 s werd 3.610 s in het
tweede uur. Na de reparatie slagen de nieuwe 11 regressietests. De volledige controle slaagt:
93 Python-tests en 8 Node-tests in de Bender-repository, plus 9 Python-tests
in de HomeAssistant-config-repository (110 in totaal). Beide lokale packages zijn
byte voor byte gelijk; `git diff --check` geeft in beide repositories geen fouten.

Aanvullend zijn de originele methoden uit HA Core 2026.10.3 lokaal uitgevoerd,
met alleen framework en opslag vervangen door testobjecten:

- `InputDatetime.async_set_datetime` en `extra_state_attributes` behouden de
  verschillende Unix-tijdstempels bij dezelfde zichtbare tekst 02:30.
- `InputNumber.async_added_to_hass` herstelt 10 A, 1.750 W en 15.000 W en de
  onder-/bovengrenzen. Ontbrekende, ongeldige en buiten bereik liggende herstelwaarden
  vallen terug op de ondergrens. Een geldige 0 W marge blijft behouden.

Bronnen: [HA input_datetime](https://github.com/home-assistant/core/blob/2026.10.3/homeassistant/components/input_datetime/__init__.py)
en [HA input_number](https://github.com/home-assistant/core/blob/2026.10.3/homeassistant/components/input_number/__init__.py).
Dit is een geïsoleerde componenttest, geen echte HA-herstarttest of bewijs van
schrijven naar de herstelopslag van de draaiende installatie.

## Afgesproken invoerplan (referentie)

1. Controleer geen laden, strategie Uit en bevestigde HEMS 0 A. Noteer de drie
   actuele instellingen en maak een verse herstelkopie van package en herstelgegevens.
2. Plaats uitsluitend het package; voer de HA-configuratiecontrole uit. Het dashboard
   en Node-RED hebben voor deze wijziging geen deployment nodig.
3. Plan een gecontroleerde HA-herstart: controleer eerst vastlegging van de actuele
   helperwaarden. Alleen templates herladen bewijst geen herstel na een herstart.
4. Controleer dat de drie waarden exact terugkomen, de heartbeat na een nieuw bericht
   gezond wordt en Uit/0 A blijft staan. Houd rekening met de bestaande herstelwachttijd.
5. Indien nodig: test afwijkende waarden binnen de installatiegrenzen, inclusief
   een geldige 0 W marge zonder laden, en herstel daarna de vooraf genoteerde waarden.
6. Controleer logs, documenteer de uitkomst en synchroniseer/push daarna beide repositories.

Een fysieke laadtest is voor deze wijziging niet uitgevoerd. De zomer-/wintertijdgrens
wordt offline gesimuleerd; wijzig daarvoor nooit de klok van de productieserver.

## Uitgevoerd op 30 oktober 2026

- 17:51 CET: auto aangesloten zonder laden; verse CP-status 2, 0 W, 0 mA op alle
  fasen, HEMS 0 A en gezonde bewaking. Strategie Uit en Manual-keuze 0 A.
- Vastgelegde instellingen: 16 A strategielimiet, 1.000 W veiligheidsmarge,
  17.250 W aansluitvermogen. Controller Safe Current 0 A en timeout 60 s.
- Herstelkopieën op de server:
  `/home/ruald/bender-backups/2026-10-30T165233Z-heartbeat-settings`.
  Package, dashboard, Node-RED-flows en `core.restore_state` zijn gekopieerd en
  op inhoud gecontroleerd. De serverversie kwam overeen met de verwachte uitgangsversie.
- Uit en HEMS 0 A opnieuw bevestigd; alleen het package is atomair vervangen,
  met behoud van eigenaar en rechten. De ingebouwde HA-configuratiecontrole slaagde.
- De test stelde tijdelijk strengere waarden in: 10 A, 1.500 W en 15.000 W.
  Via `homeassistant.save_persistent_states` zijn ze vóór herstart opgeslagen.
- Eerste herstart om 17:55:09: alle drie de testwaarden kwamen correct terug,
  maar het externe testprogramma benaderde een nog ontbrekende sensor. Het programma
  brak af en herstelde automatisch de oorspronkelijke instellingen en Uit/0 A.
  Dit was een fout in de testcontrole; het geïnstalleerde package is niet aangepast.
- Tweede herstart om 17:56:48 met een gecorrigeerde testcontrole. Om 17:57:23 waren
  de drie testwaarden exact hersteld, alle relevante controllerwaarden vers en nul,
  de bewaking gezond en een nieuwe heartbeat ontvangen. De vaste beginwaarde van
  de heartbeat (-3600 als Unix-tijdstempel) is tijdens de opstart waargenomen,
  gevolgd door een nieuwe actuele tijdstempel. De instellingen hebben na herstart
  geen vaste `initial`-waarde meer.
- Een volledige minuut observatie: Uit/0 A/0 W, nulstroom op alle fasen, de testwaarden
  onveranderd en de heartbeat elke circa tien seconden bijgewerkt.
- Om 17:58:24 oorspronkelijke waarden 16 A/1.000 W/17.250 W teruggezet en opgeslagen.
  De eindcontrole om 18:00:15 bevestigde opnieuw Uit, HEMS 0 A, 0 W en gezonde bewaking.
  Ook `core.restore_state` bevat de oorspronkelijke waarden.
- Het gewijzigde HA-Pythonproces bevestigt de herstart. Node-RED en DSMR zijn niet
  herstart; hashes van flowbestand en dashboard zijn ongewijzigd.

Server en beide lokale packages hebben SHA-256
`45a08ec1cc59303df09bbfdda7ddaa95195a58af2e76db18661ac60a6fc45b69`.
Bewijs op de laptop: `snapshots/2026-10-30-heartbeat-settings-deploy` in de werkmap,
inclusief beide testpogingen, de herstelkopiegegevens en de eindcontrole.

### Logmeldingen en grenzen van de test

Tijdens de eerste opstart verscheen één Bender Manual-templatewaarschuwing:
`None has no attribute last_changed` voor een nog ontbrekende
`binary_sensor.bender_manual_increase_ready`. Die verscheen niet in de tweede
opstartronde. Nulopdrachten en herstel zijn bevestigd; de waarschuwing is vastgelegd
als afzonderlijk opstartpunt, niet binnen deze wijziging gerepareerd. Daarna is dit
punt [lokaal gerepareerd en getest](manual-startup-warning.md); die aanvullende correctie is daarna geïnstalleerd en na een HA-herstart gecontroleerd; zie het gekoppelde verslag.
Verder waren er opstartmeldingen van andere integraties (onder meer Marstek,
Bluetooth en niet-bereikbare ESPHome-apparaten). Die zijn niet gewijzigd.

Er was geen onafhankelijke continue laadmeting terwijl HA niet bereikbaar was.
Vóór en na beide herstarts waren verse nulmetingen aanwezig; er zijn geen positieve
laadopdrachten gegeven. De zomer-/wintertijdovergang is lokaal getest, niet door de
serverklok te verzetten. De 0 W-margegrens is lokaal getest; live zijn de hierboven
genoemde drie afwijkende waarden getest. De vergelijking vóór publicatie bevestigde gelijke actieve serverbestanden en lokale kopieën; de tests en verslagen worden als repositorybestanden beheerd.
