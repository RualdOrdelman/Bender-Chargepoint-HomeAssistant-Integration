# Loadbalancer: terugkoppeling bij verlagen

Status 18 november 2026: samen met de eerdere correctie voor expliciete Manual-keuzes geïnstalleerd na afzonderlijk akkoord. Configuratiecontrole en HA-herstartcontrole geslaagd. De fysieke begrenzings-, herstel- en pauzetest is op 18 november 2026 uitgevoerd; resultaten hieronder.

## Aanleiding en regressie

Op 18 november om 06:42:07–09 CET waren de P1-fasevermogens circa 3675/5548/3544 W, spanningen 230,2/231,4/232,1 V en gemeten laadstromen 15,002/15,047/15,083 A. Met 17250 W aansluitvermogen en 1000 W marge levert dat circa 14,6 A laadruimte op de beperkende fase L2: een opdracht van 14 A is passend.

De oude berekening gebruikte `min(gemeten laadstroom, nieuwe opdracht)` voor het aftrekken van de auto uit de netmeting. Een opdrachtverlaging veranderde daardoor onmiddellijk de geschatte huislast, nog vóór de meters en auto reageerden. De regressietest voert de echte templates en Manual-scripts herhaaldelijk uit met dezelfde metingen. Met de oude templates wordt dit 14, 13, 12, 11, 10, 9, 8, 7, 6, 0 A; met de correctie blijft het 14 A.

## Correctie

De berekening van totale beschikbare stroom, beschikbare stroom per fase en huislast per fase gebruikt dezelfde regels:

- Bij een geldige positieve opdracht (geheel 6–16 A) telt de gemeten laadstroom mee; een lagere opdracht knipt die meting niet meteen af.
- De faselezing moet numeriek en eindig zijn, tussen 0 en 17000 mA liggen en maximaal 25 seconden oud zijn volgens `last_reported`. Toekomstige of ontbrekende rapporten zijn ongeldig. De verrekening is maximaal 16000 mA, passend bij het installatieplafond.
- Een ongeldige meting geeft geen laadstroomverrekening: conservatief minder vrije ruimte.
- Bij opdracht 0 A is de verrekening onmiddellijk nul, ook bij nog positieve Modbus-metingen. De bestaande nulschrijver doet dit vóór de fysieke write; herstel vereist nog steeds bevestigde stilstand.
- De DSMR-validatie, actieve fail-safe, HEMS-bevestiging, prioriteit van pauze en bestaande verhogingsvoorwaarden blijven behouden. Er is geen nieuwe wachttijd voor verlagingen.
- De veiligheidsmarge en het herstelgedrag van instellingen zijn niet gewijzigd. De scenario's gebruiken 1000 W, verdeeld over drie fasen, en 3×25 A.

## Lokale tests

`tests/test_bender_loadbalancer_feedback.py` test de echte YAML offline:

1. De opgenomen nachtelijke situatie en herhaalde evaluaties zonder nieuwe metingen.
2. De nieuwe, lagere autostroom met de bijbehorende lagere P1-netafname.
3. Extra verbruik tijdens een nog onbevestigde verlaging: onmiddellijk verder begrenzen naar 10 A of stoppen, zonder klok vooruit te zetten.
4. Dezelfde onmiddellijke verlaging via de Direct-schrijver.
5. Overbelasting op elk van de drie fasen afzonderlijk.
6. Handmatige pauze, nulverrekening en geen herstart door achterblijvende stroommetingen.
7. P1 daalt vóór de Modbus-terugmelding: Manual verhoogt niet op basis van die tijdelijke schijnruimte.
8. Ontbrekende, te oude, toekomstige, negatieve, niet-eindige en onwaarschijnlijke metingen.
9. Ongewijzigde maar vers gerapporteerde stroom; overeenstemming van faseberekeningen en huislast.
10. Het absolute plafond voor verrekening en ongeldige opdrachten.

De nieuwe regressie is ook tegen de oude templates uitgevoerd: die faalt aantoonbaar op de oorspronkelijke neerwaartse reeks. De volledige Python-testreeks controleert daarnaast onder meer Manual-keuze, pauze, fail-safe, herstel, schrijfraces en opstartgedrag.

Resultaat: alle **119 Python-tests** en **8 Node-RED-coördinatortests** geslaagd. YAML en Jinja-templates zijn in de offline testreeks geparseerd; de echte HA-configuratiecontrole is daarna bij installatie geslaagd (zie hieronder).

## Grenzen en installatievoorwaarden

De offline testreeks is geen fysieke of HA-scheduler-test; de aanvullende fysieke resultaten staan hieronder. P1 en Modbus blijven asynchroon: als een lagere autostroom eerder binnenkomt dan de bijbehorende lagere netafname kan tijdelijk extra conservatief worden begrensd. De reparatie verwijdert de zichzelf versterkende reactie op een opdrachtwijziging, niet alle meetvertraging. Er wordt bewust niet eenvoudigweg een algemene vertraging op verlagingen gezet, omdat echte extra huislast direct begrensd moet blijven.

Voor een volgende installatie blijft de werkwijze: actuele status controleren, niet laden, herstelkopieën maken, Uit en HEMS 0 A bevestigen, de samengestelde lokale package-diff beoordelen, HA-configuratie valideren en gecontroleerd laden/begrenzen/herstellen/pauzeren testen. De marge blijft 1000 W. Node-RED hoeft voor deze reparatie niet gewijzigd te worden.


## Installatie en herstartcontrole — 18 november 2026

Voor installatie: auto aangesloten, niet ladend, strategie Uit, gewenste/gevraagde/opgedragen/bevestigde stroom 0 A en verse nulmetingen. Het serverpackage was nog gelijk aan de versie tijdens de nachtanalyse. Verse herstelkopie: `/home/ruald/bender-backups/loadbalancer-manual-step2-20261118T072011Z` (package en instellingen). Stap 1 heeft daarnaast een afzonderlijke herstelkopie.

Alleen `packages/bender_chargepoint_integration.yaml` vervangen. De configuratiecontrole eindigde met code 0. Instellingen bewaard, HA-herstart aangevraagd om 08:21:23 CET. Om 08:22:10 CET waren drie opeenvolgende controles geslaagd: Uit, Manual-keuze/opdracht/HEMS 0 A, 0 W, nulstroom op alle fasen en verse terugmeldingen. DSMR, Node-RED en HEMS gezond; fail-safe-modus Actief. Marge 1000 W, aansluitvermogen 17250 W en strategielimiet 16 A behouden; controller Safe Current 0 A en timeout 60 s uitgelezen.

Geïnstalleerde SHA256: `ff8ca92bce1c21a088f3cdcaf5f781e3f41efb54013fdcccd8d56a4438bbe9c0`, gelijk aan beide lokale packages. Tijdens deze installatie nog geen Node-RED-deployment of fysieke laadtest uitgevoerd; de laadtests volgden later die middag.

Geen Bender-configuratie- of templatefouten in het gecontroleerde herstartlog. Tijdens afsluiten werden enkele Marstek-sensoren tijdelijk onbekend; die waarden waren na opstart weer numeriek. Andere meldingen betroffen onder meer Bluetooth-rechten, ESPHome-bereikbaarheid en een niet-beschikbare WTW-entiteit; die zijn buiten deze wijziging gelaten. Auto-SOC en de reeds bekende oude sessieduursensor blijven onbekend/niet beschikbaar; deze wijziging repareert die niet.


## Fysieke tests — 18 november 2026, middag

Manual-keuzes: 6 A door de gebruiker bij de auto bevestigd; expliciete opdrachten 10 A en 16 A toegepast in respectievelijk circa 234 en 155 ms. Werkelijk circa 6,9 en 10,3 kW gemeten. Bij verhogen naar 16 A ontstond kort een opdracht van 15 A: de P1-netafname steeg vóór de volgende laadstroommeting, zodat de berekende ruimte circa drie seconden 15,6–15,7 A was. Automatisch herstel naar 16 A volgde; geen neerwaartse reeks naar nul. Deze meetvertraging is niet volledig weggenomen door de correctie.

De eerste begrenzingstest om 15:31 was niet bruikbaar als bewijs van stabiele positieve begrenzing: na tijdelijk verlagen van de aansluitcapaciteit naar 10250 W steeg de echte huislast op L2 van ongeveer 0,7 naar 2,1 kW. Opdrachten: 12 → 10 → 7 → 6 → 0 A. Onder de testlimiet resteerde circa 4,2 A, zodat stoppen terecht was. De Manual-keuze bleef 16 A. De testronde werd afgebroken en veilig afgesloten; dit is geen geslaagde stabiele begrenzingstest en ook geen bewijs van terugkeer van de oude opdrachtgedreven feedbackfout.

Vanwege de door de gebruiker gemelde 98% auto-SOC volgde een korte test met maximaal 10 A:

- Auto laadde eerst op 6 A en vervolgens stabiel op 10 A (circa 7 kW).
- Om 15:38:17 tijdelijk 8500 W aansluitcapaciteit ingesteld, met marge ongewijzigd 1000 W. Beschikbare stroom circa 7,4 A.
- De opdracht ging naar 7 A en bleef tijdens 50 seconden observatie op 7 A, zonder verdere neerwaartse reeks. De HEMS-terugmelding en fasestromen volgden; uiteindelijk circa 4,9 kW. De opgeslagen Manual-keuze bleef 10 A.
- Om 15:39:07 aansluitcapaciteit hersteld naar 17250 W. Automatisch herstel gaf om circa 15:39:38 een opdracht van 8 A. Meteen tijdens die eerste herstelstap handmatig Pauze gegeven. Een volledige automatische terugkeer tot 10 A is in deze ronde bewust niet afgewacht; de 8 A-opdracht is wel gezien, daadwerkelijk stabiel laden op 8 A niet als afzonderlijk resultaat gemeten.
- Na Pauze: keuze/opdracht 0 A, gemeten 0 W en nulstroom; de gebruiker bevestigde dat de auto gestopt was. HEMS meldde daarna ook 0 A. Vervolgens zeven opeenvolgende controles over circa 30 seconden bevestigden blijvende pauze bij voldoende laadruimte.
- Eindstand om 15:40:38: Uit, keuze/opdracht/HEMS 0 A, 0 W, nulstroom op alle fasen; aansluitcapaciteit 17250 W, marge 1000 W en strategielimiet 16 A hersteld. Gezondheidscontroles groen. Geen Bender- of templatefouten gevonden in het gecontroleerde testlog.

Een afzonderlijke tijdsbewaker was tijdens elke begrenzingstest actief en is na bevestigde veilige afsluiting vrijgegeven. Tijdens de fysieke tests zijn alleen bedieningsinstellingen aangepast; geen nieuwe package- of Node-RED-wijzigingen geïnstalleerd. Testbewijs staat in de lokale werkmap onder `snapshots/loadbalancer-short-recovery-20261118T143704Z` en de eerdere `manual-physical-step3-*` en `loadbalancer-physical-step4-*` mappen.


## Synchronisatie vóór publicatie

De actieve HA-package en het Bender-dashboard zijn vergeleken met beide lokale repositories. De vijf Bender-strategieflows zijn via Node-RED MCP uitgelezen en inhoudelijk vergeleken. Alleen de posities en groepsafmetingen in de Master-export verschilden; die lokale export volgt nu de serverindeling. Er is geen Node-RED-logica gewijzigd of gedeployd. Een ontbrekende versus lege `wires`-lijst bij een link-out-node wordt bij vergelijking als gelijk behandeld.
