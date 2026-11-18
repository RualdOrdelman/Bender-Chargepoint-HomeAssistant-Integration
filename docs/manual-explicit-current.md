# Manual: een expliciete stroomkeuze direct toepassen

Status: lokaal voorbereid op 2 november 2026; op 18 november 2026 samen met de loadbalancercorrectie geïnstalleerd. HA-configuratiecontrole en herstartcontrole geslaagd; Uit/0 A bevestigd. Fysieke 6/10/16 A-keuzes en begrenzing/herstel/pauze zijn op 18 november 2026 getest; zie de resultaten in [loadbalancer-feedback.md](loadbalancer-feedback.md).

## Aanleiding en waarneming

Om circa 20:32 CET stond de bewaarde keuze op 16 A en meldde de loadbalancer 16 A ruimte, terwijl de schrijver pas 8 A opdroeg. De vorige HEMS-terugmelding was 7 A. De server gebruikte bytegelijk het laatst gepubliceerde package. De oorzaak was de Manual-opbouwgrens: ook een nieuwe gebruikerskeuze moest eerst op 6 A beginnen en vervolgens per 1 A verhogen na verse terugmelding en een aaneengesloten wachttijd van 30 seconden. Rond 20:35 was HEMS 10 A en werd circa 5,1 kW gemeten; de auto werd toen als ladend herkend.

## Lokale wijziging

`bender_manual_set_current` bewaart de keuze en roept de centrale schrijver rechtstreeks aan met een uitsluitend voor die aanroep geldende `manual_user_request: true`. De automatische regelaar krijgt deze vlag niet. Er wordt geen nieuwe helper of hersteltoestemming opgeslagen.

Bij een expliciete keuze mag de schrijver de wachttijd en stappen van 1 A overslaan. Hij vereist nog steeds verse en plausibele fase-/vermogensmetingen na de vorige opdracht, exact bevestigde HEMS, gezonde besturing, geldige gewenste stroom en een passend strategie-maximum. Een actieve fail-safe, lopende nulwrite, onbevestigde nulopdracht of ongeldige DSMR-data blijft blokkeren. De ingeschakelde loadbalancer begrenst ook een expliciete opdracht. Bij ontbrekende voorwaarden blijft de bestaande veilige route gelden; er is geen onbeperkt geldige snelle herstart na storing.

Een automatisch getriggerde Manual-beoordeling wacht tijdens de korte expliciete positieve gebruikersaanroep, om de schrijver niet te vervangen. Dit geldt niet voor keuze 0 A: de bestaande pauzeroute blijft direct werken. De onafhankelijke fail-safe, nulschrijver en Master-stoproute blijven actief. De reguliere vijfsecondenbeoordeling werkt na de gebruikersaanroep ook de statustekst bij.

Automatisch herstel na begrenzing, storing of HA-herstart behoudt 6 A bij herstart en stappen van 1 A. Handmatige pauze behoudt keuze 0 A. Een nieuwe druk op dezelfde opgeslagen keuze geldt opnieuw als expliciete opdracht.

## Validatie en grenzen

De nieuwe tests voeren de werkelijke YAML uit met gesimuleerde metingen en klok: directe keuzes vanuit 0/6/10/12 A; dezelfde keuze opnieuw; loadbalancer- en strategieplafond; automatisch geleidelijk herstel; verouderde, ongeldige en toekomstige terugmeldingen; storingen; nulwrite; pauze tijdens voorbereiding; behoud van pauze en herstartgedrag. Een asynchroon scenario test dat de door de keuze getriggerde regelaar de expliciete write niet annuleert en een daaropvolgende pauze wel wint. Alle 109 Python-tests zijn lokaal geslaagd, inclusief de bestaande regressietests. Deze modellen vervangen geen HA-configuratiecontrole en fysieke test na installatie.

## Uitvoering en resterende grenzen

De installatie en fysieke tests zijn op 18 november 2026 uitgevoerd; zie de gekoppelde testresultaten. Een expliciete keuze naar 10/16 A werd direct opgedragen. Tijdelijke begrenzing, de eerste automatische herstelstap en blijvende Pauze zijn getest. Vanwege 98% auto-SOC is in de laatste korte ronde bewust gepauzeerd bij de opdracht naar 8 A; volledig herstel tot de bewaarde 10 A is toen niet afgewacht. Node-RED-logica en dashboard vereisten geen wijzigingen.
