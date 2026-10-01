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
  (auf der Kontaktakte im Reiter Kommunikation, Abschnitt Portalzugang, sowie beim
  Portalzugang zum Übergabeprotokoll). Das PDF-Anschreiben zum Portalzugang (Übergabeprotokoll,
  Einladung als Anschreiben) enthält den Einladungslink zusätzlich als QR-Code neben dem
  gedruckten Link und Code, sofern eine öffentliche Portaladresse konfiguriert ist.
- Einladen von der Kontaktakte: Der Abschnitt Portalzugang liest beim Öffnen den Stand des
  Portalkontos des Kontakts (Kein Portalzugang, Eingeladen mit Ablauf des Codes, Zugang aktiv
  mit Aktivierungsdatum und letzter Anmeldung, Hinweis gesperrt bei einer Anmeldesperre) und
  bietet ohne bestehendes Konto Einladen mit der gewählten E-Mail-Adresse an (nur mit dem
  Recht contacts:update; lesen genügt das Recht contacts:read). Einladungscode, Hash oder
  Passwort werden dabei nie ausgegeben. Ohne konfigurierte öffentliche Portaladresse
  erscheint nur der Einladungscode.
- Einladung annehmen: Code eingeben, Passwort setzen (6 bis 128 Zeichen). Danach Anmeldung
  mit E-Mail und Passwort. Der zweite Faktor (Code aus einer Authenticator-App) ist
  freiwillig und wird unter Sicherheit eingeschaltet oder ausgeschaltet (Betreiberentscheidung
  M2-01 vom 26.09.2026). Ist er eingeschaltet, kann beim Code-Schritt Dieses Gerät 90 Tage
  merken gewählt werden; gemerkte Geräte stehen unter Sicherheit und lassen sich dort
  abmelden.
- Anmeldelink per E-Mail (M21-01): Auf der Anmeldeseite kann statt des Passworts ein
  einmaliger Anmeldelink angefordert werden (nur E-Mail-Adresse eingeben). Der Link wird an
  die hinterlegte Adresse verschickt, ist 15 Minuten gültig und einmal nutzbar; je Adresse
  und Stunde werden höchstens fünf Anfragen angenommen. Die Antwort ist immer dieselbe,
  unabhängig davon, ob ein Konto besteht. Ist unter Sicherheit für dieses Konto der optionale
  Bestätigungscode per E-Mail eingeschaltet (durch die Verwaltung, Standard aus), folgt nach
  dem Öffnen des Links eine zweite E-Mail mit einem sechsstelligen Code (10 Minuten gültig,
  einmal nutzbar). Die bestehende Anmeldung mit Passwort bleibt unverändert möglich.
- Einladungsbrief als PDF mit QR-Code (M21-01): Im Abschnitt Portalzugang der Kontaktakte
  erzeugt Einladung als Anschreiben ein PDF auf dem Briefbogen des Mandanten mit dem
  Einladungscode als Text und als QR-Code, für Kontakte, die postalisch erreicht werden. Der
  Code in diesem Brief ist 90 Tage gültig (länger als der 14-tägige E-Mail-Einladungscode),
  weil ein Brief erst mit Verzögerung ankommt. Jede neue Ausgabe des Briefs ersetzt einen
  zuvor ausgegebenen Code; ein älterer, bereits verschickter Brief wird damit ungültig.
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
| Verbrauch | ja, nach Freigabe | ja, nach Freigabe | nein | nein |
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

## Benachrichtigungen

Die Übersicht zeigt ungelesene Benachrichtigungen der Verwaltung an den eigenen Zugang. Ein
Klick öffnet den Betreff im Portal, zum Beispiel die Meldung, den Auftrag oder das
Übergabeprotokoll, und markiert nur diesen Eintrag als gelesen. Einträge ohne Portalseite
lassen sich mit einem Klick als gelesen markieren. Verweise führen nie in das CRM.

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

## Verbrauchsinformation

Die Seite Verbrauch zeigt Mietern die monatliche Verbrauchsinformation der eigenen Einheit
(Heizung und Warmwasser mit Vormonat, Vorjahresmonat und Durchschnitt im Objekt). Grundlage
sind die vom Messdienst übermittelten Monatsverbräuche; geschätzte Werte sind gekennzeichnet,
fehlende Werte werden nicht durch Null ersetzt. Die Seite ist erst sichtbar, wenn die
Verwaltung die Funktion für den Mandanten und das Objekt eingeschaltet und die Vorlage als
verifiziert markiert hat; vorher erscheint nur der Hinweis, dass die Verbrauchsinformation
noch nicht freigeschaltet ist. Eine Benachrichtigung über einen neuen Monat kommt nur, wenn
die Verwaltung den Benachrichtigungsschalter gesetzt hat. Die Anzeige ist keine Abrechnung
und kein Nachweis der Zustellung (Kapitel Abrechnung Miete, Abschnitt Verbrauchsinformation).

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

## Übergabeprotokoll am eigenen Handy

Mieter, Gehilfen und andere Beteiligte füllen ein Übergabeprotokoll auf dem eigenen Handy
oder Tablet aus, wenn die Verwaltung sie dazu eingeladen hat (Stand 29.09.2026, Umfang
M30-06).

- Einladung: per QR Code vor Ort oder per Link aus der Einladungsmail. Nach der Anmeldung
  erscheint im Menü der Eintrag Übergabe; er führt jederzeit zurück zum Protokoll, auch nach
  einem Absprung in einen anderen Bereich.
- Aufbau: die Abschnitte Objekt, Beteiligte, Kaution, Zähler, Räume, Mängel, Schlüssel,
  Gegenstände, Bemerkungen, Unterschriften sowie Prüfung und Abschluss liegen als Reiter in
  einer Zeile, die sich am Handy seitlich wischen lässt. Speichern liegt unten in Reichweite
  des Daumens.
- Fotos: Zähler, Räume, Mängel und Gegenstände nehmen ein Foto direkt beim Anlegen des
  Eintrags auf (Foto aufnehmen öffnet die Kamera, Aus Galerie wählen die vorhandenen Fotos,
  auch iPhone Fotos im HEIC Format). Jede Datei zeigt ihren Stand: Wartet, Wird hochgeladen,
  Fertig oder Fehlgeschlagen mit Erneut versuchen. Fotos werden vor dem Senden verkleinert;
  Ortsangaben und andere Metadaten entfernt der Server. Ein Tipp auf ein Foto öffnet es groß
  im selben Fenster; Schließen führt zurück zum Protokoll.
- Unterschrift: Einwilligungstext lesen, Beteiligten wählen, mit dem Finger oder Stift
  unterschreiben. Rückgängig nimmt den letzten Strich zurück, Leeren die ganze Fläche. Ein
  Drehen des Geräts erhält die Unterschrift.
- Abschluss: Protokoll verbindlich abschließen fragt in einem Bestätigungsblatt nach; liegen
  Hinweise vor, erscheinen sie zuerst und der Abschluss ist trotz Hinweisen möglich. Danach
  ist das Protokoll festgeschrieben.
- Lesefenster: nach dem Abschluss bleibt das Protokoll 14 Tage als Leseansicht erreichbar,
  mit Zählerständen, Räumen, Mängeln, Fotos, Unterschriften und dem PDF. Das PDF öffnet im
  selben Fenster; Zurück führt zum Protokoll. Interne Angaben der Verwaltung, frühere
  Fassungen und Stornierungen sind nicht sichtbar.
- Gerät: das Portal speichert keine Daten auf dem Gerät. Ohne Verbindung erscheint eine
  Hinweisseite; nicht gespeicherte Eingaben müssen nach dem Wiederaufbau der Verbindung neu
  erfasst werden. Auf dem iPad und iPhone lässt sich das Portal über Teilen und Zum
  Home-Bildschirm ablegen.

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
- **Zweiter Faktor wird abgefragt**: Der Nutzer hat ihn unter Sicherheit eingeschaltet;
  auf einem gemerkten Gerät entfällt die Abfrage 90 Tage lang. Ausschalten unter Sicherheit
  mit dem aktuellen Passwort.

## Barrierefreiheit (V13)

Das Portal ist auf semantische Struktur (eine Überschrift erster Ordnung je Seite, Landmarken
`header`, `nav`, `main`, `footer`), vollständige Tastaturbedienung (Sprungmarke „Zum Inhalt
springen“ vor Kopf und Navigation, sichtbarer Fokusring `mhvp-focus` auf jedem bedienbaren
Element, Fokusreihenfolge entlang der Lesereihenfolge), beschriftete Formularfelder mit
Fehlermeldungen über `aria-describedby`, Tabellen mit `scope`-Kopfzellen (`HoaAccountTable`,
Kontoauszug), Bildern mit Alternativtext (zum Beispiel der TOTP-QR-Code unter Sicherheit) und
reduzierte Bewegung (`prefers-reduced-motion`) angelegt. Neue Benachrichtigungen auf der
Übersicht (`PortalNotifications`) werden über `aria-live="polite"` angesagt. Die Sprache steht
im `html`-Tag der Anwendung. Das Layout bleibt bis 200 Prozent Zoom ohne horizontalen
Verlust nutzbar (Fließlayout, Umbruch der Navigation unterhalb `md`).

Die Erklärung zur Barrierefreiheit nach dem Barrierefreiheitsstärkungsgesetz (BFSG) steht ohne
Anmeldung unter `/barrierefreiheit`; sie ist als Entwurf gekennzeichnet, offene Pflichtangaben
(Ergebnis der externen Prüfung, Feedback-Kontakt, zuständige Überwachungsstelle) sind mit
„[zu ergänzen]“ markiert, siehe `docs/OPEN_QUESTIONS.md` (M21-09). Automatisierte Prüfungen der
Kernkomponenten (Navigation, Übersicht, Aushänge, Meldung, Kontoauszug/Hausgeldkonto) laufen mit
`axe-core` über `vitest-axe` (`apps/web-portal/src/components/portal/Accessibility.axe.test.tsx`)
als technisches Hilfsmittel; sie ersetzen keine externe Prüfung (`docs/ASSUMPTIONS.md` A-060).

## Portal Welle 2 (30.09.2026)

* **Chat zur Meldung.** Ist der Chat unter Einstellungen, Portalformulare, Portalfunktionen eingeschaltet, schreiben Mieter und Eigentümer in ihrer Meldung Nachrichten. Antworten der Verwaltung entstehen im Ticket als externer Kommentar (oder über `POST /portal-admin/tickets/{id}/messages`) und lösen eine Benachrichtigung im Portal aus. Interne Notizen sind nie sichtbar. Der Chat ist kein Notdienst.
* **Dokumentstatus.** In der Dokumentliste zeigt jedes Dokument Neu oder Gelesen. Der Status ist ein Indiz für den Abruf und keine Zustellung.
* **Standort der Schadensmeldung.** Das Feld Standort (Raum, Gebäudeteil, Etage) steht in der Beschreibung der Meldung.
* **Vollmacht.** Ein Vertreter mit Vollmacht wird über die API angelegt (`POST /portal-admin/representations`) mit Vollmachtsdokument und Zeitraum und sieht die Eigentümeransicht nur lesend bis zum Ende oder Widerruf. Anlegen und Widerruf entscheidet die Geschäftsführung.
* **Support-Sicht.** Der Nutzer erteilt unter Sicherheit eine befristete Einwilligung. Nur dann kann die Verwaltung seine Ansicht lesend einsehen, mit Grund, protokolliert.
* **Eigentum.** Die Seite Eigentum zeigt beschlossene Zahlungen mit Geltungsdauer und Zahlungsempfänger sowie freigegebene Meldungen zum Objekt. Es wird keine Zahlung ausgelöst.
* **Formularbaukasten.** Im CRM stehen 14 Elementtypen bereit. Die Zustellung ist Ticket oder Ticket mit E-Mail an eine feste Adresse der Verwaltung.
* **Funktionen und Statistik.** Unter Einstellungen, Portalformulare schaltet der Administrator Chat, KI-Vorqualifizierung und Support-Sicht ein und sieht die Nutzungszahlen der letzten 30 Tage.

## Belege suchen, sortieren und gesammelt laden (Portal)

Unter Dokumente suchen Sie nach Titel oder Dateiname und sortieren nach Datum oder Titel. Mit der Auswahl und dem Knopf Sammel-Download erhalten Sie die gewählten Belege als ZIP-Datei mit einer Indexdatei (INDEX.csv). Es sind höchstens 100 Belege je Abruf möglich, es gelten dieselben Sichtbarkeitsregeln wie beim Einzelabruf.

## Rollenwechsel im Portal

Konten mit mehreren Rollen (zum Beispiel Mieter und Eigentümer) wählen oben die Ansicht. Die Auswahl begrenzt nur die Navigation und vergibt keine Rechte.

## Eigentümer: Einzelabrechnung, Umlageeigenschaften, Mieterträge

Unter Hausgeldabrechnung steht die Einzelabrechnung Ihrer Einheit als PDF, sobald die Verwaltung sie freigegeben hat (Abgabe an Eigentümer) und die Freigabestufe G4 für Ihre Gemeinschaft offen ist. Unter Eigentum sehen Sie Ihren Anteil an Wirtschaftsplan und Sonderumlage, die Umlageschlüssel Ihrer Einheiten und, bei Sondereigentumsverwaltung, die vereinbarte Miete je Objekt.

## Dienstleister: E-Rechnung als XML

Bei einem ausgeführten Auftrag kann eine XRechnung (XML) eingelesen werden. Rechnungsnummer, Datum und Bruttobetrag werden vorgeschlagen und vor dem Einreichen geprüft. Die Verwaltung prüft die Rechnung wie jede andere.

## Beirat: Kontext einer Prüfposition

Bei jeder Position zeigt Kontext anzeigen Buchung, Rechnung, Auftrag, Zahlung, Umlageschlüssel und Vorjahr sowie Hinweise auf fehlende Unterlagen. Nur lesend.

## Portal-Logo hochladen (Einstellungen, Mandant)

Unter Einstellungen, Mandant, Abschnitt "Portal der Mandanten" laden Sie das Logo als PNG oder JPEG hoch. Das Logo wird als Dokument abgelegt, seine Kennung wird erst mit "Speichern" in das Branding übernommen. "Logo entfernen" und Speichern lässt das Portal wieder neutral.
