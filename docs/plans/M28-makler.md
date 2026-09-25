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
   Hostname bis zur Ablösung. Anmeldung zentral über das CRM (Entscheidung 25.09.2026):
   FLOW wird als OIDC-Client des Plattform-Providers registriert (ADR 0006 Nr. 7, Authorization
   Code mit PKCE); Benutzer und Rechte werden nur im CRM gepflegt. Voraussetzung: FLOW kann
   OIDC-Login (sonst kleiner Eingriff in FLOW).
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

## Erkenntnisse aus dem FLOW-Repository (v3ni94/FLOWFACTxHVM, gelesen 25.09.2026)

- Stack: Laravel 12, PHP 8.3, MariaDB. Betrieb geprüft 25.09.2026: flowfact.muellerhv.de zeigt auf
  217.160.0.148 (IONOS Webhosting), nicht auf den CRM-Server. Der Container "immoware-hub" auf
  dem CRM-Server ist eine andere Anwendung (Immoware Hub). Kein Docker-Compose im FLOW-Repo.
  Folge: Stufe 1 (FLOW hinter Traefik) entfällt; FLOW bleibt bis zur Ablösung im Webhosting,
  die Datenübernahme erfolgt per Datenbankexport aus dem Webhosting.
- FLOWFACT-API: belegt nur aus dem SDK `@flowfact/api-services`; zweistufige Anmeldung
  (Zugangsschlüssel gegen Cognito-Token über admin-token-service, dann Header cognitoToken),
  Dienste entity-service, schema-service, search-service, multimedia-service,
  portal-management-service. Idempotenz über eigene uuid als identifier mit Suche vor dem
  Anlegen. Portalstatus nur aus der Statusabfrage, nie aus dem Sendebefehl.
- Stand der Prüfung: bis auf den Token-Tausch (21.09.2026) ist keine Funktion gegen ein echtes
  FLOWFACT-Konto gelaufen, alles simuliert. Offen laut FLOW: ob der Tarif einen API-Token erlaubt,
  angebundene Portale, echte Schemanamen, Freigabeverhalten, Bildlimits.
- Datenvertrag: Vermarktungsart miete/kauf, Objektarten wohnung, haus, gewerbe, stellplatz,
  grundstueck; Preise in Cent mit Heizkostenregeln (Warmmiete serverseitig berechnet);
  Energieausweisfelder; drei Statusachsen (Bearbeitung, Übertragung, Portal je Portal);
  interne Daten strikt getrennt von Inseratsfeldern (Positivliste im Mapper).
- Migration: zu übernehmen sind listings.uuid, listing_flowfact_links.flowfact_entity_id und
  listing_media.flowfact_multimedia_id. Kein Exportbefehl vorhanden, Übernahme per Datenbankexport.
  Login klassisch (E-Mail, Passwort, optional 2FA), kein OIDC; für die zentrale Anmeldung ist ein
  OIDC-Client in FLOW zu ergänzen oder FLOW wird direkt abgelöst.

## Folgerungen für das CRM-Modell (Stufe 2, umgesetzt) und Stufe 3

- Das CRM-Modell `listing` wird um Objektart, Energieausweisfelder, Heizkostenregel und die
  drei Statusachsen erweitert, sobald der FLOWFACT-Adapter gebaut wird; die FLOW-Positivliste
  wird als Mapper übernommen. Bilder als Dokumente mit Prüfsumme und FLOWFACT-Medien-ID.
- Der Adapter wird aus docs/flowfact-api.md und docs/connector.md des FLOW-Repos abgeleitet und
  erst nach einem Smoke-Test gegen das echte Konto (Token, currentUser, Schemata) freigegeben.

## Stufe 4 (umgesetzt 24.09.2026): FLOW-Import per SQL-Dump

Der Import liest einen von Hand hochgeladenen Datenbankexport aus dem Webhosting (kein
Exportbefehl in FLOW, siehe oben) und erzeugt je FLOW-Anzeige eine Vorschau mit
Zuordnungsvorschlag zu Objekt und Einheit, Preisumrechnung und Statusabbildung, bevor eine
Anzeige tatsächlich angelegt wird (`mhvp.letting.flow_import`, docs/rules/M28-01.md). Die
Übernahme ist über `external_uuid` idempotent, ein zweiter Lauf über denselben Importlauf legt
nichts doppelt an. FLOWFACT selbst wird weiterhin nicht angesprochen; `publication_status` bleibt
ein aus `listing_flowfact_links.sync_status` abgeleiteter Platzhalter. Offen bleibt die
automatische Einheitenzuordnung, da FLOW kein Einheitenkennzeichen mitführt; sie ist im
Erfassungsbogen (`/makler/import`) manuell nachzutragen.
