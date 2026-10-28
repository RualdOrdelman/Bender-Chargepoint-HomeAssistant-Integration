# Bender Chargepoint Home Assistant-integratie

Home Assistant- en Node-RED-integratie voor een laadpaal met een **Bender CC613-controller** via Modbus TCP. Het project bevat uitlezing en bediening van de laadpaal, vijf laadstrategieën, driefasen-loadbalancing, bewaking van DSMR en Node-RED, een harde fail-safe en een Home Assistant-dashboard.

> [!IMPORTANT]
> Deze software is een aanvullende besturings- en bewakingslaag. Zij vervangt geen correct gedimensioneerde installatie, aardlek- en overstroombeveiliging of andere elektrische beveiligingen.

## Inhoud van de repository

```text
HomeAssistant/
├── dashboards/
│   └── bender_chargepoint.yaml
└── packages/
    ├── bender_chargepoint_integration.yaml
    └── bender_chargepoint_integration_private.yaml.example

NodeRed/
├── bender_strategy_master.json
├── bender_strategy_direct.json
├── bender_strategy_manual.json
├── bender_strategy_chargepv.json
└── bender_strategy_dynamic.json
```

- `bender_chargepoint_integration.yaml` bevat de Modbus-sensoren, helpers, templates, scripts, loadbalancer, watchdogs en herstelautomatisering.
- `bender_chargepoint.yaml` is een volledig dashboard met de tabbladen **Laadpaal**, **Instellingen** en **Debugging**.
- De vijf Node-RED-bestanden bevatten de strategiecoördinator en de afzonderlijke laadstrategieën.
- Het private voorbeeldbestand is bedoeld voor RFID-registerwaarden. Het echte private bestand hoort niet in Git.

## Werking op hoofdlijnen

```text
DSMR/P1 ──> Home Assistant ──> loadbalancer en gezondheidscontrole
                    │
                    ├──> Node-RED ──> gekozen laadstrategie
                    │                     │
                    └<── heartbeat ───────┘
                    │
                    └──> beveiligde HA-scripts ──> Modbus TCP ──> Bender CC613
```

Home Assistant is de centrale veiligheidslaag. Node-RED bepaalt de gewenste strategie, maar schrijft niet rechtstreeks naar Modbus. Alle laadopdrachten lopen via Home Assistant-scripts, die de loadbalancer en actieve fail-safe toepassen.

## Laadstrategieën

| Strategie | Gedrag |
| --- | --- |
| **Uit** | Schrijft een HEMS-limiet van `0 A`. Dit pauzeert laden; het is geen fysieke vergrendeling van de laadpaal. |
| **Direct** | Start of hervat na bevestigde stilstand en 30 seconden stabiele laadruimte; gebruikt daarna de ingestelde maximale laadstroom, begrensd op `16 A` en de ingeschakelde loadbalancer. |
| **Manual** | Behoudt de actuele HEMS-limiet als handmatige instelling. Als deze hoger is dan de beschikbare loadbalancerruimte, wordt hij veilig begrensd. |
| **ChargePV** | Reageert op `sensor.p1_meter_power`, maximaal eenmaal per 10 seconden. Negatief P1-vermogen geldt als teruglevering. De flow rekent het overschot om naar een driefasen-laadstroom en laadt alleen vanaf minimaal `6 A` én het ingestelde minimale PV-overschot. |
| **Dynamic** | Leest de vertrekdatum, benodigde kWh, maximale stroom en het `forecast`-attribuut van de Zonneplan-prijssensor. De goedkoopste benodigde uren vóór vertrek worden geselecteerd. Als de uiterste starttijd is bereikt, wordt laden als deadline-fallback gestart. De planning wordt bij activering en vervolgens ieder heel uur opnieuw berekend. |

De instelling `input_number.bender_strategy_max_current` bepaalt de bovengrens voor Direct, ChargePV en Dynamic. De implementatie gaat uit van driefasenladen en een bovengrens van `16 A` per fase.

### Manual na een fail-safe

Een harde fail-safe schrijft de HEMS-limiet naar `0 A`. Voor Manual wordt daarom de eerdere positieve HEMS-limiet opgeslagen. Na herstel:

1. moeten DSMR en Node-RED eerst 30 seconden stabiel gezond zijn;
2. wordt alleen hersteld als minimaal `6 A` veilig beschikbaar is;
3. wordt de oude waarde door de actuele loadbalancer begrensd;
4. volgt zo nodig iedere 10 seconden een nieuwe poging;
5. stopt de herstelpoging zodra een positieve HEMS-waarde is bevestigd of de gebruiker strategie/fail-safe-modus wijzigt.

Hierdoor kan Manual na een tijdelijke storing veilig hervatten zonder een latere handmatige keuze te overschrijven.

## Loadbalancing

De loadbalancer berekent per fase hoeveel stroom beschikbaar is. Daarvoor combineert hij:

- afname en teruglevering per DSMR-fase;
- de actuele stroom van de laadpaal per fase;
- de ingestelde maximale capaciteit van de huisaansluiting;
- een instelbare veiligheidsmarge;
- de werkelijke fasespanning; onbruikbare spanningen geven geen toestemming om te laden.

De laagste beschikbare waarde van L1, L2 en L3 is bepalend. De uitkomst wordt op maximaal `16 A` begrensd. Minder dan `6 A` beschikbaar betekent een laadopdracht van `0 A`, omdat een EV normaal niet onder `6 A` kan laden.

De coördinator in Node-RED verwerkt verlagingen direct. Voor overige loadbalancerupdates bewaart hij maximaal één laatste bericht en verwerkt dit uiterlijk na 5 seconden. Er wordt geen FIFO-wachtrij opgebouwd. De tijdelijke timer gebruikt de standaard contextopslag in geheugen van Node-RED; configureer hiervoor geen opslag naar schijf. Home Assistant bewaakt daarnaast iedere laadopdracht opnieuw. Uitschakelen van de softwarematige loadbalancer schakelt de elektrische beveiligingen van de installatie vanzelfsprekend niet uit.

Bij ingeschakelde loadbalancing blokkeert de centrale HEMS-schrijver een ongeldige laadruimtesensor op **0 A**, ook bij Manual. Hij controleert de onderliggende DSMR-waarden opnieuw vóór de opdracht, zodat hij niet afhankelijk is van een nog niet bijgewerkte gezondheidsstatus. De loadbalancersensor zelf geeft bij onbruikbare brongegevens eveneens 0 A. De bestaande watchdog gebruikt de foutreden voor de fail-safe en melding.

Het spanningsbereik **180–260 V** is een bewust gekozen controle op bruikbare meetgegevens voor deze 230V-installatie; het vervangt geen elektrische netbeveiliging. De vijf seconden kloktolerantie is alleen bedoeld voor een kleine afwijking. De controle bewijst nog niet dat alle losse MQTT-velden uit hetzelfde telegram komen. Een gezonde heartbeat bewijst evenmin dat iedere HEMS-opdracht bevestigd is; daarvoor is er een afzonderlijke HEMS-terugmeldingsbewaking in Home Assistant.

## Gezondheidsbewaking en harde fail-safe

### Bewaakte bronnen

Home Assistant controleert iedere 5 seconden:

- **DSMR-gezondheid:** `sensor.dsmr_reading_timestamp` mag maximaal 30 seconden oud zijn en maximaal 5 seconden vooruitlopen. Alle vereiste DSMR/P1-entiteiten moeten eindige getallen zijn. Fasespanningen moeten binnen 180–260 V liggen; afzonderlijke afname en teruglevering per fase mogen niet negatief zijn. Nulverbruik en negatieve totale P1-nettovermogens zijn wel geldig;
- **Node-RED-gezondheid:** de Master-flow schrijft iedere 10 seconden een heartbeat naar Home Assistant; deze mag niet ouder zijn dan 30 seconden;
- **HEMS-uitvoering:** de bewaakte opdracht moet exact terugkomen in een nieuwe Modbus-rapportage. De terugmelding mag maximaal 45 seconden oud zijn. Een gewijzigde opdracht krijgt maximaal 45 seconden bevestigingstijd, gecontroleerd iedere 5 seconden.

De actuele toestand is zichtbaar via onder andere:

- `binary_sensor.bender_dsmr_data_healthy`;
- `binary_sensor.bender_nodered_heartbeat_healthy`;
- `binary_sensor.bender_hems_control_healthy`;
- `binary_sensor.bender_hems_command_confirmed`;
- `sensor.bender_hems_command_status`;
- `sensor.bender_requested_current`;
- `binary_sensor.bender_charging_control_healthy`;
- `sensor.bender_dsmr_data_leeftijd`;
- `sensor.bender_nodered_heartbeat_age`;
- `input_text.bender_failsafe_reason`.

### Fail-safe-modi

| Modus | Gedrag |
| --- | --- |
| **Uit** | Watchdog grijpt niet in en wist een geobserveerde storingsstatus. Alleen gebruiken voor bewust onderhoud of diagnose. |
| **Monitoren** | Detecteert en logt storingen, maar verandert de HEMS-limiet niet. Geschikt voor ingebruikname en gepland onderhoud. |
| **Actief** | Detecteert de storing, blokkeert positieve laadopdrachten en verstuurt asynchroon een pauzeopdracht van `0 A` naar de Bender. Zolang de stop niet bevestigd is, wordt `0 A` opnieuw geprobeerd, ook bij ontbrekende terugmelding; een lopende schrijfopdracht wordt daarbij niet telkens opnieuw afgebroken. |

Na herstel start een stabilisatietimer van 30 seconden. Na actief ingrijpen moet eerst een verse terugmelding van **0 A** zijn ontvangen. Alleen als DSMR, Node-RED en HEMS gedurende die periode gezond blijven, wordt de fail-safe opgeheven en de actieve strategie opnieuw beoordeeld. Een terugkerende storing onderbreekt de timer.

### Onafhankelijke HEMS-opdrachtbewaking

De centrale schrijver bewaart de begrensde opdracht in `input_number.bender_requested_current` **vóór** de Modbus-aanroep. Een geslaagde serviceaanroep telt nog niet als bevestiging: `sensor.bender_hems_limit` moet exact dezelfde waarde terugmelden, met `last_reported` op of na de opdracht. Ook een ongewijzigde meetwaarde kan daardoor een nieuwe rapportage zijn. HEMS wordt ongeveer iedere 30 seconden uitgelezen; tijdens de normale wachttijd blijft de besturing gezond zolang de bestaande terugmelding actueel is.

`input_number.bender_hems_unconfirmed_since` bewaart het begin van de oudste nog onbevestigde opdracht. Herhaalde pogingen en tussentijdse wijzigingen verlengen die termijn niet. Na bevestiging wordt de interne tijdmarkering gewist. Deze twee interne helpers zijn geen gebruikersbediening. `input_number.bender_commanded_current` blijft apart bestaan voor de veilige verrekening van laadstroom in de loadbalancer.

In fail-safe-modus **Actief** controleert `Bender Onafhankelijke HEMS Bewaking` iedere 5 seconden ook of de gevraagde, geschreven of teruggemelde limiet boven de veilige grens ligt. De controle kan zelfstandig verlagen of stoppen wanneer Node-RED een verlaging mist. Ze verhoogt nooit zelfstandig de opdracht. Een onbevestigde nulopdracht wordt vanaf 10 seconden opnieuw geprobeerd, zolang de schrijver niet al loopt. De bestaande watchdog verwerkt een te oude of onbevestigde HEMS-terugmelding als storing en gebruikt hiervoor dezelfde push- en herstelprocedure. Een mislukte push mag de verdere afhandeling niet afbreken.

Op **Instellingen → Data Actualiteit** zijn de opdrachtstatus, gevraagde stroom, teruggemelde stroom en gezondheid zichtbaar. Mogelijke statussen zijn `Bevestigd`, `Wacht op terugmelding`, `Geen actuele terugmelding` en `Opdracht niet bevestigd`.

Dit bevestigt het HEMS-register; het bewijst op zichzelf geen fysieke uitschakeling van de contactor. Bij verlies van de volledige Modbus-verbinding kan HA geen stop garanderen. De bestaande controllerinstellingen voor communicatietimeout en Safe Current zijn in deze fase niet veranderd of fysiek als netwerkuitvaltest gevalideerd.

### Pushberichten

Met `input_boolean.bender_failsafe_notifications_enabled` kunnen meldingen bij ingrijpen en herstel worden aangezet. In het package staat momenteel een installatiegebonden notify-entiteit:

```yaml
notify.iphone_17_ruald
```

Vervang deze op beide plaatsen in `bender_chargepoint_integration.yaml` door een notify-entiteit die in jouw Home Assistant bestaat. De fail-safe blijft zonder pushdienst functioneren; alleen de melding kan dan mislukken.

## Vereisten en aannames

- Home Assistant met ondersteuning voor [packages](#1-home-assistant-package-installeren).
- Node-RED met `node-red-contrib-home-assistant-websocket` en een werkende verbinding naar dezelfde Home Assistant-instantie.
- Een Bender CC613 die via Modbus TCP bereikbaar is op poort `502`, unit/slave-id `1`.
- Een driefasenhuisaansluiting en driefasenlaadregeling.
- Een DSMR/P1-integratie die onderstaande entiteiten actueel houdt.
- Voor Dynamic: een Zonneplan-prijssensor met een bruikbaar `forecast`-attribuut.
- Voor de kleuraccenten in het meegeleverde dashboard: HACS-integratie **card-mod**.

### Verplichte DSMR/P1-entiteiten

Deze namen worden letterlijk door de huidige templates en flows gebruikt:

```text
sensor.dsmr_reading_timestamp
sensor.dsmr_reading_phase_currently_delivered_l1
sensor.dsmr_reading_phase_currently_delivered_l2
sensor.dsmr_reading_phase_currently_delivered_l3
sensor.dsmr_reading_phase_currently_returned_l1
sensor.dsmr_reading_phase_currently_returned_l2
sensor.dsmr_reading_phase_currently_returned_l3
sensor.dsmr_reading_phase_voltage_l1
sensor.dsmr_reading_phase_voltage_l2
sensor.dsmr_reading_phase_voltage_l3
sensor.p1_meter_power
```

`sensor.dsmr_reading_timestamp` moet de tijd van het laatste ontvangen P1-telegram bevatten, niet alleen een waarde die verandert wanneer verbruik of teruglevering verandert. Pas de entity-id's in package, dashboard en Node-RED-flows consequent aan als jouw integratie andere namen gebruikt.

### Dynamic-prijssensor

De huidige flow verwacht:

```text
sensor.zonneplan_current_electricity_tariff
```

Het attribuut `forecast` moet een lijst met toekomstige uren bevatten. Per item ondersteunt de flow `datetime` of `start_time` en `electricity_price` of `price`. Zonder bruikbare forecast valt de planning terug op de berekende uiterste starttijd.

## Installatie

### 1. Home Assistant-package installeren

Zorg dat packages in `configuration.yaml` zijn ingeschakeld. Voeg dit alleen toe als nog geen `homeassistant:`-sectie bestaat; voeg anders alleen de regel `packages:` aan de bestaande sectie toe.

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Kopieer vervolgens:

```text
HomeAssistant/packages/bender_chargepoint_integration.yaml
```

naar de packages-map van Home Assistant.

Controleer vóór ingebruikname in het package:

1. het IP-adres onder `modbus:` — de repository bevat momenteel `192.168.1.194`;
2. poort `502` en slave-id `1`;
3. alle DSMR/P1 entity-id's;
4. de notify-entiteit voor fail-safeberichten;
5. de maximale huisaansluiting, marge en laadstroom via de helpers in het dashboard;
6. de RFID-herkenning en scripts als sessiestop via RFID wordt gebruikt.

Voer daarna eerst de Home Assistant-configuratiecontrole uit. Herstart Home Assistant pas als die controle zonder fouten is afgerond.

### 2. Optionele private RFID-scripts

Kopieer:

```text
bender_chargepoint_integration_private.yaml.example
```

naar:

```text
bender_chargepoint_integration_private.yaml
```

Vul daarin de eigen RFID-registerwaarden in. Het publieke package roept momenteel de scripts `script.bender_rfid_ruald` en `script.bender_rfid_ellen` aan en herkent dezelfde twee namen in `sensor.bender_session_owner`. Zorg dat scriptnamen, herkenning en gebruikersnamen onderling overeenkomen als je ze aanpast.

Het echte private bestand wordt door `.gitignore` uitgesloten. Controleer vóór iedere commit dat RFID-waarden, wachtwoorden, tokens en andere secrets niet zijn toegevoegd.

### 3. Dashboard installeren

1. Installeer **card-mod** via HACS als je de meegeleverde kleuraccenten wilt gebruiken.
2. Maak in Home Assistant een nieuw dashboard in YAML/raw-modus.
3. Kopieer de volledige inhoud van `HomeAssistant/dashboards/bender_chargepoint.yaml` naar de raw-configuratie.
4. Controleer of alle entiteiten beschikbaar zijn.

Het dashboard bevat:

- **Laadpaal:** strategie, status, fail-safe, sessie, vermogen en strategiespecifieke bediening;
- **Instellingen:** maximale laadstroom, PV-drempel, loadbalancer, huisaansluiting, marge, fail-safe-modus en pushmeldingen;
- **Debugging:** ruwe Benderwaarden, DSMR/Node-RED-gezondheid, HEMS-logcontext, foutcodes, gebeurtenissen en historie.

### 4. Node-RED-flows importeren

Importeer en deploy alle vijf bestanden uit `NodeRed/`:

1. `bender_strategy_master.json`;
2. `bender_strategy_direct.json`;
3. `bender_strategy_manual.json`;
4. `bender_strategy_chargepv.json`;
5. `bender_strategy_dynamic.json`.

Let hierbij op het volgende:

- Koppel alle Home Assistant-nodes aan jouw Home Assistant-serverconfiguratie; de export bevat geen overdraagbare inloggegevens.
- Importeer ook Direct en ChargePV: de Master-flow verwijst via link-nodes naar alle vier strategiespecifieke flows.
- Deploy de Master-flow zodat de heartbeat iedere 10 seconden wordt bijgewerkt.
- Los eventuele ontbrekende of dubbele link-nodeverbindingen op voordat je een strategie activeert.

### 5. Eerste ingebruikname

Gebruik voor de eerste controle een moment waarop de auto niet actief laadt.

1. Zet **Fail-safe modus** eerst op `Monitoren`.
2. Controleer op het tabblad Debugging dat Modbus-sensoren waarden ontvangen.
3. Controleer dat DSMR, Node-RED en HEMS gezond worden weergegeven.
4. Stel de capaciteit van de huisaansluiting in. De standaardwaarde `17.250 W` past bij de gebruikte 3 × 25 A-benadering.
5. Stel een passende loadbalancermarge in; standaard is `1.000 W`.
6. Schakel de loadbalancer in.
7. Test `Uit` en daarna met toezicht een lage Manual-instelling.
8. Test de overige strategieën pas nadat de basisbediening en begrenzing kloppen.
9. Zet de fail-safe na de gecontroleerde test op `Actief`.

## Direct: veilig stoppen en hervatten

Bij een stop zet HA `input_number.bender_commanded_current` vóór de Modbus-opdracht op nul. De loadbalancer telt dan geen oude laadstroom meer terug als beschikbare ruimte. Tijdens laden wordt deze verrekening begrensd op de laatst gestuurde stroom. Dit voorkomt dat een snelle P1-update en een nog oude Modbus-meting na het stoppen tijdelijk fictieve laadruimte opleveren.

Direct hervat pas als:

- HEMS 0 A, alle fasestromen maximaal 200 mA en laadvermogen maximaal 50 W rapporteren;
- deze rapportages na de stop zijn ontvangen en nog actueel zijn (stroom/vermogen maximaal 25 seconden oud, HEMS maximaal 45 seconden);
- daarna gedurende 30 seconden onafgebroken minimaal 6 A beschikbaar is en de besturing gezond blijft.

De controles staan in `binary_sensor.bender_charger_stopped_fresh` en `binary_sensor.bender_direct_resume_ready`. Een periodieke Direct-controle iedere 5 seconden zorgt ook bij een gelijkblijvende loadbalancerwaarde voor hervatten. De eerste start van Direct gebruikt dezelfde controle. Een HA-herstart begint conservatief met laatst gevraagde stroom 0 A. De versheidscontrole gebruikt `State.last_reported` (gevalideerd op HA 2026.10.4), zodat ook ongewijzigde nulmetingen kunnen bevestigen dat de controller wordt uitgelezen.

De centrale HEMS-schrijver controleert de Direct-voorwaarden opnieuw, begrenst opdrachten op 0 of 6–16 A en slaat al bevestigde opdrachten over. Een nieuwe stop kan een oudere scriptuitvoering onderbreken. Manual behoudt zijn expliciete bediening; de wachttijd geldt voor Direct. ChargePV en Dynamic zijn hiermee niet functioneel gevalideerd.

## Lokale regressietests

De Master-trigger levert de sensorwaarde als `msg.payload`. De tests voeren de geëxporteerde Master-functie uit met een gesimuleerde klok en toetsen de echte HA-templates en volgorde van scriptacties. Ze openen geen verbinding met HA of de laadpaal.

```sh
node --test tests/bender-master-loadbalancer.test.cjs
# Python-omgeving met PyYAML en Jinja2:
python -m unittest discover -s tests -p 'test_*.py'
```

De tests dekken berichtpieken, onmiddellijke verlagingen, annuleren van een wachtende verhoging, ontbrekende/ongeldige waarden, oude nulmetingen, fouten bij schrijven en de gemeten ongewenste 0 → 6 A-overgang. De opdrachtbewaking heeft daarnaast regressietests voor exacte en verse terugmelding, de 45-secondenlimiet, behoud van de oudste deadline, herstel na bevestigde nul en zelfstandig verlagen zonder verhogingen. Ze vervangen geen fysieke laadtest of controle van HA's timers en de Modbus-terugmelding.

## Gecontroleerd testen van de fail-safe

Test een storing alleen als de auto niet laadt of als een onderbreking aantoonbaar veilig is.

### Node-RED-storing

1. Noteer de HEMS-limiet en actieve strategie.
2. Onderbreek Node-RED gecontroleerd.
3. Binnen ongeveer 30 seconden moet de Node-RED-heartbeat ongezond worden.
4. In modus `Actief` moet de fail-safe actief worden en de HEMS-limiet naar `0 A` gaan.
5. Als pushberichten zijn ingeschakeld, moet een melding met de reden volgen.
6. Start Node-RED weer en wacht minimaal 30 seconden stabiele gezondheid.
7. Controleer de herstelmelding en het opnieuw beoordelen van de strategie.

### DSMR-storing

Gebruik een gecontroleerde onderbreking van de DSMR/P1-aanvoer. De fail-safe moet reageren op een oude `sensor.dsmr_reading_timestamp` of op een ontbrekende vereiste sensor. Controleer na herstel opnieuw de stabilisatietijd en strategie.

> [!WARNING]
> Gebruik geen tweede rechtstreekse Modbus-client als test terwijl Home Assistant met de Bender verbonden is. Sommige controllers accepteren maar een beperkt aantal gelijktijdige verbindingen; zo'n test kan juist de actieve HA-verbinding verstoren.

Zet bij gepland onderhoud aan Home Assistant, Node-RED of DSMR de fail-safe zo nodig tijdelijk op `Monitoren`. Herstel `Actief` zodra beide gezondheidsindicatoren stabiel zijn.

## Belangrijkste instellingen

| Entiteit | Betekenis | Standaard/bereik |
| --- | --- | --- |
| `input_select.bender_charging_strategy` | Actieve laadstrategie | Uit, Direct, Manual, ChargePV, Dynamic |
| `input_number.bender_strategy_max_current` | Maximale strategie-laadstroom per fase | 6–16 A; standaard 16 A |
| `input_number.bender_strategy_pv_min_surplus` | Minimaal overschot voor ChargePV | 1.000–11.000 W; standaard 4.140 W |
| `input_boolean.bender_loadbalancer_enabled` | Softwarematige loadbalancer aan/uit | instelbaar |
| `input_number.bender_house_max_power` | Totale capaciteit voor de loadbalancerberekening | 5.000–25.000 W; standaard 17.250 W |
| `input_number.bender_loadbalancer_margin` | Gereserveerde veiligheidsmarge | 0–5.000 W; standaard 1.000 W |
| `input_select.bender_failsafe_mode` | Gedrag van de watchdog | Monitoren, Uit, Actief |
| `input_boolean.bender_failsafe_notifications_enabled` | Push bij fail-safe en herstel | instelbaar |
| `input_datetime.bender_strategy_departure_time` | Vertrekmoment voor Dynamic | door gebruiker |
| `input_number.bender_strategy_required_kwh` | Gewenste energie voor Dynamic | 0–100 kWh |
| `input_datetime.bender_manual_stop_time` | Geplande RFID-sessiestop in Manual | door gebruiker |

## Bendergegevens en bediening

Het package leest onder meer:

- chargepoint- en voertuigstatus;
- veilige stroom en HEMS-limiet;
- spanning, stroom en vermogen per fase;
- totaalvermogen en totale energie;
- sessie-energie en sessieduur;
- EV State of Charge, indien beschikbaar;
- actieve RFID-tag/sessie-eigenaar;
- foutcode en eventregister.

De vertaalde statussen, fouten en gebeurtenissen zijn in het dashboard zichtbaar. Schrijven gebeurt naar de registers voor Safe Current, HEMS-limiet en — optioneel — RFID-simulatie.

## Probleemoplossing

### De HEMS-limiet blijft op 0 A

Controleer achtereenvolgens:

1. `input_boolean.bender_failsafe_active`;
2. `input_text.bender_failsafe_reason`;
3. de DSMR-, Node-RED- en HEMS-gezondheid en de HEMS-opdrachtstatus;
4. de beschikbare loadbalancerstroom;
5. of minstens `6 A` beschikbaar is;
6. bij Manual: `input_boolean.bender_failsafe_manual_restore_pending`.

Een actieve fail-safe blokkeert iedere positieve opdracht via de meegeleverde scripts. Manual wacht na herstel bewust totdat minimaal `6 A` veilig beschikbaar is.

### DSMR wordt ongezond weergegeven

- Controleer of `sensor.dsmr_reading_timestamp` bij ieder telegram wordt vernieuwd.
- Controleer of alle elf vereiste DSMR/P1-entiteiten bestaan en numerieke waarden leveren.
- Controleer een eventuele MQTT-wachtrij of vertraging tussen DSMR Reader en Home Assistant.
- De actuele leeftijd en lijst met ongeldige entiteiten staan als status/attributen in Home Assistant.

### Node-RED wordt ongezond weergegeven

- Controleer of de Master-flow actief en gedeployed is.
- Controleer de Home Assistant-serververbinding in Node-RED.
- Controleer of `input_datetime.bender_nodered_heartbeat` iedere 10 seconden verandert.
- Controleer of de Master-link-nodes met alle strategyflows verbonden zijn.

### ChargePV start niet

- Teruglevering moet in `sensor.p1_meter_power` negatief zijn.
- Het absolute overschot moet minimaal de ingestelde PV-drempel bedragen.
- De berekende stroom moet minimaal `6 A` per fase zijn.
- De maximale laadstroom, fasespanningen, loadbalancer en fail-safe kunnen de uiteindelijke opdracht verder begrenzen.

### Dynamic plant niet zoals verwacht

- Controleer vertrekdatum en benodigde kWh.
- Bekijk het `forecast`-attribuut van `sensor.zonneplan_current_electricity_tariff`.
- Controleer of de forecast toekomstige uuritems met ondersteunde datum- en prijsvelden bevat.
- De berekening rondt de benodigde laadduur naar boven af op hele uren en gebruikt `3 × 230 V × maximale stroom` als laadvermogen.

### Modbus-sensoren zijn `unavailable`

- Controleer IP-adres, poort, unit-id en netwerkroute.
- Controleer of een andere Modbus-client de verbinding bezet houdt.
- Controleer de Home Assistant-logboeken voordat je waarden naar registers schrijft.

## Beveiliging en beheer

- Bewaar RFID-registerwaarden uitsluitend in het genegeerde private package.
- Exporteer geen Node-RED-credentials, API-tokens of Home Assistant access tokens naar Git.
- Beveilig de Node-RED-editor en beperk netwerktoegang tot Modbus TCP.
- Maak vóór wijzigingen een export/back-up van de actieve Home Assistant- en Node-RED-configuratie.
- Houd lokaal, de actieve server en GitHub aantoonbaar gelijk; vergelijk bestanden inhoudelijk en niet alleen op wijzigingsdatum.
- Zet wijzigingen gefaseerd live: eerst lokaal valideren, dan gecontroleerd op de server testen en pas daarna naar GitHub pushen.

## Bekende installatiegebonden onderdelen

De repository weerspiegelt de huidige installatie en bevat daarom waarden die bij hergebruik aangepast moeten worden:

- Bender-IP-adres `192.168.1.194`;
- notify-entiteit `notify.iphone_17_ruald`;
- RFID-gebruikers, tagherkenning en private scriptnamen;
- DSMR/P1 entity-id's;
- Zonneplan-prijssensor;
- aannames van driefasenladen, maximaal `16 A` en minimaal `6 A`.

Controleer deze punten opnieuw na het wijzigen van integraties, entity-id's, de netaansluiting of de laadpaalconfiguratie.

---

Laatst inhoudelijk gecontroleerd tegen de Home Assistant-package-, dashboard- en Node-RED-code: **september 2026**. De Master-, Direct-, meetgegevens- en HEMS-veiligheidslaag en bijbehorende documentatie zijn bijgewerkt op **28 oktober 2026**.
