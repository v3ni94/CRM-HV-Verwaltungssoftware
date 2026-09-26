# Portal (Mieter, Eigentümer, Beirat, Dienstleister)

Stand 26.09.2026, Version 1.22.1. Dieses Kapitel richtet sich an Sachbearbeiter, die
Portalzugänge einrichten und Portaleingaben bearbeiten, sowie an Mieter, Eigentümer,
Beiratsmitglieder und Dienstleister, die das Portal nutzen.

## Zweck

Das Portal (eigene Anwendung unter der Portal-Adresse des Mandanten) gibt Mietern,
Eigentümern, Beiratsmitgliedern und Dienstleistern einen rollenabhängigen Zugang zu ihren
Daten. Jede Eingabe mit Geld- oder Vertragsbezug ist ein Vorschlag und wird von der
Verwaltung geprüft; nichts wird automatisch übernommen (Hinweis im Portal: Vorschlag, wird
von der Verwaltung geprüft). Interne Vermerke der Verwaltung sind im Portal nie sichtbar.

## Anmeldung und Einladung

- Die Verwaltung lädt einen Kontakt ein (Portalzugang einladen); Rechte leiten sich aus den
  Verträgen des Kontakts ab (Mieter, Eigentümer) und werden bei Änderungen neu abgeleitet.
  Der Einladungscode wird nur einmal angezeigt und gilt 14 Tage; er ist zusammen mit der
  Portaladresse zu übermitteln. Im CRM steht der Einladungslink als Text und als QR-Code
  (derzeit beim Portalzugang zum Übergabeprotokoll; ein QR-Code im PDF-Anschreiben ist
  Betreiberentscheidung M21-08).
- Einladung annehmen: Code eingeben, Passwort setzen. Danach Anmeldung mit E-Mail,
  Passwort und zweitem Faktor bei jeder Anmeldung; vertrauenswürdige Geräte gibt es im
  Portal bewusst nicht.
- Installation als App (PWA): Das Portal bietet auf unterstützten Geräten Installieren an
  (unter iOS in Safari über Teilen und Zum Home-Bildschirm hinzufügen). Es werden keine
  Daten auf dem Gerät gespeichert; ohne Verbindung zeigt die App nur die Startseite mit dem
  Hinweis Keine Verbindung.

## Seiten je Rolle

| Seite | Mieter | Eigentümer | Beirat | Dienstleister |
| --- | --- | --- | --- | --- |
| Übersicht | ja | ja | ja | ja |
| Dokumente | ja | ja | nein | nein |
| Meldungen | ja | ja | nein | nein |
| Kontoauszug | ja | ja | nein | nein |
| Zählerstand | ja | ja | nein | nein |
| Datenänderung | ja | ja | nein | nein |
| Aushänge | ja | ja | nein | nein |
| Formulare | je Zielgruppe | je Zielgruppe | nein | nein |
| Beschlüsse | nein | ja | nein | nein |
| Ansprechpartner | nein | ja | nein | nein |
| Hausgeldkonto | nein | ja | nein | nein |
| Prüfungsraum | nein | nein | ja | nein |
| Aufträge | nein | nein | nein | ja |
| Übergabeprotokolle | wenn freigegeben | wenn freigegeben | nein | nein |

Ein Kontakt kann mehrere Rollen tragen (zum Beispiel Eigentümer und Beirat); die Seiten
addieren sich.

## Dokumente und Lesebestätigungen

Dokumente zeigt die für den Beteiligten freigegebenen Dokumente (Sichtbarkeit im Portal am
Dokument, Kapitel Dokumente und DMS). Öffnen oder Herunterladen wird als Abruf vermerkt. Im
CRM zeigt das Dokument unter Abrufe über das Portal je Abruf Zeitpunkt, Art (angezeigt,
heruntergeladen) und Konto. Der Abruf ist ein Indiz, keine Zustellung und keine Rechtsfolge;
Fristen werden daraus nicht abgeleitet.

## Meldungen (Schäden und Anliegen)

Neue Schadensmeldung mit Titel, Beschreibung und optional Fotos (JPEG oder PNG). Fotos
werden beim Hochladen von Aufnahmedaten (Ort, Kamera) befreit und verkleinert. Jede Meldung
wird im CRM ein Ticket mit Quelle Portal; der Verlauf zeigt Status (Neu, In Bearbeitung,
Wartet auf Rückmeldung, Erledigt, Geschlossen, Abgelehnt), Nachrichten und Anhänge. Der
Melder kann Nachrichten ergänzen; interne Kommentare der Verwaltung bleiben verborgen.

Terminvorschläge des Handwerkers: Hat die Verwaltung einen Auftrag freigegeben, kann der
Dienstleister bis zu drei Termine vorschlagen. Der betroffene Bewohner sieht sie in seiner
Meldung unter Terminvorschläge des Handwerkers und bestätigt einen mit Diesen Termin
bestätigen. Die Auswahl gilt als Bestätigung gegenüber Handwerker und Verwaltung, setzt den
Termin am Auftrag und erscheint im Ticketverlauf; die übrigen Vorschläge gelten als nicht
gewählt.

## Kontoauszug, Zählerstand, Datenänderung

- Kontoauszug: offene Posten der eigenen Verträge (Information, keine Abrechnung).
- Zählerstand melden: Vorschlag mit Zähler, Stand und Datum; die Verwaltung prüft und
  übernimmt im CRM.
- Datenänderung: Stammdaten oder Bankverbindung ändern lassen; jeder Vorschlag wird im CRM
  unter Vorschläge aus dem Portal angenommen oder abgelehnt. Bankverbindungen unterliegen
  zusätzlich der Vier-Augen-Freigabe (Kapitel Kontakte).

## Schwarzes Brett (Aushänge)

Im CRM pflegt die Verwaltung am Objekt unter Schwarzes Brett Aushänge mit Titel, Text,
Gültig ab, Gültig bis (leer = auf Weiteres), Zielgruppe (Mieter und Eigentümer, Mieter,
Eigentümer) und optional einem Dokument des Objekts als Anlage (Recht Objekte ändern;
Liste mit Objekte lesen). Beenden nimmt einen Aushang sofort aus dem Portal, der Eintrag
bleibt erhalten.

Im Portal zeigt Aushänge die gültigen Aushänge der eigenen Objekte für die passende
Zielgruppe; neue Aushänge (14 Tage ab Anlage) sind als Neu markiert, die Übersicht meldet
neue Aushänge. Ein Aushang ist eine Information der Verwaltung, keine Zustellung und keine
Fristauslösung.

## Formulare

Die Verwaltung legt unter Einstellungen, Portalformulare Formularvorlagen an (Kapitel
Einstellungen): Name, Hinweistext, Ticketkategorie, Zielgruppe (Mieter und Eigentümer, Nur
Mieter, Nur Eigentümer) und Felder (Text, Zahl, Datum, Auswahl, Datei, je Feld Pflicht).

Im Portal listet Formulare die Vorlagen der eigenen Zielgruppe. Absenden erzeugt einen
Vorgang: Im CRM entsteht ein Ticket der gewählten Kategorie mit den Angaben als Text und
den hochgeladenen Dateien als Anhang; im Portal erscheint der Vorgang unter Meldungen. Die
Angaben sind ein Vorschlag und werden von der Verwaltung geprüft.

## Eigentümerseiten

Nur mit aktiver Eigentümerrolle (Eigentumsverhältnis in der Gemeinschaft):

- Beschlüsse: verkündete Beschlüsse der eigenen Gemeinschaft mit Nummer, Datum,
  Gegenstand, Art, Abstimmungsergebnis und Wirksamkeitsstatus. Maßgeblich bleibt die
  Beschluss-Sammlung der Verwaltung.
- Ansprechpartner: Verwaltung sowie Hausmeister und Notdienst des Objekts, soweit für
  Eigentümer freigegeben; keine privaten Rufnummern.
- Hausgeldkonto: gebuchte Einträge des eigenen Debitorenkontos im Buchungskreis der
  Gemeinschaft (Sollstellungen, Zahlungen und Gutschriften, Saldo). Hinweis im Portal:
  keine Abrechnung, keine Rechtsfolge; maßgeblich sind Wirtschaftsplan, Jahresabrechnung
  und Beschlüsse. Ohne Buchungskreis oder solange das Altsystem führt, erscheint nur ein
  Hinweis ohne Beträge.

## Prüfungsraum des Beirats

Beiratsmitglieder erhalten je Prüfauftrag einen Beiratszugang (Kapitel WEG, Prüfauftrag).
Im Portal sehen sie unter Prüfungsraum den Prüfauftrag, Zeitraum, Stichprobe oder
Vollprüfung, Gesamtstatus, die ausgewählten Positionen mit Status (Offen, Geprüft,
Rückfrage, Beanstandet, Veraltet), die zugehörigen Abrechnungspositionen und nur die dazu
freigegebenen Belege (Beleg öffnen wird als Abruf vermerkt). Unter Vermerke und Rückfragen
erfassen sie Vermerk oder Rückfrage je Position oder zum gesamten Prüfauftrag; die
Verwaltung antwortet im CRM, die Antwort erscheint am selben Eintrag. Der Beirat bucht
nichts, gibt nichts frei und ändert keine Abrechnung. Eine nach der Prüfung geänderte
Rechnung oder stornierte Buchung markiert die Position auch für den Beirat als veraltet.

## Dienstleister (Aufträge)

Dienstleister sehen unter Aufträge ihre Vorgänge mit Status (Angefragt, Angebot abgegeben,
Freigegeben, Termin vereinbart, In Ausführung, Ausgeführt, Rechnung eingereicht,
Angenommen, Abgelehnt, Storniert) und Aktionen:

1. Auftrag ablehnen oder Angebot abgeben (Betrag, optional Datei).
2. Nach Freigabe durch die Verwaltung: Termin direkt festlegen oder Terminvorschläge an den
   Bewohner senden (bis zu drei Termine, Hinweis). Der Bewohner bestätigt einen Vorschlag
   im Portal (siehe Meldungen); der Status je Vorschlag ist Offen, Bestätigt, Nicht gewählt
   oder Ersetzt.
3. Ausführung dokumentieren mit Ausführungsbericht und Fotos der Ausführung (JPEG oder
   PNG, ohne Aufnahmedaten).
4. Rechnung einreichen (Nummer, Datum, Bruttobetrag, Datei). Die Rechnung ist ein Vorschlag
   und durchläuft den Belegeingang und Rechnungseingang wie jede Eingangsrechnung (Kapitel
   Belegeingang).

## Mitarbeiterzugang und Portalrechte je Rolle

Jede Mitarbeiterin und jeder Mitarbeiter erhält zusätzlich einen eigenen Portalzugang für
den gesamten Mandanten, um Vorgänge aus Sicht des Portals nachvollziehen zu können. Unter
Einstellungen, Rollen und Rechte legt die Matrix Portalrechte je Rolle fest, welche
Portalfunktionen der Mitarbeiterzugang je CRM-Systemrolle sieht. Die Rollen Portalnutzer,
Nur-Lesezugriff, Steuerberater und Versicherungsmakler erhalten keinen Portalzugang; ein
Rollenwechsel in eine ausgenommene Rolle entzieht den Zugang sofort. Änderungen an der
Matrix verlangen das Recht Mandanteneinstellungen ändern; Übernehmen auf bestehende Zugänge
wendet eine geänderte Matrix nachträglich an. Ein Mitarbeiterzugang erhält keine
Beiratsrolle.

## Was ist Vorschlag, was verbindlich

Zählerstand, Datenänderung, Formulareinreichung, Angebot, Terminvorschlag und Rechnung sind
Vorschläge; verbindlich werden sie erst durch Prüfung und Übernahme im CRM. Ein Aushang, ein
Dokumentabruf oder eine Ansicht des Hausgeldkontos ist keine Zustellung, keine Abrechnung
und begründet keine Frist. Die Termin-Bestätigung eines Bewohners setzt nur den Termin am
Auftrag.

## Häufige Fehler

- **Seite Beschlüsse, Ansprechpartner oder Hausgeldkonto meldet Nur für Eigentümer**: Der
  Zugang hat kein aktives Eigentumsverhältnis; im CRM Zugriffsrechte neu ableiten.
- **Formular fehlt im Portal**: Vorlage inaktiv oder Zielgruppe passt nicht zur Rolle.
- **Terminvorschläge nicht möglich**: Der Auftrag ist noch nicht freigegeben oder hat keine
  Meldung mit Bewohner.
- **Aushang im Portal nicht sichtbar**: Gültigkeit liegt nicht im heutigen Tag, Zielgruppe
  passt nicht oder der Aushang wurde beendet.
- **Foto wird abgelehnt**: Nur JPEG und PNG; nicht lesbare Bilder werden abgewiesen.
- **Zweiter Faktor bei jeder Anmeldung**: Gewollt, das Portal kennt keine
  vertrauenswürdigen Geräte.
