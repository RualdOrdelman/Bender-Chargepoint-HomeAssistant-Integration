# Manual-stroom onthouden — invoerplan

**Actuele stand — 30 oktober 2026:** de Manual-regeling, Master-stopcorrectie en SOC-correctie staan op de server. De afgesproken laad-, begrenzings-, herstel-, pauze- en HA-herstarttests zijn afgerond met de hieronder genoemde meetbeperkingen. De serverconfiguratie en de vijf actieve Bender-flows zijn vergeleken met de lokale exports. De secties hieronder zijn een chronologisch verslag; eerdere vermeldingen van openstaande stappen beschrijven de toenmalige stand.

De aanvullende P1- en warmtepompcorrecties staan in de afzonderlijke HomeAssistant-config-repository en zijn op 30 oktober om 17:21 CET geïnstalleerd. Negen lokale regressietests slagen. De tweede template-herlaadcontrole gaf geen P1- of warmtepompvalidatorfout. De bestaande watchdog bleef ongewijzigd; tijdens herladen bleven de bekende meldingen over overlappende triggers bestaan, waarna de bewaking herstelde. Eindstand Uit/HEMS 0 A. Dit verandert de scope van de niet-afgeronde ChargePV- en Dynamic-strategieën niet.

Status op 29 oktober 2026: stappen 1–3 zijn uitgevoerd; het Manual-package, dashboard en de Manual-flow staan op de server. Stap 4 is uitgevoerd met losgekoppelde auto: opbouw 0 → 6 → … → 16 A, begrenzing op 12 A met behoud van keuze 16 A, herstel, 75 seconden blijvende pauze en opnieuw selecteren van Manual zijn geslaagd. Eindstand: Uit, bevestigd 0 A, keuze 0 A, maximum 16 A.

Tijdens Pauze werd aanvankelijk een Modbus-verzoek geannuleerd. De HA-trace bevestigde dat het wissen van de keuze de automatische regeling start, waarna het pauzescript zelf ook een nulopdracht verstuurt. De stopcorrectie is inmiddels op de server geladen: de nulschrijver draait onafhankelijk met `single`, en het pauzescript start de bewaakte regelaar asynchroon zodat een onderbroken regelaar niet ook de dashboard/API-aanroep afbreekt.

## Stopcorrectie — uitgevoerd op 29 oktober 2026

- Verse herstelkopieën gemaakt; beide installaties zijn met de ingebouwde HA-configuratiecontrole gevalideerd. Alleen het package en de geladen scripts zijn bijgewerkt. Dashboard, Node-RED-flows, Modbus-verbindingen en HA-container zijn niet herstart of gewijzigd.
- De eerste live ronde liet nog een afgebroken API-aanroep zien; de nulstand werd wel bereikt. De aanvullende lokale test reproduceert het doorgeven van annulering aan een synchroon wachtend pauzescript. De asynchrone aanroep voorkomt dit. 71 Python- en 8 Node-tests slagen.
- Definitieve live ronde: 16:07–16:12 CET, auto los. Handmatige keuze 6 A werd bevestigd; gewone Pauze wiste de keuze en leverde bevestigde 0 A op. Daarna opnieuw 6 A bevestigd en `bender_manual_set_current(current=0)` gecombineerd met twee gelijktijdige nulverzoeken: alle API-aanroepen geslaagd, dubbele starts van de nulschrijver overgeslagen, 0 A bevestigd.
- Pauze vervolgens 75 seconden behouden bij ruimte voor 16 A. Geen HA/Modbus-foutmeldingen in deze ronde. Eindstand Uit, keuze 0 A, gevraagd/bevestigd 0 A, maximum 16 A, gezonde bewaking en auto los.
- Traces tonen overgeslagen dubbele starts en voltooide nulschrijvingen. Enkele eerste, nog lopende traces waren vóór de volgende opname uit de beperkte HA-tracehistorie verdwenen. De lokale asynchrone regressietests dekken de onderbrekingsvolgordes aanvullend; dit is geen fysieke laadtest.
- Package SHA-256: `0a6aad02302d0e40057dfda2bce9e34c1e2754b49fb0ead32ba16e8e692c52d8`; server en beide lokale kopieën gelijk. Herstelkopieën onder `/home/ruald/bender-backups/2026-10-29T145856Z-pause-fix-deploy` (vóór de nulschrijvercorrectie) en `/home/ruald/bender-backups/2026-10-29T150658Z-pause-caller-deploy` (vóór de aanvullende aanroepcorrectie). Lokaal testbewijs staat in gelijknamige snapshotmappen van de werkmap.

## Fysieke Manual-tests — uitgevoerd op 30 oktober 2026

- De auto laadde op 6 A met ongeveer 4,3 kW; 60 seconden stabiel geobserveerd en door de gebruiker bij de auto bevestigd.
- Gewone Pauze gaf binnen ongeveer 12 seconden verse bevestiging van HEMS 0 A, 0 W en nulstroom op alle fasen. De gebruiker bevestigde de stop; drie minuten geen hervatting bij ruimte voor 16 A.
- Van 09:38 tot 09:50 CET: keuze 10 A opgebouwd via 6, 7, 8 en 9 naar 10 A; werkelijk laadvermogen ongeveer 7 kW. Tijdelijke strategielimiet 6 A verlaagde opdracht en fysieke stroom, terwijl de keuze 10 A bleef.
- Na herstel van de strategielimiet naar 16 A volgde zelfstandig 6 → 7 → 8 → 9 → 10 A. Tweede begrenzing naar 6 A, vervolgens herstel naar daadwerkelijk circa 7 A en Pauze tijdens die opbouw: keuze/opdracht 0 A, daarna bevestigd HEMS 0 A, 0 W en nulstroom. De gebruiker bevestigde ook deze stop. Twee minuten geen hervatting.
- HA-historie bevestigt opdrachten `0,6,7,8,9,10,6,7,8,9,10,6,7,0` en gebruikerskeuze `0,10,0`; geen extra positieve opdracht na Pauze. Verhogingen in stappen van 1 A met meer dan 30 seconden ertussen. Geen HA-logmeldingen in deze testronde.
- Eindstand Uit, bevestigde HEMS 0 A, keuze 0 A, strategielimiet 16 A, 0 W, auto aangesloten en bewaking gezond. Testbestanden en historie bewaard in de werkmap onder `snapshots/2026-10-30T083812Z-manual-physical-ramp`.

Deze test gebruikt een tijdelijke strategielimiet, geen overbelasting van de huisaansluiting. De aansluitende uitvaltests hieronder hebben een DSMR-herstelprobleem aangetoond. GitHub pas bijwerken na de afgesproken validatie.

## Manual-uitvaltests — 30 oktober 2026

De gerichte tests onderbraken alleen het DSMR-tijdstempeltopic of de Bender-heartbeat. DSMR, Node-RED en HA zijn niet gestopt of herstart; andere MQTT-velden en flows bleven actief. Dit test de watchdogroutes, niet een volledige containeruitval.

- **DSMR, 10:05–10:11 CET:** geladen op 6 A; verouderd telegram gedetecteerd; bevestigde HEMS 0 A en fysieke nulstroom om 10:07:19. Gebruiker bevestigde stop en storingspush. De automatische stop wiste echter de Manual-keuze van 6 naar 0 A. Na gezond herstel om 10:10:06 bleef laden daardoor uit. Veilig stoppen geslaagd; keuze bewaren en automatisch hervatten afgekeurd.
- **Node-RED-herstel, 10:12–10:18 CET:** heartbeat tijdelijk onderbroken, keuze 6 A behouden, bevestigd gestopt om 10:14:19. Na herstel en stabilisatie zelfstandig hervat op 6 A, fysiek bevestigd om 10:18:08; daarna veilig afgesloten.
- **Node-RED-pauze, 10:28–10:34 CET:** opnieuw 6 A geladen; bij heartbeatverlies keuze behouden en fysiek gestopt. Om 10:30:22 gewone Pauze gegeven tijdens actieve storing: keuze naar 0 A. Gebruiker bevestigde stop en storingspush. Na gezond herstel om 10:33:06 nog 90 seconden HEMS 0 A, 0 W en nulstroom, zonder hervatting. Geslaagd.
- Eerste poging van de Node-RED-pauzetest afgebroken vóór foutinjectie: de DSMR-tijdstempel bleef op 10:25:57 staan en werd rond 10:26:32 weer actueel. Rond 10:26:29 werd de keuze gewist en gestopt. De gepollde gezondheidsstatus bleef aan; deze korte vertraging kan de directe versheidscontrole eerder laten ingrijpen dan de periodieke watchdog. De oorzaak van de vertraging is nog niet vastgesteld. De herhaalde Node-RED-test had dit probleem niet.

### Vastgestelde fout en vervolg

In de tijdens de live test gebruikte Master gaat uitgang 2 van `bender_master_lb_rate_limit` bij ongeldige laadruimte of minder dan 6 A rechtstreeks naar `bender_master_link_uit`. Die roept `script.bender_stop_charging` aan, dat in Manual de gebruikerskeuze wist. DSMR-veroudering maakt de laadruimtesensor 0 A. De bewaarde HA-trace van 10:06:54 toont het wissen via deze stopfunctie. Automatische veiligheidsstop en bewuste Pauze zijn daardoor onvoldoende gescheiden.

De toen vastgestelde vervolgstap (hieronder inmiddels lokaal uitgevoerd): automatische stop moet 0 A afdwingen met behoud van Manual-keuze; alleen bewuste Pauze/geplande stop/strategiewissel mag de keuze wissen. Test ook echte laadruimte onder 6 A, herstel en overlappende stopverzoeken. Daarna gecontroleerd uitrollen en DSMR-herstel opnieuw fysiek testen. Een aparte DSMR-pauzeproef was toen niet onafhankelijk te beoordelen, omdat de automatische stop de keuze al wist; die is na reparatie alsnog geslaagd, zoals hieronder vastgelegd. Ook behoud van pauze bij een afgesproken HA-herstart blijft open. Er is in deze fase geen logische reparatie of GitHub-push uitgevoerd.

### Eindcontrole

Om 10:34:51 CET: strategie Uit, keuze/opdracht/bevestigde HEMS 0 A, strategielimiet 16 A, 0 W, alle fasen 0 mA, auto aangesloten en bewaking gezond. DSMR-instellingen exact hersteld; beide heartbeat-herstelbewakers succesvol afgerond. Alle 1024 Node-RED-nodedefinities gelijk aan de beginstand; HA-package en dashboard ongewijzigd. Geen containerherstart. Bewijs: `snapshots/2026-10-30T090129Z-manual-fault-tests` in de werkmap; herstelkopie met dezelfde naam onder `/home/ruald/bender-backups`.


Bij terugzetten: eerst Uit en bevestigde 0 A, wachten totdat de nulschrijver inactief is, het vorige package herstellen en scripts herladen. Controleer opnieuw bewaking en nulstand. De oudere Manual-functionaliteit blijft dan behouden, met het bekende aandachtspunt bij dubbele stopopdrachten.

## Automatische stop gescheiden van Pauze — lokaal gerepareerd op 30 oktober 2026

**Lokaal gerepareerd en daarna op 30 oktober om 10:47 CET op de server geïnstalleerd; fysieke DSMR-herstel- en pauzehertest inmiddels geslaagd (zie hieronder).** Alleen `NodeRed/bender_strategy_master.json` heeft een functionele wijziging. Beide lokale HA-packagekopieën, dashboard, Manual-flow en controllerinstellingen zijn in deze reparatie ongewijzigd. Tijdens de lokale reparatie zijn SSH en live MCP niet gebruikt; de latere serverinstallatie staat afzonderlijk hieronder beschreven.

Uitgang 2 van `bender_master_lb_rate_limit` gaat nu naar `bender_master_automatic_stop`. Deze node roept `script.turn_on` aan voor de bestaande `script.set_bender_hems_limit`, met vaste `variables.current: 0`, zonder wachtrij en met geblokkeerde berichtoverschrijvingen. Hiermee blijven opdrachtregistratie, nulschrijver, bevestigingsbewaking en fail-safe behouden. De node schrijft niet rechtstreeks naar Modbus en bewaart/herstelt zelf geen oude gebruikerskeuze. De bestaande Uit-route en de Pauze-knop blijven `script.bender_stop_charging` gebruiken. Dat script wist de Manual-keuze; een later automatisch nulverzoek kan die niet terugzetten.

De nieuwe regressietests voeren de werkelijke Master-functie uit en volgen de geëxporteerde bedrading/servicegegevens naar het bestaande YAML-testmodel. Vóór de flowcorrectie faalden de tests aantoonbaar op keuze 0 in plaats van 16 A; na de correctie slagen alle **78 Python-tests en 8 Node-tests**. Gedekt zijn DSMR-veroudering vóór bijgewerkte gezondheidsstatus, ontbrekende/ongeldige laadruimte, laadruimte onder 6 A, bevestigde stilstand en stabiele opbouw 0 → 6 → 7 A, Pauze vóór/tijdens/na storing, late nulverzoeken, mislukte nulwrite met behouden deadline, en gelijktijdige automatische stop/handmatige pauze. De asynchrone tests bevestigen dat een automatische stop een positieve write mag onderbreken, terwijl dubbele nulverzoeken de lopende nulwrite niet annuleren.

Dit is lokale validatie met gesimuleerde HA-planning en een adapter voor statische Node-RED-serviceconfiguratie. Het bewijst nog niet de echte websocket-node, HA-runtime of fysieke laadstop na deze wijziging.

### Invoerstappen — installatie en DSMR-hertests uitgevoerd

1. Actuele serverversie opnieuw vergelijken, herstelkopie van Master maken en auto/strategie/vermogen controleren. Eerst Uit en verse bevestigde HEMS 0 A.
2. Verifiëren dat het bestaande package met bewaakte schrijver en onafhankelijke nulschrijver nog actief is. Geen package- of dashboardherstart nodig voor deze correctie.
3. Alleen Master bijwerken; andere tabs en bestaande node-ID's behouden. Controleer heartbeat, bewaking en nulstand.
4. Onder toezicht op 6 A: DSMR-tijdstempeluitval, fysieke stop en push, behouden Manual-keuze en gecontroleerd herstel. Herhalen met Pauze tijdens de storing: geen hervatting. Test ook tijdelijke laadruimte onder 6 A en herstel, zonder de huisaansluiting werkelijk te overbelasten.
5. Afsluiten op Uit/HEMS 0 A, alle testinstellingen herstellen en bewijs vastleggen. Pas na geslaagde live validatie synchroniseren/committen/pushen. De afzonderlijke HA-herstarttest voor behoud van pauze blijft open.

Bij terugzetten: eerst Uit/0 A bevestigen, daarna uitsluitend de vorige Master-export terugzetten. Die oude versie heeft nog het bekende verlies van Manual-keuze bij automatische stop. Herstelbewijs en lokale wijzigingsbestanden staan in de werkmap in de snapshotmap met suffix `manual-auto-stop-local`.

## Master-correctie geïnstalleerd — 30 oktober 2026, 10:47 CET

Op expliciet akkoord alleen Master bijgewerkt; geen laadtest gestart. Auto aangesloten maar niet ladend, met verse 0 W en 0 mA op alle fasen. Strategie expliciet op Uit gezet en nulopdracht gegeven; verse HEMS 0 A bevestigd om 10:45:24 CET. Fail-safe bleef Actief en de bewaking gezond.

Verse herstelkopie van Master en alle flowdefinities: `/home/ruald/bender-backups/2026-10-30T094428Z-master-auto-stop-deploy`. De serverversie kwam inhoudelijk overeen met de geteste uitgangsversie. De server laat bij vier link-out-nodes een lege `wires`-lijst weg; die ongewijzigde serverrepresentatie is behouden.

Deploy uitsluitend via de Master-tab. Na teruglezen waren precies de groepsledenlijst en stopbedrading gewijzigd, plus de nieuwe node `bender_master_automatic_stop`. Alle andere nodedefinities, het HA-package en het dashboard zijn gelijk aan de verse herstelkopie. Geen HA- of containerherstart. Lokale Master-export en server zijn inhoudelijk gelijk. De recente logs tonen de Master-update en geen gevonden foutmelding.

Zeven controles over ruim één minuut na de installatie bevestigden Uit, HEMS 0 A, 0 W en gezonde besturing. Handmatige keuze bleef 0 A; strategielimiet bleef 16 A. Bewijs staat in de werkmap onder `snapshots/2026-10-30T094428Z-master-auto-stop-deploy`. Geen GitHub-push uitgevoerd.

**Status na de onderstaande hertest:** fysieke DSMR-uitval/herstel vanaf 6 A en Pauze tijdens DSMR-storing geslaagd. De tijdelijke laadruimte onder 6 A en het herstel zijn inmiddels live gemeten (zie hieronder); de gebruiker bevestigde de stop; hervatten is alleen via verse fysieke laadpaalmetingen bevestigd. Nog uit te voeren: HA-herstart met behoud van pauze. Hiervoor eerst opnieuw de actuele toestand controleren en de afzonderlijke test afspreken.

## Fysieke DSMR-hertest na Master-correctie — geslaagd op 30 oktober 2026

Van 10:50 tot 11:04 CET zijn beide afgesproken tests op maximaal 6 A uitgevoerd. Alleen het DSMR-tijdstempeltopic werd per ronde drie minuten onderbroken; andere metingen bleven beschikbaar. De normale herstelroutine en een onafhankelijke herstelbewaker hebben beide rondes succesvol afgerond. Dit valideert de DSMR-versheidsbewaking, niet een volledige uitval van alle DSMR-topics of de container.

- **Automatisch herstel:** vóór storing werkelijk laden op 6 A en circa 4,4 kW. Storing gedetecteerd om 10:52:46, verse HEMS 0 A, 0 W en nulstroom op alle fasen om 10:52:54. De Manual-keuze bleef 6 A. Na terugkeer van de tijdstempel werd de bewaking gezond om 10:55:51; na de aanvullende Manual-wachttijd zelfstandig hervat. Fysiek laden bevestigd om 10:56:49, circa 4,0–4,2 kW, vervolgens 20 seconden stabiel. Gebruiker bevestigde stop, hervatten, storingspush en herstelpush. Tussen de rondes afgesloten op Uit en 0 A.
- **Pauze tijdens storing:** opnieuw werkelijk laden op 6 A; DSMR-storing gedetecteerd om 10:59:50. Om 11:00:00 waren HEMS 0 A, 0 W en nulstroom bevestigd met keuze nog 6 A. Daarna gewone Pauze gegeven tijdens actieve storing: keuze naar 0 A. Na gezond herstel om 11:03:01 bleef de auto nog 90 seconden op HEMS 0 A, 0 W en nulstroom. Gebruiker bevestigde stop, beide pushes en blijvende stilstand na herstel.
- De HA-historie bevestigt opdrachten `0,6,0,6,0,6,0`, gebruikerskeuze `0,6,0,6,0` en strategie `Uit,Manual,Uit,Manual,Uit`. Geen positieve opdracht na de laatste Pauze.

Eindcontrole om 11:04:50 CET: Uit, keuze/opdracht/bevestigde HEMS 0 A, 0 W, alle fasen 0 mA, strategielimiet 16 A, auto aangesloten en bewaking gezond. Alle 1025 nodedefinities en beide HA-bestanden gelijk aan de beginstand; DSMR-instellingen exact hersteld; geen containerherstart. Geen codewijziging, deployment of GitHub-push tijdens deze hertest.

Logwaarnemingen: bij beide foutdetecties eenmaal `Bender Hard Fail-safe Watchdog: Already running` (dubbele start terwijl de automation loopt); stoppen en melden zijn in beide rondes geslaagd. Node-RED meldde daarnaast om 11:00:13 een `Connection lost` bij de andere node `Zet WTW stand med`. Die node is niet gewijzigd of onderzocht; geen effect op deze gemeten Bender-testresultaten vastgesteld. Dit is dus geen foutloze-logclaim.

Het eerder aangetoonde verlies van Manual-keuze bij DSMR-uitval is in deze fysieke hertest opgelost bevonden. Bewijs en herstelkopieën: werkmap `snapshots/2026-10-30T095010Z-dsmr-manual-retest`, server `/home/ruald/bender-backups/2026-10-30T095010Z-dsmr-manual-retest`. De afzonderlijke test met laadruimte onder 6 A is later uitgevoerd en staat hieronder beschreven. De afgesproken HA-herstarttest voor behoud van pauze blijft open; die is niet uitgevoerd binnen de DSMR-testopdracht.

## Laadruimte onder 6 A — live metingen geslaagd op 30 oktober 2026

Test uitgevoerd van 11:19 tot 11:23 CET, zonder HA-herstart. Auto aangesloten, vooraf Uit/HEMS 0 A en gezonde bewaking. Manual-keuze ingesteld op 6 A. Werkelijk laden bevestigd om 11:20:05, circa 4 kW met stroom op alle drie de fasen.

Om 11:20:15 alleen de Bender-loadbalancer tijdelijk conservatiever ingesteld: veiligheidsmarge van 1000 naar 5000 W en verondersteld huisaansluitingsvermogen van 17250 naar 5000 W. Dit verlaagt de berekende laadruimte; er zijn geen extra verbruikers aangezet, geen meetwaarden vervalst en geen elektrische aansluitlimieten verhoogd. Berekende laadruimte werd 0 A. De stopopdracht volgde onmiddellijk; om 11:20:25 waren verse HEMS 0 A, 0 W en 0 mA op alle fasen bevestigd. Manual-keuze bleef 6 A. Nog 45 seconden stilstand bij onvoldoende ruimte, zonder storingsmodus: DSMR/Node-RED en besturing bleven gezond, fail-safe niet actief.

Om 11:21:11 oorspronkelijke instellingen hersteld: huisaansluiting 17250 W, marge 1000 W, berekende laadruimte weer 16 A. Geen nieuwe Manual-keuze gegeven. Na de stabilisatiewachttijd volgde zelfstandig een 6 A-opdracht; fysieke laadstroom en circa 4 kW bevestigd om 11:22:06, vervolgens 20 seconden stabiel gevolgd.

Afgesloten op Uit; keuze/opdracht/bevestigde HEMS 0 A, 0 W en nulstroom bevestigd om 11:22:56. Eindcontrole om 11:23:40 bevestigde beide oorspronkelijke loadbalancerinstellingen en strategielimiet 16 A. De onafhankelijke herstelbewaker is om 11:23:00 beëindigd zonder ingreep omdat de normale afsluiting was geslaagd. Alle flows en HA-bestanden ongewijzigd; geen containerherstart en geen GitHub-push.

HA-historie: opdrachten `0,6,0,6,0`, Manual-keuze `0,6,0`, strategie `Uit,Manual,Uit`, fail-safe voortdurend uit. Dit bevestigt automatisch stoppen en hervatten met behoud van keuze. De gebruiker heeft de fysieke stop op het autoscherm bevestigd. Het latere antwoord over hervatten beschrijft de verwachte eindstand Uit/0 A nadat de test was afgesloten; het eerdere hervatten is daarmee niet onafhankelijk door de gebruiker bevestigd. De hervatting is wel vastgesteld via verse fysieke laadpaalmetingen, niet alleen via het HEMS-register.

Bewijs: werkmap `snapshots/2026-10-30T101526Z-manual-low-headroom-test`; serverherstelkopie met dezelfde mapnaam onder `/home/ruald/bender-backups`. De exacte overgang rond 5,9/6,0 A is hiermee niet fysiek gekarakteriseerd: de test gebruikte 0 A beschikbare ruimte, dus duidelijk onder de minimumstroom. Nog open uit het invoerplan: HA-herstart met behoud van handmatige pauze, daarna definitieve server/laptopvergelijking, documentatiecontrole en commits/push naar beide repositories.

## Gewenst resultaat

Gekozen 16 A blijft 16 A wanneer de loadbalancer de werkelijke HEMS-limiet tijdelijk naar 12 A verlaagt. Bij voldoende stabiele ruimte herstelt de opdracht via 13, 14, 15 en 16 A. Na een automatische stop begint hij bij 6 A. Een handmatige pauze blijft 0 A, ook na storing of HA-herstart.

## Gecontroleerde invoering (later, met akkoord)

1. Controleer dat niet wordt geladen; bij voorkeur auto los. Noteer huidige strategie en limieten. Maak een verse herstelkopie van serverpackage, dashboard en uitsluitend de Manual-flow. Controleer verschillen met de lokale uitgangsversies; overschrijf geen tussentijdse wijzigingen.
2. Zet strategie Uit en bevestig actuele HEMS 0 A. Houd de bestaande fail-safe actief. Neem het HA-package over en voer de HA-configuratiecontrole uit. De uitbreiding bevat een nieuwe helper, templates, scripts en automatiseringen; alleen scripts herladen is niet voldoende. Kies vooraf het passende onderhoudsmoment voor eventuele HA-herstart en daarmee onderbreking van alle HA-integraties.
3. Controleer dat de nieuwe keuze op 0 A staat en de nieuwe entiteiten/scripts beschikbaar zijn. De oude HEMS-waarde (bijvoorbeeld 12 A) wordt niet geïmporteerd als keuze. Controleer de nieuwe templates en timers in de echte HA-runtime, inclusief gelijke sensorwaarden met een nieuw meettijdstip.
4. Werk alleen de Manual-tab in Node-RED bij, met behoud van de bestaande link-ID naar Master en de HA-serverconfiguratie. De flow roept nu `script.bender_manual_reconcile` aan, zonder eigen HEMS-teruglezing of wachtrij. Controleer vóór deploy dat geen andere tabs mee wijzigen. De oude flow kan met het nieuwe HA-package tijdelijk nog aanwezig zijn: zijn oude script zet geen gebruikerskeuze meer. Gebruik de nieuwe flow pas nadat het HA-script bestaat.
5. Neem het dashboard over. Controleer gekozen stroom versus actieve limiet en Pauze. Zet Manual aan: zonder nieuwe keuze moet de opdracht 0 A blijven. Test eerst met losgekoppelde auto, daarna onder toezicht met 6 A.
6. Test een tijdelijke beperking en terugkeer van ruimte via de daarvoor afgesproken testinstellingen. Bevestig direct verlagen, behoud van keuze, verse terugmelding en minstens 30 seconden stabiele ruimte vóór elke verhoging. Herstel testinstellingen. Controleer daarna expliciet Pauze tijdens het wachten en tijdens herstel: ook na meerdere minuten mag geen positieve opdracht volgen.
7. Test de bestaande DSMR/Node-RED-fail-safe gecontroleerd: keuze blijft bewaard, nulopdracht/terugmelding en push werken, vervolgens opbouw vanaf 6 A. Herhaal met handmatige pauze tijdens de storing: geen hervatting. Controleer bij een afgesproken HA-herstart dat een opgeslagen pauze behouden blijft. Deze offline tests zijn geen vervanging voor deze fysieke tests.
8. Pas na geslaagde observatie: haal de uiteindelijke serverbestanden/export terug, vergelijk met beide lokale repositories en commit/push de HA-bestanden naar HomeAssistant-config en dezelfde HA-bestanden plus Manual-flow/tests/documentatie naar de Bender-repo. Sluit de taak af met de testuitkomsten.

## Terugzetten

Eerst strategie Uit en HEMS 0 A bevestigen; niet terugzetten terwijl wordt geladen. Herstel de oude Manual-flow en het oude dashboard voordat het nieuwe HA-script verdwijnt; herstel daarna het complete oude package met bijbehorende oude herstelautomatisering. Controleer HA-configuratie en herlaad/herstart passend bij de helperwijzigingen. Verwijder of hergebruik geen nieuwe positieve keuze als oude HEMS-instelling. Controleer opnieuw Uit/0 A en de bestaande bewaking voordat normaal gebruik hervat.

## Lokale testgrenzen

De tests voeren de werkelijke YAML-expressies en scriptacties uit met gesimuleerde sensoren, klok en Modbus-schrijffouten. De 30-secondenvertraging wordt in het testmodel nagebootst. Dit bewijst niet het gedrag van HA's scheduler, de geïnstalleerde Node-RED-nodes, de fysieke auto of de timing van echte Modbus-rapporten. De controllerinstellingen Safe Current en timeout veranderen niet.

## HA-herstart met behoud van handmatige pauze — 30 oktober 2026

Uitgevoerd van 11:38 tot 11:42 CET. Vooraf geslaagde HA-configuratiecontrole en verse herstelkopieën. Auto aangesloten, strategie Uit, keuze/opdracht/HEMS 0 A, 0 W en nulstroom op alle fasen; bewaking gezond en controllerterugval 0 A na ingestelde timeout 60 s.

- Manual geselecteerd en expliciet Pauze gegeven. Om 11:38:56 vers bevestigd: Manual, keuze 0 A en fysieke nulmetingen. Vervolgens één normale HA-herstart via de HA-service uitgevoerd.
- De herstart is bevestigd door het gewijzigde HA-Pythonproces. Node-RED en DSMR zijn niet herstart. Modbusverbindingen sloten normaal en openden weer bij het starten.
- Om 11:39:33 waren Manual, keuze/opdracht/HEMS 0 A, verse nulmetingen en gezonde bewaking terug. Daarna 120 seconden geobserveerd bij beschikbare ruimte voor 16 A: geen automatische hervatting; alle gemeten fasestromen en het vermogen bleven nul.
- Afgesloten om 11:41:33 op Uit en HEMS 0 A. Onafhankelijke eindcontrole om 11:41:47 bevestigde ook 0 W/nulstroom, keuze 0 A, strategielimiet 16 A, huisaansluiting 17.250 W en marge 1.000 W. De herstelbewaker beëindigde zichzelf zonder ingreep.
- De HA-historie toont keuze en opdracht uitsluitend 0 A, strategie Uit → Manual → Uit en fail-safe actief steeds uit. Alle 1025 Node-RED-nodedefinities, HA-package en dashboard zijn ongewijzigd. Geen deployment, codewijziging of GitHub-push.

Beperkingen en waarnemingen: tijdens de HA-onderbreking was er geen continue fysieke telemetrie en geen afzonderlijke observatie door de gebruiker. De test bewijst herstel van de opgeslagen pauze en blijvende nulmetingen na herstart, niet een onafhankelijk gemeten ononderbroken nulstroom gedurende de hele HA-uitval. Een extra rechtstreekse Modbus-leesmonitor leek vóór de test de HA-uitlezing te verstoren (tijdelijk onbeschikbare fasestroomsensoren). Twee voorbereidende pogingen zijn daarom vóór enige HA-mutatie afgebroken. Die monitor is gestopt; daarna waren alle metingen stabiel en is de herstarttest uitgevoerd. Gebruik deze gelijktijdige uitleesmonitor niet opnieuw zonder onderzoek.

Tijdens starten is één aparte templatefout vastgelegd: `sensor.bender_ev_soc` krijgt `unknown` waar een getal wordt verwacht (11:39:41). Dit is een aandachtspunt voor de afhandeling van een onbekende auto-SOC; in deze test had het geen waargenomen effect op de Manual-pauze of gezonde bewaking. Niet aangepast binnen deze testopdracht.

Bewijs: werkmap `snapshots/2026-10-30T102922Z-ha-restart-pause-test`; serverherstelkopie met dezelfde naam onder `/home/ruald/bender-backups`. Daarmee is de afgesproken HA-herstarttest afgerond. Resterend vóór publiceren: definitieve server/laptopvergelijking, documentatiecontrole, beoordeling van de SOC-opstartmelding en daarna de afgesproken commits/push naar beide repositories.

## SOC-opstartmelding — lokale correctie op 30 oktober 2026

De percentagesensor retourneerde letterlijk `unknown` als het bronregister ontbrak of 65535 aangaf. Dit schendt HA's contract voor numerieke templates: de uitkomst moet een getal of `none` zijn. De eerdere integerconversie liet bovendien negatieve waarden door en kon een waarde net boven 100 afkappen tot een geldig lijkende 100.

Beide lokale packagekopieën zijn gericht aangepast: alleen eindige getallen binnen 0–100 blijven meetwaarden, alle andere invoer geeft `none`. De dashboardweergave blijft Onbekend voor ontbrekende SOC; een echte 0 blijft geldig. Entiteitsnamen, bronregister, polling, dashboard en laadbesturing zijn niet gewijzigd. Geen serververbinding of deployment uitgevoerd voor deze reparatie.

De nieuwe offline tests gebruiken de werkelijke YAML-template. Ze reproduceren de oude fout en controleren opstarten zonder bron, foutteksten, 65535, negatieve/te hoge/niet-eindige waarden, 0/100 en herstel zonder een oude waarde vast te houden. De tests zijn een lokale templatecontrole, geen HA-runtime-integratietest. Live logcontrole volgt pas bij een afzonderlijk goedgekeurde installatie.

Validatie: alle 82 Python-regressietests geslaagd, inclusief vier nieuwe SOC-tests met meerdere invoergevallen. Beide lokale packages zijn bytegelijk; een YAML-vergelijking met de herstelkopie bevestigt dat uitsluitend de SOC-state-template inhoudelijk is aangepast. `git diff --check` is voor beide repositories geslaagd. Bewijs: werkmap `snapshots/2026-10-30-soc-local-fix`.

## SOC-correctie — veilig geïnstalleerd op 30 oktober 2026

Voorcontrole om 17:02:59 CET: auto aangesloten zonder laden, verse nulmetingen, strategie Uit, HEMS 0 A en gezonde bewaking. Herstelkopie gemaakt onder `/home/ruald/bender-backups/2026-10-30T160259Z-soc-deploy`, inclusief package, dashboard en Node-RED-flowbestand. Het serverpackage was exact gelijk aan de lokaal beoordeelde oude versie. De eerste schrijfpoging via het hostaccount had onvoldoende bestandsrechten en veranderde het package niet; plaatsing is vervolgens via de HA-container uitgevoerd met behoud van eigenaar en rechten.

Uitsluitend het package met de SOC-correctie geplaatst; de ingebouwde HA-configuratiecontrole slaagde. Om 17:04:39 de template-integratie herladen. Geen HA-herstart, geen Node-RED-deployment en geen wijziging van dashboard of flows. De normale templateservice herlaadt alle templates, waardoor ook andere templates tijdelijk opnieuw initialiseren.

De bronwaarde bleef 65535, met verse polls om 17:04:43 en 17:05:43. De SOC-weergave bleef correct `unknown`, zonder nieuwe fout voor `sensor.bender_ev_soc`. Gedurende 125 seconden bleef Uit/HEMS 0 A en fysiek 0 W/nulstroom bevestigd. De bewaking was na herladen tijdelijk niet gezond en was om 17:05:24 weer gezond. Eindcontrole om 17:06:45: Uit, Manual-keuze/opdracht/HEMS 0 A, nulstroom en gezonde bewaking.

Andere waarnemingen tijdens herladen: `sensor.p1_meter_power` gaf tijdelijk tekst `unavailable` aan een numerieke templatevalidator; `sensor.luxtronik_id_web_temperatur_ta` gaf `unknown`. De Bender-watchdog meldde enkele overlappende triggers als `Already running`. Geen SOC-fout. Deze andere meldingen zijn vastgelegd, niet binnen deze opdracht aangepast.

Serverpackage en beide lokale kopieën hebben SHA-256 `1e8fa17d86ad44440ec81293222db764fe66e194e8a57227715b27396db89448`. Dashboard en Node-RED-flowbestand bleven gelijk aan de herstelkopie; het HA-Pythonproces is niet herstart. Bewijs in de werkmap: `snapshots/2026-10-30T160259Z-soc-deploy`. Deze controle betreft herladen en verse bronmetingen, geen nieuwe volledige HA-opstarttest. GitHub is niet bijgewerkt.
