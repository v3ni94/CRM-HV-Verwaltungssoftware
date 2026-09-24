# M28 Makler: Müller FLOW in die Plattform überführen

Stand 25.09.2026, Entscheidung des Betreibers: Müller FLOW (Verwaltung von Anzeigen für
Vermietung und Verkauf, Übergabe an FLOWFACT, das die Inserate veröffentlicht) läuft heute
produktiv unter flowfact.muellerhv.de und wird als Bereich "Makler" in das CRM überführt.
Zielhost der Übergangszeit: flow.mueller-holding.ag.

## Zielbild

- Reiter "Makler" (Gruppe Verwaltung, Recht `letting:read`): Anzeigen, Interessenten (M26),
  Besichtigungen, Übergabe an FLOWFACT mit Statusrückmeldung.
- Eine Anzeige entsteht aus einem Verwaltungsobjekt und einer Einheit; Stammdaten (Adresse,
  Fläche, Zimmer, Baujahr, Energieausweis sobald modelliert, Miete oder Kaufpreis) werden
  vorbelegt und bleiben mit der Einheit verknüpft.
- FLOWFACT bleibt der Kanal zu den Portalen; die Plattform sendet, FLOWFACT inseriert.

## Stufen

1. **Betrieb**: DNS flow.mueller-holding.ag, FLOW als Container hinter dem bestehenden Traefik
   (Netz traefik-proxy, Zertifikatsauflöser letsencrypt), flowfact.muellerhv.de als zweiter
   Hostname bis zur Ablösung. Kein Eingriff in FLOW.
2. **Datenmodell im CRM** (Domäne `letting`): `listing` (Anzeige: Einheit, Art Vermietung oder
   Verkauf, Preis, Texte, Bilder als Dokumente, Status Entwurf, aktiv, reserviert, beendet),
   `listing_publication` (Übergabe an FLOWFACT: Zeitpunkt, externe ID, Status, Fehlertext).
   Interessenten und Besichtigungen hängen an der Anzeige (Prospect aus M26 erweitern).
3. **FLOWFACT-Anbindung**: Adapter mit Schnittstelle, Zugangsdaten je Mandant in den
   Einstellungen, Übergabe nur nach Klick, nie automatisch. Format und Endpunkte werden erst
   nach Vorlage der FLOWFACT-Dokumentation umgesetzt (keine erfundene Schnittstelle).
   Alternative, falls FLOWFACT OpenImmo annimmt: OpenImmo-Export (M26-02).
4. **Migration**: Bestandsdaten aus FLOW (Anzeigen, Interessenten, Zuordnung zu FLOWFACT-IDs)
   per Import mit Testlauf und Abgleich, wie beim Immoware24-Import (M8).
5. **Ablösung**: FLOW abschalten, flowfact.muellerhv.de auf den Makler-Bereich umleiten.

## Voraussetzungen vom Betreiber

- Zugriff auf den FLOW-Quellcode oder eine Beschreibung der Datenfelder und der FLOWFACT-
  Übergabe (welche API, welche Felder, welche IDs kommen zurück).
- FLOWFACT: API-Dokumentation und Zugangsdaten (nur auf dem Server, nie im Repository).
- Entscheidung, welche Felder Pflicht für ein Inserat sind (Pflichtangaben in Immobilienanzeigen,
  Energieausweis: M26-03).

## Gates

Keine Geldflüsse; Provisionen und Rechnungen an Käufer oder Vermieter bleiben außerhalb dieses
Meilensteins. Veröffentlichung erfolgt durch FLOWFACT, daher keine neue Freigabestufe; der
Versand von Daten an FLOWFACT braucht die Zugangsdaten und die dokumentierte Schnittstelle.
