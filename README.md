# Bender Laadpaal Integratie

Een complete Home Assistant & Node-RED integratie voor de **Bender CC613** laadpaal controller, inclusief slimme laadstrategieën en Load Balancing.

---

## 📖 Functionele Beschrijving

Dit project zorgt ervoor dat je jouw elektrische auto slim kunt opladen via een gebruiksvriendelijk dashboard in Home Assistant. Het systeem regelt automatisch de laadsnelheid op basis van jouw voorkeuren en beschermt tegelijkertijd je huisaansluiting.

### 🔋 Laadstrategieën
Je kunt op elk moment kiezen uit 5 standen:

1.  **Uit**: De laadpaal is vergrendeld. Er kan niet geladen worden.
2.  **Direct**: De auto begint meteen te laden op maximale snelheid (standaard 16A, tenzij begrensd door de Load Balancer). Handig als je haast hebt.
3.  **Manual**: Handbediening. Jij bepaalt zelf via het dashboard de laadstroom (6A, 10A of 16A).
4.  **ChargePV (Zonneladen)**: Het systeem kijkt naar je slimme meter (P1).
    *   Is er stroom over? Dan gaat dat naar de auto.
    *   Gaat de zon harder schijnen? De auto laadt sneller.
    *   Komt er een wolk? De auto laadt langzamer of pauzeert.
    *   *Doel:* 100% gratis rijden op zonne-energie.
5.  **Dynamic (Slim Laden)**:
    *   Jij geeft aan hoe laat je weg moet en hoeveel energie je nodig hebt.
    *   Het systeem berekent wanneer de stroom het goedkoopst is (op basis van dynamische tarieven).
    *   De auto laadt precies genoeg op de goedkoopste momenten om klaar te zijn voor vertrek.

### ⚖️ Load Balancer (Actieve Beveiliging)
Dit systeem beschermt je meterkast (zekeringen) tegen overbelasting. Dit is vooral kritiek als je een warmtepomp, inductieplaat of wasdroger samen met de auto gebruikt.

*   **Per Fase Bescherming:** Het systeem meet continu (elke 10 seconden) het verbruik op Fase 1, 2 en 3 van je huis via de slimme meter.
*   **Berekening:** `Beschikbaar = Zekering (25A) - Veiligheidsmarge - Huidig Huisverbruik`.
*   **Ingrijpen:**
    *   De laadpaal past zich automatisch aan naar de fase waar de *minste* ruimte is.
    *   Als de beschikbare ruimte onder de **6 Ampère** zakt, stopt het laden tijdelijk (Pauze). Dit is een harde veiligheidsgrens voor elektrische auto's.
    *   Zodra er weer ruimte is, start het laden vanzelf weer.

### 📱 Het Dashboard
Het dashboard is ingericht in drie tabbladen:
1.  **Laadpaal:** Voor dagelijks gebruik. Strategie kiezen, live status en verbruik zien.
2.  **Instellingen:** Voor configuratie. Hier stel je o.a. de Load Balancer marge in en de capaciteit van je huisaansluiting.
3.  **Debugging:** Voor probleemoplossing. Toont actieve foutmeldingen, historische events en raw Modbus data.

### 🔍 Uitgebreide Monitoring
Het systeem biedt gedetailleerde informatie over je laadsessie:
*   **Voertuig Status (Control Pilot):** Toont de IEC 61851-1 state (A t/m E) - van "niet aangesloten" tot "laden actief".
*   **EV Batterij SOC:** State of Charge van je auto (indien ondersteund door het voertuig).
*   **Sessie Energie & Duur:** Hoeveel kWh er geladen is en hoe lang de huidige/laatste sessie duurt.
*   **Foutmeldingen:** Automatische vertaling van Bender error codes naar leesbare Nederlandse meldingen.
*   **Event Log:** Historische events zoals reboots, autorisatiepogingen en firmware updates.

---

## 🛠️ Technische Installatie Handleiding

### Benodigdheden
*   **Home Assistant** (met `packages` ondersteuning ingeschakeld in `configuration.yaml`).
*   **Node-RED** (als addon binnen HA of los).
*   **Slimme Meter Integratie** in HA (bijv. DSMR of P1 Monitor) met sensoren voor voltage en stroom per fase.
*   **Bender CC613** controller verbonden via Modbus TCP.

### Stap 1: Home Assistant Package Installeren
1.  Kopieer het bestand `HomeAssistant/packages/bender_chargepoint_integration.yaml` naar de `packages/` map van je Home Assistant installatie.
2.  Open het bestand en controleer de **Modbus IP** instellingen bovenaan (regel 4):
    ```yaml
    modbus:
      - name: modbus_hub
        type: tcp
        host: 192.168.x.x  # <-- PAS DIT AAN NAAR HET IP VAN JOUW BENDER
        port: 502
    ```
3.  Controleer of de **DSMR sensoren** in het bestand overeenkomen met de namen van jouw slimme meter entiteiten:
    *   Per-fase sensoren: `sensor.dsmr_reading_phase_currently_delivered_l1` (en L2, L3)
    *   Totaal vermogen: `sensor.p1_meter_power` (voor ChargePV strategie)
4.  Herstart Home Assistant.

### Stap 2: Dashboard Configureren
1.  Maak een nieuw dashboard aan in Home Assistant of voeg een nieuwe view toe aan je bestaande dashboard.
2.  Installeer de HACS frontend integratie **Card-mod** (nodig voor de gekleurde knoppen).
3.  Kopieer de inhoud van `HomeAssistant/dashboards/bender_chargepoint.yaml`.
4.  Plak dit in de Raw Configuration Editor van je dashboard.

### Stap 3: Node-RED Flows Importeren
De logica van de strategieën draait in Node-RED.

1.  Open Node-RED.
2.  Importeer de volgende 5 JSON bestanden uit de `NodeRed/` map in deze volgorde:
    *   `bender_strategy_master.json` (De coördinator).
    *   `bender_strategy_manual.json`
    *   `bender_strategy_direct.json`
    *   `bender_strategy_chargepv.json`
    *   `bender_strategy_dynamic.json`
3.  Controleer de **Home Assistant Server** node in elke flow. Zorg dat deze verbonden is met jouw HA instantie.
4.  Klik op **Deploy**.

### Stap 4: Eerste Ingebruikname
1.  Ga naar het **Instellingen** tabblad op je nieuwe dashboard.
2.  Zet de **Load Balancer** op "Actief" (Aan).
3.  Stel de **Huisaansluiting Capaciteit** in (standaard 17250W voor 3x25A).
4.  Stel een **Veiligheidsmarge** in (bijv. 1000W).
5.  Ga naar het **Laadpaal** tabblad en test de strategie "Manual" om te kijken of de communicatie met de Bender werkt.

---
*Laatst bijgewerkt: Februari 2026*
