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

- Erneute Einladung (T13-01): Ist eine Einladung abgelaufen und wurde nie angenommen, lädt Portalzugang einladen am selben Kontakt erneut ein. Es entsteht kein zweites Konto; Code und Ablauf (14 Tage) werden erneuert, der alte Code wird ungültig. Bei aktivem Konto oder noch gültiger Einladung erscheint ein Konflikt.

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
  mit E-Mail und Passwort. Der zweite Faktor (Code aus einer Authenticator-App) ist im
  Portal standardmäßig freiwillig und wird unter Sicherheit eingeschaltet oder ausgeschaltet
  (Betreiberentscheidung M2-01 vom 26.09.2026, Standard auch nach Regel M2-04). Wählt die
  Verwaltung als Pflicht unter Einstellungen, Rollen und Rechte, ihn auch für Portalzugänge
  vorzuschreiben (Regel M2-04, Standard aus), richtet der
  Nutzer ihn bei der nächsten Anmeldung auf der Seite Zweiten Faktor einrichten ein, auch nach
  einem Anmeldelink; ausschalten lässt er sich dann nicht. Ist er eingeschaltet, kann beim
  Code-Schritt Dieses Gerät 90 Tage
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
Gültig ab, Gültig bis (leer = auf Weiteres), Kategorie (Katalog), Hinweisstufe (neutral,
Info, Warnung, Gefahr), Zielgruppen (Mieter, Eigentümer, Dienstleister, mehrere wählbar) und
optional mehreren Dokumenten des Objekts als Anlagen, kommagetrennt als Dokument-IDs (Recht
Objekte ändern; Liste mit Objekte lesen). Jedes Dokument muss für alle gewählten Zielgruppen
freigegeben sein. Beenden nimmt einen Aushang sofort aus dem Portal, der Eintrag bleibt
erhalten. In der Liste steht je Aushang die Lesequote (gelesen x von y).

Im Portal zeigt Aushänge die gültigen Aushänge der eigenen Objekte für die passende
Zielgruppe; Dienstleister sehen Aushänge für Objekte, an denen sie einen Auftrag haben. Die
Hinweisstufe ist farblich und als Text gekennzeichnet, neue Aushänge (14 Tage ab Anlage) sind
als Neu markiert, die Übersicht meldet neue Aushänge. Mit Als gelesen bestätigen hinterlegt
das Konto eine Lesebestätigung. Sie ist ein Hinweis auf die Kenntnisnahme, keine Zustellung
und keine Fristauslösung; ein Aushang ist eine Information der Verwaltung.

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
4. Rechnung einreichen (Nummer, Datum, Bruttobetrag, Datei, optional Nettobetrag, USt-Satz
   und IBAN laut Rechnung). Die Rechnung ist ein Vorschlag und durchläuft den Belegeingang
   und Rechnungseingang wie jede Eingangsrechnung (Kapitel Belegeingang). Netto und USt
   müssen zum Brutto passen (sonst Fehlermeldung). Nach der Annahme steht der Auftrag auf
   Abgerechnet; der Belegentwurf trägt Netto, USt und IBAN und zeigt als Befund, ob die
   IBAN zum Kreditorenstamm passt und ob das Rechnungsbuch dieselbe Rechnung schon enthält.
   Die Befunde kennzeichnen nur, sie sperren nichts und lösen keine Zahlung aus.

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
- **Zweiten Faktor einrichten erscheint nach dem Passwort**: Die Verwaltung hat die Pflicht
  für Portalzugänge gewählt (Regel M2-04, Standard ist freiwillig); QR-Code mit der App scannen, ersten
  Code eingeben, danach ist der Nutzer angemeldet.
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

Seit GAH-304 prüft ESLint zusätzlich das Regelset `jsx-a11y` (recommended) und `pages.axe.test.tsx` lässt axe über alle Seiten unter `app/(portal)` laufen (gesperrter und leerer Zustand). `@axe-core/playwright` für Browserläufe ist offline nicht installierbar und bleibt offen.

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

## Vertretung im Portal

Konten mit einer Vollmacht sehen im Portal den Menüpunkt "Vertretung" und im Ansichtswechsel die Rolle "Vertreter". Die Seite zeigt den Vertretenen, den Gültigkeitszeitraum und die Restlaufzeit. Die Vollmacht legt die Verwaltung am Kontakt an, mit Vollmachtsdokument und Zeitraum. Der Zugriff ist lesend und endet mit dem Ablauf oder dem Widerruf; abgelaufene Vollmachten bleiben als "Abgelaufen" sichtbar, gewähren aber nichts mehr.

## Einladung erneuern (V03)

Ist die Einladung eines Kontakts abgelaufen und nicht angenommen, zeigt der Abschnitt "Portalzugang" am Kontakt die Schaltfläche "Einladung erneuern". Sie stellt für dasselbe Konto einen neuen Code mit neuer Frist aus; der Code erscheint einmalig als Code, Link und QR-Code. Aktive, gesperrte und noch gültige Einladungen lassen sich nicht erneuern.

## Freigabe je Unterlagenklasse, Sprache, Dienstleisterinformationen (AA14)

- Unterlagenklasse freigeben: Für einen Portalzugang kann die Verwaltung die Dokumente einer Klasse (zum Beispiel Abrechnungsbelege) eines Rechtsträgers freigeben, mit Rolle und Gültigkeit (`POST /api/v1/portal-admin/accounts/{id}/document-class-grants`). Sichtbar sind nur Dokumente dieser Klasse mit Verknüpfung zum Rechtsträger und Freigabe für die Rolle; die Freigabe bleibt bei der Neuableitung der Rechte erhalten. Welche Rolle welche Klasse erhält, entscheidet die Verwaltung (offen: AA14-03).
- Sprache: Im Kopf des Portals wählt der Nutzer Deutsch oder English; ohne Wahl gilt die Browsersprache, sonst Deutsch. Eine weitere Sprache erfordert nur eine Übersetzungsdatei.
- Formulare: Der Formularbaukasten bietet 20 Elementtypen (neu: Anschrift, Standort, Unterschrift als Name, Einwilligung, Betrag, Trennlinie).
- Dienstleister: Die Seite Rahmenverträge zeigt die eigenen Rahmenverträge und den Verfügbarkeitskalender (nur lesend). Zeitfenster erfasst die Verwaltung über `POST /api/v1/portal-admin/provider-availability`.

## Sprache und Dienstleister im Portal (AB12)

* Die Sprache wählen Sie im Portal oben rechts und auf der Anmeldeseite. Angemeldete Personen haben die Wahl am Portalkonto gespeichert; bei der nächsten Anmeldung gilt diese Sprache auch auf einem anderen Gerät. Wer nicht angemeldet ist, behält die im Browser gewählte Sprache.
* Einstellungen, Dienstleister im Portal (Recht: Kontakte ändern): Dienstleister suchen, Verfügbarkeitsfenster erfassen oder entfernen und Unterlagenklassen eines Rechtsträgers für das Portalkonto freigeben. Der Dienstleister sieht die Fenster im Portal nur lesend. Bewertungen werden dort nicht angezeigt.

## Portalzugang ohne sofortige Einladung und Statusanzeige (AC04)

Beim Anlegen eines Portalzugangs in der Kontaktakte steuert der Schalter "Einladung sofort senden", ob die Einladung direkt versendet wird. Ist er aus, entsteht der Zugang mit dem Status "Nicht eingeladen"; die Einladung lässt sich später mit der Aktion "Einladen" nachholen. Bei abgelaufener Einladung steht die Aktion "Einladung erneuern" bereit. Angezeigt werden alle sechs Status: Nicht eingeladen, Eingeladen, Zugang aktiv, gesperrt, Einladung abgelaufen und Zugang entzogen. Ein entzogener Zugang bleibt entzogen.

Die Einstellungsseite "Dienstleister im Portal" bietet die Rechtsträgerauswahl über einen eigenen Lesepfad (`GET /portal-admin/legal-entities`, nur Id und Name) an, der das Recht tenant_settings:read verlangt; das Recht members:read ist dafür nicht nötig. Pflegen der Fenster und Freigaben verlangt weiterhin contacts:update. Fehlt Ihnen tenant_settings:read, ersetzt ein Hinweistext die leere Rechtsträgerauswahl im Bereich der Klassenfreigaben; die Verfügbarkeitsfenster bleiben bedienbar, Klassenfreigaben setzt die Mandantenadministration (AD05).

## Nutzungsbedingungen annehmen (AD03)

Hat der Verwalter für den Mandanten eine Fassung der Nutzungsbedingungen veröffentlicht (Einwilligungsregeln unter Einstellungen, Feld Fassung der Portal-Nutzungsbedingungen), leitet das Portal nach der Anmeldung auf die Seite Nutzungsbedingungen weiter, bis die Fassung angenommen ist. Dort wird die Fassung angezeigt und mit dem Haken und der Schaltfläche Annehmen und fortfahren bestätigt. Zeitpunkt und Fassung werden beim Kontakt als Einwilligung gespeichert. Bei der Aktivierung einer Einladung erscheint der Haken nach dem ersten Versuch, sobald eine Fassung veröffentlicht ist. Ein Widerruf der Annahme im CRM sperrt den Portalzugang sofort wieder bis zur erneuten Annahme.

Ist die Fassung veröffentlicht, zeigt die Einladungsseite den Haken zur Annahme schon beim Öffnen des Einladungslinks (öffentlicher Abruf der Fassung, ohne Anmeldung und ohne Hinweis darauf, welche Mandanten das Portal nutzen). Als Nachweis der Annahme speichert das Portal Zeitpunkt, Fassung und einen Hash der Verbindungsadresse, nicht die Adresse selbst; der Hinweis steht unter dem Haken. Der Text der Nutzungsbedingungen kommt vom Mandanten (Rechtstexte des Portals), die Software erzeugt ihn nicht.

Kontaktdaten des Mieters oder Eigentümers sehen Dienstleister im Auftrag nur, wenn der Kontakt der Weitergabe an Dienstleister zugestimmt hat (Einwilligung data_sharing) oder der Mandant die vertragliche Notwendigkeit zulässt. Sonst erscheint der Auftrag ohne diese Angaben, der Grund steht im Ereignisprotokoll.

## Online-Teilnahme an der Versammlung (AD06)

Nur für Eigentümer und nur, wenn die Verwaltung die Online-Versammlung freigeschaltet hat. Unter "Versammlungen" bei einer hybriden oder virtuellen Versammlung "Online-Teilnahme anzeigen" wählen.

- "Online-Teilnahme zusagen" meldet die eigenen Einheiten für die Online-Teilnahme an.
- "Videokonferenz öffnen" führt zur Videolösung, die die Verwaltung hinterlegt hat.
- "Wortmeldung abgeben" trägt Sie in die Rednerliste ein; die Verwaltung ruft auf.
- Abstimmen ist nur möglich, solange die Verwaltung die Abstimmung zum TOP geöffnet hat, eine Stimme je Einheit. Das Ergebnis erscheint erst nach der Verkündung.
- "Vollmacht erteilen": Einheit wählen, Bevollmächtigten (Einheit eines anderen Eigentümers oder Verwaltung), Zeitraum und das unterschriebene Vollmachtsdokument hochladen. Eine erteilte Vollmacht kann jederzeit widerrufen werden.

## Eigentümerportal: Mieterträge und Meldungen (Welle 16)

Unter Einstellungen, Portalfunktionen schaltet die Verwaltung die Anzeige der Mieterträge für Kapitalanleger ein (Standard aus) und wählt, welche Meldungen Eigentümer zu ihren Objekten sehen: keine, nur freigegebene oder alle Meldungen der eigenen Objekte (nur Nummer, Titel und Status). Vor dem Einschalten der Mieterträge ist die Datenschutzfreigabe zu prüfen.

## Formularbaukasten: Typen, Prüfregeln und Vorschau (Welle 16)

Unter Einstellungen, Portalformulare zeigt "Elementtypen und Prüfregeln anzeigen" die 20 Elementtypen des Baukastens mit dem erwarteten Wert und der Prüfregel je Typ. Der Hinweis dabei nennt, dass der Abgleich mit der Typenliste des bisherigen Portals noch offen ist.

- "Vorschau anzeigen" bei einer Vorlage oder im Editor zeigt das Formular so, wie es im Portal erscheint. Mit "Beispielwerte prüfen" prüft das System Ihre Beispielwerte mit denselben Regeln wie bei einer Einreichung und zeigt den Text, der im Ticket entstehen würde. Es wird nichts gespeichert, kein Vorgang angelegt und nichts versendet. Dateien werden in der Vorschau nicht hochgeladen.
- Im Portal sehen Mieter und Eigentümer bei Anschrift, Standort, Unterschrift und Betrag einen kurzen Hinweis zum erwarteten Wert. Meldet die Prüfung einen Mangel, steht die Meldung direkt am betroffenen Feld.

## Bewertungen von Dienstleistern (Welle 16)

Unter Einstellungen, Portalformulare, Portalfunktionen steuert die Auswahl "Bewertungen von Dienstleistern", ob die Verwaltung eine Übersicht der Bewertungen sieht. Standard ist "nicht anzeigen". Bei "nur der Verwaltung als Übersicht anzeigen" erscheinen je Dienstleister die Zahl der bewerteten Aufträge, der Durchschnitt und die Verteilung der Sterne, ohne Freitexte. Dienstleister, Mieter und Eigentümer sehen die Bewertungen im Portal nicht. Die Bewertung selbst geben Sie weiter wie bisher beim Abschluss des Auftrags an.


## Assistent für die eigenen Unterlagen (Chat-Bot)

Der Assistent beantwortet Fragen von Mietern und Eigentümern zu den Unterlagen, die für ihren Zugang freigegeben sind. Er liest nie Unterlagen anderer Einheiten oder Personen, und ein Zugang ohne Freigaben bekommt gesagt, dass keine Unterlagen freigegeben sind.

**Für die Verwaltung.** Unter Einstellungen, Portalfunktionen gibt es zwei Schalter, beide ab Werk aus: Assistent für die eigenen Unterlagen (Chat-Bot) und Datenschutz-Feature für KI-Antworten. Mit dem Chat-Bot zeigt das Portal den Menüpunkt Assistent und durchsucht die freigegebenen Unterlagen. KI-Antworten kommen erst hinzu, wenn

1. das Datenschutz-Feature eingeschaltet ist,
2. ein Datenschutzhinweis als Textbaustein "Portal-Assistent: Datenschutzhinweis zur KI-Antwort" eingereicht und durch eine zweite Person freigegeben ist (den Text liefert der Mandant, die Software enthält keinen Rechtstext),
3. der Nutzer den Hinweis in der aktuellen Fassung zur Kenntnis genommen hat und
4. der KI-Anbieter mit Auftragsverarbeitungsvertrag freigegeben ist (Einstellungen, KI).

Fehlt eine Voraussetzung, zeigt der Assistent nur die Treffer und nennt den Grund. Das Protokoll der Fragen (maskiert, mit Ergebnis, Quellen und Grund) steht unter Portalfunktionen, sichtbar mit dem Recht Mandanteneinstellungen.

**Für Mieter und Eigentümer.** Menüpunkt Assistent: Frage eingeben, optional eine Einheit wählen. Eine KI-Antwort ist als solche gekennzeichnet, nennt ihre Quellen und ist Information, keine Auskunft oder Zusage der Verwaltung. Reicht die Grundlage nicht, erscheint ein Hinweis und die Treffer; für verbindliche Fragen bleibt die Meldung an die Verwaltung. Pro Stunde sind höchstens 20 Fragen möglich.

## Support-Ansicht je Portalzugang (CRM)

Im Kontakt, Reiter Freigaben, zeigt die Support-Ansicht lesend, was die Person im Portal sieht (Rollen, Verträge, Meldungen, freigegebene Unterlagen). Sie setzt den Mandantenschalter für die Support-Sicht und eine gültige Einwilligung der Person voraus. Pro Aufruf ist ein Grund Pflicht, jeder Aufruf wird protokolliert; das Protokoll lässt sich anzeigen. Änderungen sind in dieser Ansicht nicht möglich. Recht: Einstellungen ändern (tenant_settings:update).

## Assistent im Portal: Antwort im Hintergrund

Die Antwort der KI entsteht im Hintergrund. Das Portal zeigt den Zustand und fragt ihn ab; dauert die Antwort länger als zwei Minuten, erscheinen stattdessen Treffer aus den eigenen Unterlagen.

## Nebenkostenabrechnung für Mieter (AF16)

Mieter sehen unter "Nebenkostenabrechnung" (`/nebenkosten`) die ausgegebene Betriebs- und Heizkostenabrechnung ihres eigenen Mietvertrags: Kostenanteil, Vorauszahlungen, Ergebnis (Nachzahlung oder Guthaben), die Kostenpositionen mit eigenem Anteil und Erläuterungen zu Umlageschlüssel, Verbrauch, Vorauszahlungen und Saldo. Das Abrechnungsschreiben steht als PDF bereit, sofern es an der Ergebniszeile hinterlegt ist. Die Funktion ist je Mandant unter Fachliche Regeln ("Nebenkostenabrechnung im Mieterportal") einzuschalten, Standard aus; zusätzlich muss die Freigabestufe G3 offen sein, sonst bleibt die Liste leer mit Hinweis. Die Erläuterungen erscheinen nur, wenn die Textbausteine "Mieterportal Abrechnung: Erläuterung ..." freigegeben sind, sonst steht dort ein Platzhalter. Der Abruf wird als Indiz vermerkt und ist keine Zustellung.

## Eigentümerabrechnung, Erläuterung und Wirtschaftsplan (AF15)

Eigentümer sehen unter "Eigentümerabrechnung" (`/eigentuemerabrechnungen`) die ausgegebenen Abrechnungen ihrer Mietverwaltung oder Sondereigentumsverwaltung mit Einnahmen, Ausgaben, Auszahlungen und PDF. Die Anzeige schaltet die Verwaltung unter Portalfunktionen ein (Standard aus); zusätzlich ist die Freigabestufe G3 nötig. Unter "Hausgeldabrechnung" steht je Einheit eine Erläuterung mit Kostenanteil, Vorschüssen (Soll und Ist), Abrechnungsspitze und Rücklage, unter "Wirtschaftsplan" (`/wirtschaftsplaene`) der beschlossene Plan mit Jahresbetrag und monatlichem Vorschuss der eigenen Einheiten; beides erst mit Freigabestufe G4. Die Erklärtexte lassen sich als Textbausteine `portal_owner_explain_*` freigeben. Auf der Seite "Eigentum" erscheint bei leerer Mieterträge-Liste ein Hinweis, die Annahme der Nutzungsbedingungen verlinkt direkt die veröffentlichte Fassung.

Eigentümer reiner Mietverwaltungen (ohne Wohnungseigentum) erhalten den Zugang zur Eigentümerabrechnung über ihren eigenen Rechtsträger, solange ihr Eigentum im Objekt läuft; nach einem Eigentümerwechsel entfällt der Zugang mit der nächsten Neuableitung der Zugriffsrechte. Angezeigt werden nur Abrechnungen des eigenen Rechtsträgers. Abrechnungen, deren Rechtsträger die Gemeinschaft selbst ist, sehen deren Eigentümer nur, wenn die Verwaltung den Schalter "Abrechnungen der Gemeinschaft als Vermieterin im Eigentümerportal" einschaltet (Standard aus, Entscheidung AF25-02 offen).

## Abgrenzung zum CRM-Handbuch (AG13)

Dieses Kapitel beschreibt ausschließlich die Anwendung `apps/web-portal` für Mieter, Eigentümer, Beirat und Dienstleister. Einstellungen, die die Verwaltung im CRM vornimmt (Fachliche Regeln, Portalfunktionen, Textbausteine, Freigabestufen), stehen in den CRM-Kapiteln, vor allem Einstellungen und Plattform, und sind hier nur dort erwähnt, wo sie das Portal sichtbar steuern. Das Demo-Band und die API-Schlüssel-Seite gehören zum CRM und erscheinen im Portal nicht.

## Aufträge bewerten (AG06)

Nach Abschluss eines Auftrags kann der betroffene Bewohner in der Meldung unter Auftrag bewerten Sterne (1 bis 5) und eine Anmerkung abgeben, einmalig; ebenso die Verwaltung auf der Auftragsseite im CRM. Die Bewertungen sind intern und werden dem Dienstleister nie gezeigt. Wer sie sieht, steuert die Verwaltung unter Einstellungen, Bewertungen von Dienstleistern: aus (Standard), nur Verwaltung oder zusätzlich der Durchschnitt des Dienstleisters für Bewohner. Regel `docs/rules/AG06-01.md`.

## Belegeinsicht für Eigentümer (AG09)

Unter Einstellungen, Fachliche Regeln, Schalter "Belegeinsicht im Eigentümerportal" einschalten (Standard aus, zusätzlich Freigabestufe G4). Eigentümer finden die Seite "Belegeinsicht" im Portal, filtern nach Abrechnungsjahr und Bezeichnung und laden Belege herunter, für die sie nach der Dokumentberechtigung zugelassen sind. Jeder Abruf wird als Indiz vermerkt. Hinweis: Die Einsicht in Kostenbelege ist eine Entscheidung der Verwaltung, vor dem Einschalten mit Datenschutz und Gemeinschaftsordnung abstimmen.

## Umlaufbeschlüsse (AG07)

Unter Umlaufbeschlüsse sehen Eigentümer laufende Umlaufverfahren ihrer Gemeinschaft und stimmen je eigener Einheit und Beschlussantrag einmal mit Ja, Nein oder Enthaltung ab. Nach der Stimmabgabe zeigt die Seite Zeitpunkt und Prüfsumme des Beschlusstexts als Nachweis. Die Funktion ist nur aktiv, wenn die Verwaltung den Schalter Umlaufbeschluss im Eigentümerportal eingeschaltet hat und die Freigabestufe G4 offen ist. Das Ergebnis stellt die Verwaltung im CRM fest; dort erscheinen die Portalstimmen lesend im Formular Umlaufbeschluss erfassen.

## Reporting für Kapitalanleger (AG08, GAF-34)

Eigentümer mit Sondereigentumsverwaltung sehen unter Reporting je Einheit und Abrechnungszeitraum die vereinbarte Monatsmiete, die auf Mieter umlagefähigen Kosten, die Leerstandstage und den Leerstandsanteil des Objekts. Die Seite ist nur sichtbar gefüllt, wenn der Mandantenschalter "Mieterträge im Portal" (owner_rental_income_enabled) eingeschaltet und die Freigabestufe G3 offen ist; sonst erscheint ein Hinweis. Mieternamen und Zahlungsstatus werden nicht angezeigt.

## SEPA-Lastschriftmandat erteilen (GAH-309)

Mieter und Eigentümer mit Vertrag erteilen unter Lastschrift (`/lastschrift`) der Verwaltung ein SEPA-Lastschriftmandat für wiederkehrende Zahlungen. Ablauf:

1. Vertrag wählen. Mit "Mandatstext anzeigen" erscheinen Gläubiger-Identifikationsnummer, Mandatsreferenz und die Zahlungsart "wiederkehrende Zahlung".
2. Kontoinhaber (Vor- und Nachname) und IBAN eingeben, die BIC ist optional. Die IBAN wird auf Gültigkeit geprüft.
3. Die Bestätigung "Ich bin Kontoinhaber und erteile das oben stehende SEPA-Lastschriftmandat" setzen und "Mandat erteilen" wählen.

Das Mandat wird nur als Vorschlag übermittelt. Es steht unter "Ihre Mandate" mit dem Status "in Prüfung", wird nach Prüfung und Freigabe durch die Verwaltung "übernommen" oder "abgelehnt". Der Textform-Nachweis liegt als PDF unter Dokumente. Erst ein übernommenes Mandat kann die Verwaltung verwenden; Einzüge löst das Portal nicht aus, sie bleiben hinter der Freigabestufe für Zahlungsausgang (G2) und der Freigabe der Verwaltung.

Häufige Rückfragen: Fehlt die Seite oder ist die Vertragsliste leer, hat das Konto keinen Vertrag; dann in der Kontaktakte im CRM den Portalzugang und die Verträge prüfen.

## Passkeys als zweiter Faktor (GAH-309)

Unter Sicherheit können Portalnutzer Passkeys (Fingerabdruck, Gesichtserkennung, Gerätesperre oder Sicherheitsschlüssel) als zweiten Faktor registrieren. Ein Passkey ersetzt bei der Anmeldung den Code der Authenticator-App, das Passwort bleibt erforderlich; es gibt keine Anmeldung allein per Passkey.

* **Registrieren:** Unter Sicherheit im Abschnitt "Passkeys (zweiter Faktor)" eine Bezeichnung eingeben (zum Beispiel "Handy privat"), "Passkey hinzufügen" wählen und die Abfrage des Geräts bestätigen. Danach erscheint der Passkey in der Liste.
* **Anmelden:** Bei der Anmeldung steht "Passkey verwenden" zur Wahl; der Code der Authenticator-App bleibt als Weg erhalten.
* **Entfernen:** In der Liste "Entfernen" wählen. Geht ein Gerät verloren, den Passkey von einem anderen Gerät aus entfernen; bei Problemen die Verwaltung ansprechen.
* **Nicht sichtbar oder nicht nutzbar:** Zeigt die Seite "Passkeys sind nicht freigeschaltet", ist die Funktion für den Mandanten nicht aktiv. Meldet der Browser "Dieser Browser unterstützt keine Passkeys", hilft ein aktueller Browser mit HTTPS-Zugang.

## Reporting für Kapitalanleger: warum die Seite leer bleibt (GAH-311)

Die Seite Reporting (`/reporting`) zeigt nur dann Zahlen, wenn zwei Bedingungen zugleich erfüllt sind:

1. Der Mandantenschalter "Mieterträge im Portal" (`owner_rental_income_enabled`) ist eingeschaltet. Er steht im CRM unter Einstellungen, Fachliche Regeln, und ist im Standard aus.
2. Die Freigabestufe G3 (Mietabrechnungen) ist für den Mandanten geöffnet. Solange sie geschlossen ist, erscheint der Hinweis zur Sperre statt der Zahlen.

Bleibt die Seite leer oder zeigt nur den Hinweis, zuerst Schalter und Freigabestufe prüfen, danach, ob dem Eigentümer eine Einheit mit Sondereigentumsverwaltung zugeordnet ist. Nicht-Eigentümer sehen den Hinweis "nur für Eigentümer". Die Seite enthält weder Mieternamen noch Zahlungsstatus; sie ersetzt keine Abrechnung.

## Sicherheit: Passwort ändern und aktive Sitzungen

Unter Sicherheit ändern Portalnutzer ihr Passwort: aktuelles Passwort, neues Passwort und
Wiederholung eingeben, dann Passwort ändern wählen. Danach enden alle Sitzungen des Kontos,
auch auf anderen Geräten; die Anmeldung erfolgt mit dem neuen Passwort.

Die Liste Aktive Sitzungen zeigt Gerät oder Browser, Beginn und letzte Aktivität jeder
Sitzung. Mit Sitzung beenden wird eine unbekannte oder nicht mehr benötigte Sitzung sofort
widerrufen. Anmeldungen, Fehlversuche, Sperren, Passwortänderungen und beendete Sitzungen
werden im Protokoll der Verwaltung festgehalten, ohne Passwörter oder Codes.

Ist der zweite Faktor verloren (Smartphone verloren), kann die Verwaltung ihn nur zurücksetzen,
wenn sie das Verfahren freigeschaltet hat (Standard aus); zwei Mitarbeitende müssen zustimmen.

## Zählerstand mit Foto melden (GAJ-401)

Unter Zählerstand melden fügen Sie ein Foto des Zählers bei, über die Dateiauswahl oder direkt mit der Kamera (Schaltfläche Foto aufnehmen). Das Foto wird ohne Aufnahmedaten gespeichert und dient der Verwaltung als Ablesebeleg. Ohne Foto erscheint ein Hinweis; die Meldung bleibt möglich und wird für die Verwaltung als ohne Foto gekennzeichnet. Übernimmt die Verwaltung den Stand, bleibt das Foto am Zählerstand verknüpft.

## Fotos direkt mit der Kamera (GAJ-404)

Bei der Schadensmeldung und bei den Ausführungsfotos des Dienstleisters öffnet die Schaltfläche Foto aufnehmen auf dem Smartphone direkt die Kamera. Die Dateiauswahl bleibt daneben erhalten.

## Stand der Aufträge zur Meldung (GAJ-402)

In der Einzelansicht einer Meldung zeigt der Abschnitt Stand der Aufträge den laufenden Status jedes Auftrags (angefragt, beauftragt, terminiert, in Ausführung, ausgeführt usw.) und den Termin. Dienstleister, Preise und interne Vermerke werden nicht angezeigt; Aufträge im Entwurf bleiben intern.

## Einsichtsanfrage im Eigentümerportal (GAJ-202)

Auf der Seite Belegeinsicht stellen Eigentümer eine Anfrage auf Einsicht in die Verwaltungsunterlagen ihrer Gemeinschaft (Umfang Abrechnung, Belege, Verträge, Beschlüsse oder eine Beschreibung) und sehen den Stand ihrer Anfragen. Die Anfrage geht in die Einsichtsanfragen des CRM; Freigabe, Bereitstellung und Ablehnung bleiben bei der Verwaltung. Die Funktion erscheint nur, wenn die Verwaltung den Schalter der Belegeinsicht (Portalverwaltung, Funktionen) eingeschaltet hat. Interne Vermerke der Verwaltung sind im Portal nicht sichtbar.

## Fotopflicht beim Zählerstand einstellen (AN02)

Unter Einstellungen, Portalformulare legen Sie mit "Foto beim Zählerstand" fest, ob beim Melden eines Zählerstands ein Foto erwartet wird: kein Foto erwartet, Hinweis bei fehlendem Foto (Standard) oder Foto ist Pflicht. Bei Pflicht lehnt das Portal eine Meldung ohne Foto ab. In der Vorschlagsprüfung am Kontakt sehen Sie zu jeder Zählerstandsmeldung die beigefügten Fotos als Link zur Dokumentansicht und den Vermerk, wenn kein Foto beigefügt wurde. Die Entscheidung über eine Fotopflicht liegt beim Betreiber (AM06-01).
