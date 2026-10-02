# Einstellungen

## Zweck

Einstellungen bündelt alles, was den Mandanten und seinen Betrieb betrifft: Benutzer,
Rollen, Postfächer, DMS- und Google-Verbindung, SLA, KI, Immoware24-Anbindung, Bank,
Ticketvorlagen, Antwortvorlagen, Automatisierung, Telefonie, Portalformulare, WEG
(Mehrheitsregeln) und Buchhaltung, DATEV. Änderungen an Mandanteneinstellungen verlangen
das Recht Mandanteneinstellungen ändern; ohne dieses Recht sind die Seiten nur lesbar.

## Rechtsträger der verwaltenden Gesellschaft

Unter Einstellungen, Mandant zeigt die Karte "Rechtsträger der verwaltenden Gesellschaft",
ob die verwaltende Gesellschaft (zum Beispiel die Hausverwaltung Müller GmbH) einen eigenen
Rechtsträger mit Buchungskreis besitzt (Status eingerichtet oder nicht eingerichtet). Die
Schaltfläche "Rechtsträger und Buchungskreis einrichten" legt beides einmalig an: den Namen
aus den Firmendaten des Mandanten, den Buchungskreis mit den Standardkonten der Kontenvorlage.
Ein erneuter Klick ändert nichts. Der eigene Buchungskreis nimmt eigene Forderungen der
Verwaltung auf (Verwalterhonorar, Rechnungsentwürfe über Mahngebühren an Gemeinschaft oder
Vermieter) und bleibt von den Buchungskreisen der verwalteten Gemeinschaften und Eigentümer
getrennt. Die Einrichtung erfordert das Recht Mandanteneinstellungen ändern; Buchungen in
diesem Buchungskreis bleiben wie überall hinter G1.

## Benutzer und Kompetenzen

Unter Benutzer und Rollen werden Konten angelegt, Rollen zugewiesen und Kompetenzen
(Zuständigkeiten für die automatische Ticketzuweisung) gepflegt. Benutzerkonten werden
nie gelöscht, sondern gesperrt oder wieder aktiviert, damit die Nachvollziehbarkeit
gewahrt bleibt. Passwort zurücksetzen erzeugt ein Startpasswort, das persönlich zu
übergeben ist; der Benutzer sollte es unter Meine Daten selbst ändern.

Freigabepflicht für Ticketantworten (Betreiberentscheidung vom 26.09.2026): Je Benutzer kann
mit dem Recht Mandanteneinstellungen ändern das Kennzeichen Freigabepflicht gesetzt werden,
mit Grund Azubi oder neuer Mitarbeiter und optional befristet bis zu einem Datum
(einschließlich). Antworten aus dem Ticket dieser Benutzer gehen als Vorlage an alle übrigen
Freigabeberechtigten und werden erst nach Freigabe durch eine zweite Person versendet.
Benutzer ohne Kennzeichen, die das Recht Kommunikation freigeben haben, versenden ihre
Ticketantworten direkt. Jede Änderung des Kennzeichens wird im Ereignisprotokoll mit Benutzer
festgehalten. Unter Mandant und Briefbogen steht zusätzlich die Notbremse Ticketantworten:
Freigabe für alle (Standard aus): Ist sie an, brauchen alle Ticketantworten des Mandanten die
Freigabe einer zweiten Person, unabhängig vom Kennzeichen.

## Objektzuordnung je Benutzer

Unter Einstellungen, Benutzer legt die Mandantenadministration je Mitglied fest, welche
Objekte es sehen darf (Schaltfläche Objekte). Ohne Auswahl sieht das Mitglied alle Objekte.
Mit Auswahl ist es auf die gewählten Objekte beschränkt; Administratorrollen sind nie
eingeschränkt. Die Zuordnung wird protokolliert und wirkt auf Objekte, Einheiten, Verträge,
Tickets, Dokumente und Eingangsrechnungen: Listen zeigen nur Einträge der zugeordneten
Objekte, fremde Datensätze erscheinen als nicht gefunden. Tickets und Rechnungen ohne
Objektbezug sieht ein eingeschränktes Mitglied nicht. Seit 01.10.2026 gilt die Zuordnung
auch für Bankkonten, Bankumsätze und Zahlungsaufträge, Betriebskosten- und
Eigentümerabrechnungen, die WEG-Bereiche (Versammlungen, Beschlüsse, Wirtschaftspläne,
Hausgeldabrechnungen, Sonderumlagen, Darlehen, Maßnahmen, Einsichtsanfragen), die
Auswertungen der Buchungskreise, Dienstleisterverträge, die globale Suche und die
Nachschlagewerkzeuge des Assistenten. Zusätzlich gilt sie für die Portalverwaltung
(Portalzugänge und Einladungen nur für Kontakte mit einem Vertrag auf einem zugeordneten
Objekt), die Objektakte je Objekt (Vollständigkeit, Listen, Abgabeexporte), die
Migrationsimporte und Altdaten (Abgleichberichte, Abnahmeprotokolle, Buchungskreise,
historische Tickets und Einzelposten), die Prüfberichte des Beirats, die Bankregeln und
Regelvorschläge, das Sync-Protokoll, die Klärungsliste und die Zuordnung eines Bankkontos zu
einem Objekt (nur zugeordnete Ziele). Kontakte und Kataloge bleiben mandantenweit (Regel
M2-02). Eine Änderung wirkt ab der nächsten Anfrage.

## Gleichzeitiges Bearbeiten über die Schnittstelle

Verträge (Bemerkungen und Mahnsperre), Tickets, Dokumente und Eingangsrechnungen liefern
beim Lesen einen Änderungsstand (ETag). Sendet ein Programm diesen Stand beim Speichern mit
(If-Match) und hat inzwischen jemand anderes gespeichert, wird die Änderung abgelehnt und
muss nach dem Neuladen wiederholt werden. Ohne diesen Stand wird wie bisher gespeichert. Die
Oberfläche merkt sich seit 01.10.2026 den Stand beim Öffnen eines Vertrags, Tickets,
Dokuments oder einer Rechnung und sendet ihn beim Speichern mit. Hat inzwischen jemand anderes
gespeichert, erscheint die Meldung "Der Datensatz wurde zwischenzeitlich geändert. Bitte die
Seite neu laden und die Änderung erneut vornehmen." Nach anderen Aktionen am Datensatz
(Kommentar, Statuswechsel, Verknüpfung) speichert die Oberfläche bis zum nächsten Laden ohne
Abgleich, damit kein falscher Konflikt entsteht.

## Passkeys

Unter Meine Daten, Abschnitt Passkeys, registriert jeder Benutzer eigene Passkeys
(Regel S16-01). Ein Passkey dient bei der Anmeldung als zweiter Faktor anstelle des Codes der
Authenticator-App. Mit dem Haken "Anmeldung ohne Passwort erlauben" kann ein Passkey im CRM
zusätzlich die Anmeldung ohne Passwort ermöglichen (Schaltfläche "Mit Passkey anmelden" auf
der Anmeldeseite); das Gerät verlangt dann PIN oder Biometrie. Im Portal gibt es Passkeys nur
als zweiten Faktor. Passkeys lassen sich jederzeit entfernen. Die Funktion erscheint erst,
wenn der Betreiber sie freigeschaltet hat; bis dahin dient TOTP als zweiter Faktor.

## Erledigungsarten beim Ticketabschluss

Unter Mandant und Briefbogen, Abschnitt Erledigungsarten, legt der Mandant fest, welche Arten
der Abschlussdialog der Tickets anbietet (Betreiberentscheidung vom 26.09.2026, Kapitel
Tickets, Erledigungsnotiz beim Abschluss). Eingebaute Arten: Stammdaten ergänzt, Handwerker
beauftragt, Auskunft erteilt, Weitergeleitet, Kein Handlungsbedarf, Abgelehnt, Zahlung
geklärt, Termin vereinbart, Mangel behoben, Vertrag geändert, Zusammengeführt, Sonstiges.
Jede eingebaute Art lässt sich per Haken abschalten, außer Sonstiges (Auffang mit
Freitextpflicht) und Zusammengeführt (Standard beim Zusammenführen). Eigene Arten, höchstens
30, bestehen aus einem Code (Kleinbuchstaben, Ziffern, Unterstrich, 2 bis 32 Zeichen, zum
Beispiel schluessel_uebergeben) und einer Bezeichnung; der Code ist die technische Kennung im
Verlauf, in Lernbeispielen und in der API und lässt sich nachträglich nicht ändern. Das
Entfernen einer Art ändert bereits abgeschlossene Tickets nicht; ihre Art bleibt im Verlauf
lesbar. Die Pflege erfordert das Recht Mandanteneinstellungen ändern; jede Änderung steht im
Ereignisprotokoll (Mandanteneinstellungen geändert, Feld resolution_kinds).

## Meine Daten: Passwort, zweiter Faktor, Geräte

Unter Meine Daten (Benutzermenü oben rechts) ändert jeder Benutzer sein Passwort (12 bis 128
Zeichen, kein bekanntes kompromittiertes Passwort, aktuelles Passwort erforderlich,
Betreiberentscheidung 9 a vom 30.09.2026, Regel M2-05) und
verwaltet den zweiten Faktor: Zweiten Faktor einrichten zeigt einen QR-Code und den Schlüssel
für die Authenticator-App; erst nach Bestätigen mit einem gültigen Code ist der zweite Faktor
aktiv, danach fragt die Anmeldung nach dem Passwort zusätzlich den Code ab. Zweiten Faktor
ausschalten verlangt das aktuelle Passwort und entfernt alle gemerkten Geräte. Ob der zweite
Faktor Pflicht ist, legt die Richtlinie des Mandanten fest (Abschnitt Zweiter Faktor je Rolle);
unter der Pflicht lässt er sich nicht ausschalten, solange kein Passkey eingerichtet ist.

Gemerkte Geräte: Wer beim Code-Schritt Dieses Gerät 90 Tage merken wählt, wird auf diesem
Gerät 90 Tage lang ohne Code angemeldet. Die Liste zeigt Gerät (Browserkennung) und Ablauf;
Abmelden entfernt das Gerät sofort, ebenso das Ausschalten des zweiten Faktors und ein
Passwort zurücksetzen durch die Administratorin oder den Administrator. Aktive Sitzungen
lassen sich daneben einzeln beenden.

## Rollen und Portalrechte

Unter Rollen und Rechte werden Rechte je Rolle vergeben; Systemrollen lassen sich nicht
ändern. Die Matrix Portalrechte je Rolle bestimmt zusätzlich, welche Portalfunktionen der
Mitarbeiterzugang einer Rolle im Portal sieht (siehe Kapitel Portal). Nur Benutzer mit
dem Recht Mandanteneinstellungen ändern dürfen diese Matrix speichern.

## Zweiter Faktor je Rolle

Unter Einstellungen, Rollen und Rechte legt der Abschnitt Zweiter Faktor je Rolle fest, wer
sich mit einem zweiten Faktor (TOTP-App oder Passkey) anmelden muss (Regel M2-04):

- Freiwillig (Standard): jeder Benutzer entscheidet selbst, ob er einen zweiten Faktor
  einrichtet (Betreiberentscheidung M2-01). Ohne gespeicherte Richtlinie gilt diese Variante,
  niemand wird zur Einrichtung gezwungen.
- Pflicht für alle CRM-Rollen: jede Rolle außer dem Portalzugang. Das ist eine Wahl des
  Mandanten.
- Pflicht nur für ausgewählte Rollen: Pflicht nur für die angekreuzten Rollen.
- Auch für Portalzugänge vorschreiben: erstreckt die Pflicht auf Mieter, Eigentümer und
  Dienstleister im Portal (Standard aus).

Wählt der Mandant eine Pflicht, wirkt sie bei der nächsten Anmeldung, niemand wird ausgesperrt: Wer noch keinen
zweiten Faktor hat, sieht nach dem Passwort die Seite Zweiten Faktor einrichten mit QR-Code
und Schlüssel, bestätigt mit dem ersten Code aus der App und ist danach angemeldet. Laufende
Sitzungen bleiben bestehen. Lesen verlangt das Recht Mandanteneinstellungen lesen, Speichern
das Recht Mandanteneinstellungen ändern. Ist der Faktor Pflicht, zeigt Meine Daten einen
Hinweis statt Zweiten Faktor ausschalten.

## Löschen nur Administrator

Löschende Aktionen (zum Beispiel eine SLA-Regel, ein Kontakt endgültig oder ein
Übergabeprotokoll) sind an das jeweilige Recht `...:delete` gebunden. In der
Vorbelegung führt nur die Rolle Administrator dieses Recht. Wer eine löschende Aktion
nicht ausführen kann, meldet sich an die Administratorin oder den Administrator des
Mandanten.

## Postfächer

Google-OAuth-Client des Mandanten, verbundene Postfächer, Standardpostfach und Freigabe
je Benutzer. Postfächer werden nur gelesen; jede neue Mail erzeugt ein Ticket. Ein
Standardpostfach sehen alle Benutzer des Mandanten, auch neu angelegte. Kalenderfreigabe
je Postfach verlangt nach der ersten Aktivierung ein erneutes Verbinden mit Google, damit
der Kalender-Scope erteilt wird (siehe Kapitel Kalender).

Telefonassistenz (Hallo Heidi): Auf derselben Seite wird je Mandant eingestellt, ob
Gesprächsprotokolle der KI-Telefonassistenz als Anruf erkannt werden, mit welchen
Absendermustern (Teil der Absenderadresse, durch Komma getrennt; Standard hallo-heidi,
halloheidi, hallo.heidi) und mit welchen Kennwörtern im Betreff (Standard hallo heidi). Leere
Felder bedeuten die Standardwerte. Die Wirkung im Ticket beschreibt das Kapitel Tickets,
Abschnitt Anrufe über die Telefonassistenz.

## DMS und Google-Verbindung

Unter DMS-Anbindung werden Paperless-Zugangsdaten (Basis-URL, API-Token, Feld-IDs für
Objektnummer und Gesellschaft) und die Google-Drive-Anbindung gepflegt. Mit Google
verbinden öffnet die Google-Anmeldung und hinterlegt Client-Secret und Refresh-Token
automatisch; ohne hinterlegten OAuth-Client (Einstellungen, Postfächer) ist das nicht
möglich. Alternativ lassen sich Client-ID, Client-Secret und Refresh-Token manuell
eintragen (Manuell hinterlegen).

Für Paperless zusätzlich: das Webhook-Geheimnis für den Post-Consume-Webhook (mindestens
16 Zeichen, nur schreibbar, wird nie wieder angezeigt; leer lassen, um es zu behalten) und
der Schalter Belegeingang aus Paperless automatisch (Standard aus). Ohne Geheimnis weist
der Endpunkt jede Meldung ab. Details im Kapitel Belegeingang.

## SLA mit Vorschlagswerten

Unter SLA und Bereitschaft: Regeln je Priorität (Reaktions- und Lösungszeit,
Geschäftszeit oder Kalenderzeit), Eskalationsstufen mit Kanälen je Stufe (Standard Stufe
1 intern, Stufe 2 intern und E-Mail, Stufe 3 zusätzlich SMS), Bereitschaftsplan,
Geschäftszeitenkalender und Notfallalarme. Vorschlagswerte laden legt fehlende Regeln je
Priorität als Vorschlag an; dies ist Produktschutz, keine Rechtsvorschrift, und ersetzt
keine Prüfung durch die Geschäftsführung. Eine Regel braucht zwingend einen Namen; ohne
Namen lässt sich Speichern nicht abschließen.

## SMS und WhatsApp Hinweis

Der Kanal SMS läuft über ein anbieterneutrales HTTP-Gateway je Mandant (Reiter
SMS-Gateway, mit Testnachricht). Ein WhatsApp-Kanal ist zum Stand dieses Handbuchs nicht
umgesetzt; sofern eine Anfrage WhatsApp erwähnt, ist dies als offener Punkt zu behandeln
und nicht als vorhandene Funktion zu bestätigen.

## KI und Wissensbasis

Unter KI werden Anbieter (Anthropic oder OpenAI), Modelle je Stufe, Monatsbudget und
Datenschutzangaben (Auftragsverarbeitungsvertrag, Trainings-Opt-out) gepflegt. Jede
Änderung hebt eine bestehende Freigabe auf; die Freigabe muss eine andere Person
erteilen als die, die zuletzt gespeichert hat (Vier-Augen-Prinzip). Ist das
Monatsbudget ausgeschöpft, werden neue KI-Aufträge gesperrt.

Je Stufe (klein, groß) lässt sich zusätzlich die Ausgabegrenze des Modells laut Anbieter
eintragen (Token je Antwort). Bleibt das Feld leer, gilt der Standard 16000. Der Wert wird bei
jedem Aufruf als Obergrenze mitgegeben; ein zu hoher Wert wird vom Anbieter abgewiesen, ein zu
niedriger führt bei umfangreichen Listen zu abgeschnittenen Antworten, die die Plattform durch
Aufteilen der Daten abfängt.

Mit "Verbindung testen" schickt die Plattform je eingerichteter Stufe einen Minimalprompt an den
Anbieter und zeigt je Stufe Status, Modellname, Antwortzeit und bei Fehlern die Meldung des
Anbieters. Der Test benötigt einen hinterlegten Schlüssel und die gespeicherte Konfiguration,
setzt aber keine Freigabe voraus, erteilt keine und hebt keine auf. Die minimalen Kosten werden
dem Monatsbudget belastet und erscheinen im Verbrauch. Die Embedding-Stufe wird nicht getestet.

Die KI-Wissensbasis (Kapitel
Mail, Abschnitt Vorbereitung) wird je Mandant und optional je Objekt unter KI,
Wissensbasis gepflegt: Ablageregeln, Arbeitsweisen, Fakten und aus Korrekturen gelernte
Einträge, filterbar je Objekt.

## Wissen (gelernte Playbooks und Lernbeispiele)

Die Seite Einstellungen, Wissen (seit 1.24.0, Recht Mandanteneinstellungen lesen) zeigt in
zwei Reitern, was die Plattform aus abgeschlossenen Vorgängen gelernt hat. Reiter Playbooks:
gelernte Playbooks mit Trefferzahl und Letzte Nutzung; Deaktivieren (Recht Kommunikation
ändern) nimmt ein Playbook aus den Vorschlägen, ohne es zu löschen; die Bearbeitung des Textes
erfolgt weiterhin unter Mail, Playbooks. Reiter Lernbeispiele: die gespeicherten Beispiele mit
Filter nach Aufgabe (zum Beispiel Erledigung eines Tickets oder bestätigte Vorschläge), jeweils
mit Eingabe und Ergebnis. Lernbeispiele werden nicht von Hand angelegt; sie entstehen beim
Abschluss eines Tickets (Kapitel Tickets, Lernen aus Erledigungen). Alles auf dieser Seite ist
Vorschlagsgrundlage, keine Freigabe und keine Buchung.

## Automatischer Belegeingang

Unter DMS-Anbindung, Karte Automatischer Belegeingang: Schalter Rechnungen aus neuen
E-Mails automatisch erfassen (Standard aus). Aktiv startet je neuem PDF-Anhang mit
Rechnungsmerkmal beim Postfachabruf genau eine KI-Extraktion als Belegentwurf; nichts wird
gebucht, jede Extraktion belastet das KI-Monatsbudget (Kapitel Belegeingang).

## Telefonie

Unter Telefonie wird der anbieterneutrale Telefonie-Webhook eingerichtet: Webhook aktiv,
Anbieter oder Anlage (freie Bezeichnung), Geheimnis (HMAC, mindestens 16 Zeichen, wird
einmal gespeichert und nie wieder angezeigt; leer lassen, um es zu behalten). Die Seite
zeigt den Endpunkt, den die Telefonanlage aufruft. Ohne Geheimnis lässt sich der Webhook
nicht aktivieren. Es werden keine Gesprächsinhalte angenommen; Rufnummern erscheinen nur
mit dem Recht Kontakte lesen unmaskiert. Anbieterwahl und Auftragsverarbeitung sind
Betreiberentscheidung (M23-06). Anrufliste und Rückruf-Vorschlag: Kapitel Kommunikation.

## Portalformulare

Unter Portalformulare werden Formularvorlagen für das Portal gepflegt: Name, Hinweistext
im Portal, Ticketkategorie (Kategorie des Tickets, das aus einer Einreichung entsteht),
Zielgruppe (Mieter und Eigentümer, Nur Mieter, Nur Eigentümer), Reihenfolge und Felder
(Feldtyp Text, Zahl, Datum, Auswahl mit Optionen, Datei; je Feld Pflicht). Aktivieren und
Deaktivieren steuern die Sichtbarkeit im Portal; Vorlagen mit Einreichungen lassen sich nur
deaktivieren, nicht löschen. Jede Einreichung wird ein Ticket mit Anhängen (Kapitel Portal,
Formulare).

## Automatisierung

Unter Automatisierung werden Regeln der Regel-Engine (Auslöser Ereignis oder Zeitplan,
Bedingungen, Aktionen, Testlauf, Protokoll) gepflegt. Regeln lösen keine Buchungen,
Zahlungen, Freigaben oder Mailversand aus. Einzelheiten im Kapitel Automatisierung.

## WEG (Mehrheitsregeln)

Unter WEG stehen die Mehrheitsregeln je Beschlussgegenstand mit Fundstelle, Geltung (alle
Gemeinschaften oder eine Gemeinschaft) und Freigabe durch eine zweite Person (Recht
Buchhaltung freigeben). Einzelheiten im Kapitel WEG.

## Kautionszinsen (Referenzzinssatz je Jahr)

Einstellungen, Kautionszinsen: Zinssatz je Kalenderjahr in Prozent (bis fünf
Nachkommastellen, Komma oder Punkt) mit Vermerk für Quelle und Datum. Lesen mit dem Recht
Verträge lesen, Pflege mit dem Recht Mandanteneinstellungen ändern. Ein bestehendes Jahr wird
beim Speichern überschrieben; Entfernen löscht den Satz für das Jahr.

Die Tabelle ist die einzige Grundlage der Kautionsabrechnung mit Zinsart Referenzzinssatz je
Jahr (Kapitel Verträge). Die Plattform bezieht keinen Zinssatz automatisch und belegt keinen
Wert vor. Welcher Satz für Mietkautionen rechtlich maßgeblich ist, ist durch Rechtsberatung
zu bestätigen; die Fundstelle gehört in den Vermerk.

## Fristtypen

Einstellungen, Fristtypen (Lesen mit `tenant_settings:read`, Pflege mit `tenant_settings:update`).
Je Fristtyp: Bezeichnung, Code, Auslöser (Zugang der Kündigung, Übergabe erfolgt, Zugang des
Mieterhöhungsschreibens, Verwaltungsbeginn, Verwaltungsende, Vertragsende oder Datum wird
eingetragen), Dauer in Monaten und Tagen, verantwortliche Rolle, Quelle der Dauer, Aktiv. Die
Systemtypen Verwalterwechsel, Kautionsabrechnung und Mieterhöhung sind ohne Dauer angelegt. Die
Software gibt keine Dauer vor und trifft keine Rechtsaussage; jede berechnete Fälligkeit trägt
den Hinweis zu verifizieren. Dauer nur nach rechtlicher Prüfung eintragen und die Quelle
vermerken (offener Punkt WS-01-Q1). Ein Typ ohne Dauer verlangt beim Anlegen der Frist die
Eingabe der Fälligkeit. Deaktivierte Typen stehen beim Anlegen nicht mehr zur Auswahl.

## Buchhaltung, DATEV

Unter Buchhaltung, DATEV wird die DATEV-Kontenzuordnung gepflegt (Recht Buchhaltung
ändern; sonst nur Ansicht): CRM-Konto zu DATEV-Sachkonto mit Bezeichnung, Buchungskreis
(oder alle Buchungskreise) und Gültig ab, Aktivieren und Deaktivieren. Es ist kein
Kontenrahmen vorbelegt; jede Zuordnung wird nach Abstimmung mit dem Steuerberater
eingetragen. Import aus CSV (Kopfzeile mit account_code, datev_account, optional label und
valid_from) mit Vorschau (neu, ändern, unverändert, Fehler je Zeile) und Übernehmen. Der
Prüfbericht nicht zugeordneter Konten zeigt je Buchungskreis und Zeitraum Konten mit
Buchungen ohne Zuordnung; diese blockieren den DATEV-Buchungsstapel-Export. Der Export
selbst bleibt wie die produktive Buchführung hinter G1 (Kapitel Buchhaltung).

## Immoware24-Verbindung und Diagnose

Immoware24 bleibt Master der Stammdaten; die Plattform liest ausschließlich per WebDAV,
CardDAV und CalDAV, es gibt keinen Schreibpfad Richtung Immoware24. Unter
Immoware24-Anbindung werden Zugangsdaten und Abrufintervall hinterlegt. Verbindung prüfen
zeigt Erfolgreich oder Fehlgeschlagen mit Zeitpunkt der letzten Prüfung. Dokumente,
Kontakte und Termine jeweils jetzt abrufen löst einen sofortigen Lauf aus; die Liste der
letzten Läufe zeigt je Lauf Start, Ende, Status sowie gesehene, neue, geänderte und
entfernte Datensätze zur Fehlerdiagnose.

## Häufige Fehler

- **KI-Freigabe verschwindet nach dem Speichern**: Gewollt, jede Änderung hebt die
  Freigabe auf; eine zweite Person muss erneut freigeben.
- **SLA-Regel lässt sich nicht speichern**: Feld Name ist leer; ein Name ist Pflicht.
- **Google Drive lässt sich nicht verbinden**: Kein OAuth-Client hinterlegt; zuerst unter
  Postfächer den OAuth-Client eintragen.
- **Immoware24-Verbindung meldet Fehlgeschlagen**: Zugangsdaten, Basis-URL oder
  TLS-Prüfung stimmen nicht; letzte Läufe auf wiederkehrende Fehlermeldung prüfen.

## Buchhaltung, Kontenrahmen

Unter Buchhaltung, Kontenrahmen wird der Kontenrahmen des Mandanten freigegeben (V8). Jede
Version hat den Status Entwurf, zur Prüfung oder freigegeben. Zur Prüfung geben und neue
Version anlegen erfordern das Recht Buchhaltung ändern, die Freigabe das Recht Buchhaltung
freigeben. Im Freigabedialog werden Kommentar und optional die Dokument-ID des
Prüfschreibens der Steuerberatung erfasst; Datum und Freigeber werden protokolliert. Ein
freigegebener Kontenrahmen wird nicht mehr geändert; Änderungen erzeugen eine neue Version
mit erneuter Freigabe. Der Versionsverlauf zeigt alle Versionen. CSV und PDF exportieren den
Kontenrahmen für die Steuerberatung. Die Freigabestufe G1 wird nur mit einem freigegebenen
Kontenrahmen genehmigt.

## Buchhaltung, G1 Öffnung

Unter Buchhaltung, G1 Öffnung steht die Checkliste vor der produktiven Buchführung
(Freigabestufe G1, Öffnungsliste M12-09). Der Stand kommt aus dem System: freigegebener
Kontenrahmen (V8), Zahl der abgenommenen Anhang-D-Fälle, manuelle Prüfpunkte, Automatikstufen
je Fallklasse, Schalter des lernenden Buchhalters und der Stand der Freigabestufe G1 mit
ihren Anträgen. Die Unterlagen `docs/acceptance/kontenrahmen-pruefung.md`,
`docs/acceptance/abnahme-anhang-d.md` und `docs/handbuch/verfahrensdokumentation.md` sind
verlinkt. Je Prüfpunkt (Fall D04 bis D58 mit Stufe G1, Querschnittsfälle D50, D51, D57 und
die manuellen Punkte fachkundige Person, Umsatzsteuerprüfung, Belegkette B05, Mahn- und
Lastschriftausschluss, Löschlauf) trägt eine Person mit dem Recht Buchhaltung freigeben das
Ergebnis bestanden, nicht bestanden oder offen mit Datum und Name ein; ein Test im Code ist
keine Abnahme. Der Antrag auf G1 wird mit dem Recht Freigabestufen beantragen als regulärer
Freigabeantrag gestellt; die Nachweiszeile entsteht aus dem Stand der Seite. Die Entscheidung
trifft eine zweite Person unter Plattform, Freigabestufen (Vier-Augen-Prinzip); ohne
freigegebenen Kontenrahmen wird die Genehmigung mit `MHVP-GATE-0004` abgelehnt. Die Seite
öffnet die Stufe nie selbst.

Seit Welle 16 (AE03) nimmt jeder Prüfpunkt zusätzlich eine verantwortliche Person (Mitglied
des Mandanten) und einen Nachweis auf, entweder als Dokument aus dem DMS oder als Verweis
(Pfad, Aktenzeichen, Fundstelle). Ein bestandener Punkt ohne Nachweis wird mit „Nachweis
fehlt“ markiert; die Seite zählt Punkte ohne verantwortliche Person und ohne Nachweis und
verweist auf die Gate-Checkliste `docs/plans/GATE-CHECKLISTEN.md`, Abschnitt G1.

## Buchhaltung, Automatikstufen: Automatikschalter und Vergleichslauf

Der Automatikschalter des Mandanten lässt sich in der Oberfläche nur einschalten, wenn die
Freigabestufe G1 offen ist: eine Person mit den Rechten Buchhaltung freigeben und
Mandanteneinstellungen ändern stellt einen Antrag mit Grund, eine zweite Person gibt ihn frei
oder lehnt ihn ab. Erst die Freigabe schaltet die Automatik ein; der Lauf prüft Stufen, Regeln
und Gate weiterhin selbst. Solange G1 geschlossen ist, bleibt der Antrag gesperrt.

Der Vergleichslauf zeigt aus dem Entscheidungsspeicher je abgeschlossener Entscheidung, ob der
beste Vorschlag der Automatik der manuellen Buchung entsprochen hätte (Übereinstimmung,
anderer Vorschlag, geändert gebucht, ohne Vorschlag, abgelehnt, automatisch gebucht,
storniert), gesamt und je Fallklasse. Der Bericht bucht nichts und ist kein
Sicherheitsnachweis.

Unter Buchhaltung, DATEV steht zusätzlich die formale Prüfung des Buchungsstapels
(Prüfbericht je Export, Testdatei für den Importtest, Prüfung beliebiger Dateien); siehe
[DATEV-Importtest](datev-importtest.md).

## Lexware Office

Organisationen je Gesellschaft mit API Schlüssel, AVV, Postfach und Schaltern, Zuordnung der
Rechnungsarten, Kontaktabgleich, Warteschlange und vorbereitete Dauerrechnungen unter
Schnittstellen, Lexware Office; siehe [Lexware Office](lexware-office.md).

## Benachrichtigungen (eigene Einstellungen)

Unter Einstellungen, Benachrichtigungen legt jeder Benutzer für sich fest, welche Meldungen in der App
und zusätzlich per E-Mail ankommen. Die Zeile "Alle anderen Arten" gilt für Arten ohne eigene Zeile.
Mit "Stummschalten für" (1 Stunde bis 7 Tage) pausieren App und E-Mail für alle Arten. Verpflichtende
Meldungen (SLA-Eskalation, Fristen zur Vorfrist, ablaufende Bankzustimmung) bleiben immer aktiv und sind
in der Liste gesperrt. Mails zu Benachrichtigungen werden alle paar Minuten gesammelt versendet und
setzen ein eingerichtetes Standardpostfach voraus. Ohne Einstellung gilt: App an, E-Mail aus.

## Neue Einstellungsseiten der Version 1.49.0

### Datenschutz (`/einstellungen/datenschutz`)

Voraussetzung: Recht Datenschutz verwalten, für Freigaben das Recht Datenschutz freigeben. Die Seite
enthält vier Bereiche. Fristen und Profile sind Entwürfe des Betreibers und vor dem produktiven
Einsatz rechtlich zu prüfen.

* Löschprofile: Frist in Monaten und Fristbeginn je Datenart (Kontakte, Portalzugänge, Kommunikation,
  Tickets, Sonstige). Ein Profil gilt erst nach Freigabe; jede Änderung setzt die Freigabe zurück.
  Ohne freigegebenes Profil bleibt jede Löschung gesperrt.
* Löschanträge: Antrag mit Kontakt und Eingangsdatum. Die Sperrprüfung berücksichtigt Löschprofil,
  Aufbewahrungsfrist, Verknüpfungen und Dokumentfristen. Freigabe und Ausführung erfolgen durch eine
  zweite Person. Die Anonymisierung ist nicht umkehrbar, gebuchte Inhalte bleiben unberührt.
* Register: Auftragsverarbeiter, Unterauftragsverarbeiter, Verarbeitungstätigkeiten und
  Verantwortlichkeiten, bei Auftragsverarbeitern mit AVV Status (kein AVV, angefragt, bestätigt,
  nicht erforderlich).

### Dokumentkategorien (`/einstellungen/dokumentkategorien`)

Kategoriebaum mit Zuordnung zu Paperless Dokumenttyp, Paperless Tag und Drive Ordner. Neue Kategorie
mit Kürzel, Bezeichnung und übergeordneter Kategorie anlegen, Zuordnung je Kategorie bearbeiten.
Geänderte Zuordnungen werden an bestehende Spiegel übertragen.

### Teams (`/einstellungen/teams`)

Teams bündeln Mitarbeiter für die Zuweisung von Tickets und Aufträgen. Anlegen, Bearbeiten (Name,
Mitglieder) und Löschen. Ein Team, das Tickets oder Vorlagen zugeordnet ist, kann nicht gelöscht
werden. Ohne das Recht zum Lesen der Benutzer ist die Mitgliederliste nicht verfügbar.

### Benachrichtigungen (`/einstellungen/benachrichtigungen`)

Persönliche Einstellung, gilt nur für das eigene Konto. Je Art der Meldung (zum Beispiel Ticket
zugewiesen, Wartung fällig, Terminerinnerung, Tagesübersicht) wählen Sie, ob sie in der App und per
E-Mail eintrifft. Die Zeile Alle anderen Arten gilt für nicht einzeln aufgeführte Arten. Stummschalten
ist für 1, 8, 24 Stunden oder 7 Tage möglich. Verpflichtende Meldungen zu Fristen, SLA und
Bankzustimmungen bleiben davon unberührt.

### Schadenbearbeiter (`/einstellungen/schnittstellen/schadenbearbeiter`)

Voraussetzung: Recht Mandanteneinstellungen lesen, zum Ändern Recht Mandanteneinstellungen ändern, für die Übernahme Recht Tickets anlegen. Regel INT-SDT-01. Die Seite bindet den externen Schadenbearbeiter an: Schadentickets werden übergeben, Status, Kommentare und Anhänge werden in beide Richtungen abgeglichen.

* Verbindung: Basisadresse und Integrationstoken erzeugt der Schadenbearbeiter in seinem Adminbereich. Das HMAC-Geheimnis für ausgehende Anfragen ist optional. Das Webhook-Geheimnis muss beim Schadenbearbeiter identisch hinterlegt werden, die Webhook-Adresse zeigt die Seite an. Token und Geheimnisse werden verschlüsselt gespeichert und nie wieder angezeigt (nur die letzten vier Zeichen des Tokens).
* Auftragsverarbeitung: Vor dem Aktivieren sind das Datum, ab dem der AVV vorliegt, und optional ein Vermerk einzutragen. Datum und bestätigendes Mitglied werden gespeichert. Der Eintrag ersetzt keine datenschutzrechtliche Prüfung. Ohne AVV lässt sich die Anbindung nicht aktivieren.
* Anbindung aktiv: Standard aus. Ist der Schalter aus, ruft weder eine Nutzeraktion noch ein Job den Schadenbearbeiter auf.
* Verbindung testen und Jetzt abgleichen: zeigen Ergebnis und Zeitpunkt des letzten Tests und Abgleichs. Meldet der Schadenbearbeiter einen ungültigen Token, hält die Warteschlange an, bis ein neuer Token hinterlegt ist.
* Vorhandene Schadentickets übernehmen: Tickets des Schadenbearbeiters ohne Zuordnung stehen in einer Liste mit Vorschlägen für Objekt und Ticket. Die Vorschläge sind nur Vorschläge. Je Ticket wählt ein Mitglied Mit vorgeschlagenem Ticket verknüpfen, Neues Ticket anlegen oder Verwerfen.
* Am Ticket: Das Feld Schadenbearbeiter übergibt das Ticket mit Objektnummer, Titel, öffentlicher Beschreibung und den erfassten Schadendaten. Kommentare und Dokumente verlassen die Plattform nur, wenn sie ausdrücklich gesendet werden. Interne Notizen werden nie übertragen. Der Status des Schadenbearbeiters wird angezeigt und ändert den lokalen Status nicht.

## Benachrichtigungen in der Einstellungsübersicht

Die Eigenen Benachrichtigungseinstellungen (`/einstellungen/benachrichtigungen`) sind jetzt als Kachel in der Einstellungsübersicht erreichbar, nicht mehr nur über die Suche. Der Hauptmenüpunkt Aufträge (`/auftraege`) steht in der Gruppe Verwaltung und erscheint mit dem Leserecht für Tickets.

## Standardfrist für Einsichtspakete

Unter Einstellungen, Mandant legt die Karte Standardfrist für Einsichtspakete fest, wie viele Tage ein Bereitstellungspaket einer Einsichtsanfrage abrufbar bleibt (1 bis 365). Leer bedeutet ohne Ablauf. Die Frist gilt nur für Pakete, die ohne eigene Frist erzeugt werden; bereits erzeugte Pakete behalten ihre Frist. Die Änderung erfordert das Recht Mandanteneinstellungen ändern und wird protokolliert.

## Portal je Mandant

Unter Einstellungen, Mandant legt die Karte Portal der Mandanten den Anzeigenamen sowie die https-Links zu Impressum und Datenschutzerklärung fest. Sie erscheinen im Portal unter der Domain des Mandanten zusammen mit Farben und Logo aus den Briefkopfdaten; leere Felder lassen das Portal neutral. Die Auswahl Anmeldestrenge steht standardmäßig auf Wahl je Konto. Mit der Option E-Mail-Code bei jeder Anmeldung per Link verlangt das Portal bei Anmeldungen per Link immer den Code; die Passwortanmeldung mit TOTP bleibt freiwillig.

## Benachrichtigungen: Zustellung der E-Mail

Unter Einstellungen, Benachrichtigungen wählen Sie je Art, ob die E-Mail sofort (Sammelmail im 5-Minuten-Takt) oder täglich gegen 07:30 Uhr als eine Sammelmail kommt. Die Auswahl ist nur mit gesetztem Kanal E-Mail möglich. Der Versand setzt ein eingerichtetes Standardpostfach voraus.

## Vollständiger Mandantenexport

Unter Einstellungen, Mandant starten Sie als Mandantenadministrator mit Export starten einen Gesamtexport aller Mandantendaten (JSON je Tabelle plus Dokumentdateien als ZIP). Der Export läuft im Hintergrund, mit Aktualisieren sehen Sie den Status. Ist er fertig, laden Sie das ZIP herunter. Start und Abruf werden protokolliert. Das Archiv enthält personenbezogene Daten und ist sicher aufzubewahren, siehe docs/rules/P14-06.md.

Aufbewahrung der Exportarchive: Direkt darunter legen Sie unter Aufbewahrung der Exportarchive die Dauer in Tagen fest (1 bis 3650). Leer bedeutet, dass kein Archiv automatisch gelöscht wird (Standard). Ist eine Dauer gesetzt, löscht ein täglicher Lauf (03:50 Uhr) abgelaufene Archive aus dem Objektspeicher und setzt den Export auf Abgelaufen, Archiv gelöscht. Der Eintrag mit Größe, Prüfsumme und Abrufzähler bleibt als Nachweis, ein Abruf des gelöschten Archivs ist nicht mehr möglich (Antwort 409). Die Frist läuft ab Fertigstellung; eine spätere Änderung wirkt auch auf fertige Archive ohne Ablaufdatum. Jede Änderung und jede Löschung wird protokolliert. Die Dauer ist mit dem Datenschutz abzustimmen (offen, OPEN_QUESTIONS T01-01).

Hinweis für Portalkonten: Reine Portalkonten (Eigentümer, Mieter, Dienstleister) können einen Passkey nur als zweiten Faktor nutzen. Passwortlose Registrierung und Anmeldung lehnt die API mit dem Fehlercode MHVP-AUTH-0014 ab.

## Einmalige Umstellung der Selbstauskunft-Links (Betreiber)

Nach dem Update ruft ein Plattform-Administrator einmal `POST /api/v1/platform/maintenance/self-disclosure-token-hash` auf (oder startet den Celery-Task `mhvp.letting.hash_self_disclosure_tokens`). Alte Links im Klartext werden auf SHA-256 umgestellt, bereits versandte Links bleiben gültig, der Aufruf ist wiederholbar und ändert dann nichts mehr.

## Objektübernahme: Standardteam und Zuständiger der Aufgaben

Für die Aufgaben, die aus der Checkliste der Objektübernahme entstehen, kann der Mandant ein Standardteam und einen Zuständigen festlegen (Schnittstelle `/onboarding/takeover-ticket-defaults`, Recht Mandanteneinstellungen). Beide Angaben sind optional, ohne Angabe werden die Aufgaben nicht zugewiesen. Die Einstellung gilt für Aufgaben, die danach angelegt werden. Ob bei Mietobjekten mit mehreren Eigentümern ein Sammelkonto je Eigentümer angelegt wird, ist noch nicht entschieden, es wird kein Sammelkonto angelegt.

Die Kontenzuordnung der Honorarbuchung prüft die Kontoart: Forderungskonto Aktiv, Erlöskonto Ertrag, Umsatzsteuerkonto Passiv. Andere Konten werden abgelehnt.

## Übernahme-Tickets (Standardteam und Zuständiger)

Unter Einstellungen, Übernahme-Tickets legen Sie fest, welchem Team und welchem Benutzer die Tickets aus der Übernahme-Checkliste eines Objekts zugewiesen werden. Beide Felder sind Auswahllisten aus den Teams und aktiven Benutzern des Mandanten. Die Auswahl "Keine Zuweisung" bedeutet, dass die Tickets ohne Team und ohne Zuständigen angelegt werden.

Die Änderung gilt nur für Tickets, die nach dem Speichern aus der Checkliste angelegt werden, bestehende Tickets bleiben unverändert. Ansehen dürfen Sie die Werte mit dem Recht Mandanteneinstellungen lesen, ändern nur mit dem Recht Mandanteneinstellungen ändern. Fehlt Ihnen das Leserecht für Teams oder Benutzer, zeigt die Auswahl nur den gespeicherten Wert, und ein Hinweis weist darauf hin.

## Inhalt der Benachrichtigungsmails (Mandant)

Unter Einstellungen, Benachrichtigungen legt die Verwaltung für den Mandanten fest, was Benachrichtigungsmails enthalten. Voll (Standard) sendet Titel und Text. Hinweis sendet nur die Anzahl neuer Benachrichtigungen und einen Link ins CRM, ohne Titel und Text. Zum Ändern ist das Recht tenant_settings:update erforderlich. Welcher Modus gelten soll, ist eine Datenschutzentscheidung (Offene Frage U15-05).

## Zustellweg und Nummernkreise

Unter Einstellungen, Zustellweg und Nummernkreise legt die Verwaltung den Standard-Zustellweg (Post, E-Mail, Portal) fest. Er gilt im Versand, wenn weder die Position noch der Kontakt einen Zustellweg vorgibt. Darunter lassen sich Präfix, Stellenzahl, Startwert und Jahresbezug der Nummernkreise einstellen; die Vorschau zeigt die nächsten drei Nummern. Derzeit wirkt die Einstellung bei Vertragsnummern. Der Rechnungsnummernkreis ist bis zur Freigabe durch den Steuerberater gesperrt (Offene Frage AA17-01). Zum Ändern ist das Recht tenant_settings:update erforderlich.

## Ordnerschema der Google-Drive-Ablage

In der DMS-Anbindung bestimmt das Ordnerschema, in welche Ordner die Direktablage eines Dokuments zu einem Objekt schreibt, zum Beispiel {objekt}/{kategorie}/{jahr}. Leer bedeutet {objekt}/{jahr}.

## Kundendomains und OIDC-Clients (Plattform)

Plattformadministratoren pflegen unter Plattform, Domains die Hostnamen eines Mandanten (Zweck Portal, CRM oder API) mit Hinweis auf den CNAME-Eintrag und sperren oder entsperren den Mandanten. Unter Plattform, OIDC-Clients werden Clients der Anmeldung für Bestandstools angelegt, das Secret erneuert und Clients deaktiviert. Das Secret wird nur einmal angezeigt.

## Plattformaudit

Plattformadministratoren sehen die festgeschriebenen Plattformaktionen (Domain angelegt oder entfernt, Mandantenstatus geändert, OIDC-Client angelegt, Secret erneuert, aktiviert, deaktiviert) über `GET /api/v1/platform/audit-events` (Parameter `limit`, `offset`, `action`). Die Einträge sind nicht änderbar und enthalten keine Secrets. Die Oberfläche dafür ist die Seite Plattform, Plattformaudit (siehe Handbuch Plattform, Abschnitt Audit).

## Textbausteine (Informationsblatt, Anschreiben, § 35a)

Unter Einstellungen, Textbausteine pflegen Sie die Texte, die auf dem Informationsblatt zur Betriebskostenabrechnung, im Eigentümeranschreiben und im Nachweis § 35a EStG erscheinen. Ein Text wird als Entwurf angelegt, zur Freigabe eingereicht und von einer zweiten Person mit dem Recht Dokumente freigeben freigegeben. Ausgegeben wird nur der freigegebene Text; ohne Freigabe erscheint der Hinweis "Text nicht freigegeben". Die Software liefert keine Rechtstexte, den Wortlaut stimmen Sie mit Rechtsanwalt oder Steuerberater ab.

## Rechtstexte des Portals (Impressum, Datenschutz, Nutzungsbedingungen)

Unter Einstellungen, Rechtstexte des Portals pflegen Sie Impressum, Datenschutzerklärung und Nutzungsbedingungen des Portals Ihres Mandanten. Die Pflege entspricht den Textbausteinen: Entwurf anlegen, zur Freigabe einreichen, Freigabe durch eine zweite Person mit dem Recht Dokumente freigeben. Im Portal erscheint nur die freigegebene Fassung, verlinkt im Fuß der Seite und auf der Anmeldeseite (Seite Rechtliches, auch ohne Anmeldung erreichbar). Solange kein Text freigegeben ist, zeigt das Portal den Hinweis "Text nicht freigegeben" oder den externen Link, den Sie unter Mandant bei der Markenanpassung für Impressum und Datenschutz hinterlegt haben. Die Software liefert keine Rechtstexte, den Wortlaut stimmen Sie mit Ihrer Rechtsberatung ab.

Die Ampel oben zeigt den Freigabestand je Text. Darunter sehen Sie die Fassung der Nutzungsbedingungen in der Einwilligungsrichtlinie (zum Beispiel NB-2, also Versionsnummer des freigegebenen Textes) und ob sie dem freigegebenen Text entspricht. Mit dem Recht Kontakte freigeben können Sie die Fassung ausdrücklich übernehmen oder den Schalter "Dem freigegebenen Text folgen" setzen. Beides verpflichtet die Portalkonten, die neue Fassung anzunehmen; der Standard ist die Pflege von Hand. Die Änderung wird protokolliert.

## Fachliche Regeln (alle Schalter für offene Entscheidungen)

Unter Einstellungen, Fachliche Regeln (`/einstellungen/fachliche-regeln`) finden Sie alle Mandantenschalter, mit denen die Plattform fachlich offene Entscheidungen abbildet, an einer Stelle. Die Seite sehen Sie mit dem Recht Mandanteneinstellungen lesen oder Buchhaltung lesen. Jede Zeile zeigt die Bezeichnung des Schalters, die Kurzbeschreibung, den aktuellen Wert, den Standard, alle Varianten und das Kennzeichen "Entscheidung offen" mit der Nummer der offenen Frage in `docs/OPEN_QUESTIONS.md`. Der Link "Fachmaske öffnen" führt zur Maske, in der der Schalter fachlich wirkt (zum Beispiel die Periodensperren oder die Rechtstexte des Portals). Die Suche in den Einstellungen findet jeden Schalter über seine Bezeichnung.

Der Standard ist immer die konservative Variante: Sie bucht nichts, versendet nichts und löscht nichts, und sie ändert keine Berechnung. Die Software entscheidet keine Rechts- oder Steuerfrage. Welche Variante gilt, entscheidet der Betreiber (Geschäftsführung) nach Prüfung durch Rechtsanwalt oder Steuerberater. Die Freigabestufen G1 bis G5 bleiben von den Schaltern unberührt: Auch eine geänderte Variante umgeht kein Gate: Buchen und rechtlich maßgebliche Ausgaben bleiben hinter der jeweiligen Stufe. Die Frage in `docs/OPEN_QUESTIONS.md` bleibt offen, bis der Betreiber entschieden hat.

**Wert ändern.** Wählen Sie unter "Ändern" die Variante (oder tragen Sie Datum oder Zahl ein) und klicken Sie auf "Speichern". Weicht der neue Wert vom Standard ab, fragt die Seite zuerst nach: Mit "Änderung bestätigen" schreiben Sie den Wert, mit "Abbrechen" bleibt alles unverändert. Die Rückkehr zum Standard speichert ohne Rückfrage. Die Änderung wirkt sofort für den ganzen Mandanten. Das Ändern verlangt das in der Tabelle genannte Recht; ohne dieses Recht sehen Sie nur den Wert und den Hinweis auf das fehlende Recht. Verlangt der Schalter eine Begründung, erscheint dafür ein eigenes Feld: bei der Freigabe durch zwei Personen im Kontenrahmen (gilt für die neueste Version und nur, solange sie nicht freigegeben ist) und bei einer Rechtsgrundlage der Einwilligungen, die von der Einwilligung abweicht (mindestens 10 Zeichen). Nur Anzeige ist die Buchungsautomatik, weil das Einschalten einen eigenen Ablauf braucht (Antrag bei offenem G1 und Freigabe durch eine zweite Person auf der Seite Buchhaltung, Automatikstufen). Steht beim aktuellen Wert "nicht lesbar", war die Schnittstelle für Ihren Benutzer nicht erreichbar; es wird dann nichts zum Ändern angeboten.

Die Schalter im Überblick (Stand Welle 16):

**Buchhaltung**

| Schalter | Standard | Varianten | Offene Frage | Änderung |
| --- | --- | --- | --- | --- |
| Nummer für Mietrechnungsentwürfe | Entwurfsnummer ENTWURF-JJJJ-NNNNNN | Entwurfsnummer ENTWURF-JJJJ-NNNNNN; Reguläre Rechnungsnummer MR auch im Entwurf; Ausgabe bei geschlossenem G1 ablehnen | AC03-01 | hier (Recht Verträge ändern) |
| Nebenbuchprüfung blendet ausgebuchte Posten aus | Ein | Ein; Aus | AC01-02 | hier (Recht Mandanteneinstellungen ändern) |
| Periodensperre: Umfang | Nur Sperre des Buchungskreises | Nur Sperre des Buchungskreises; Sperre je Objekt und Zeitraum | P06-02, AA08-01 | hier (Recht Mandanteneinstellungen ändern) |
| Periodensperre beim Abschluss einer Abrechnung setzen | Aus | Ein; Aus | P06-02, AA08-01 | hier (Recht Mandanteneinstellungen ändern) |
| Aufhebung einer Periodensperre zulassen | Aus | Ein; Aus | P06-02, AA08-01 | hier (Recht Mandanteneinstellungen ändern) |
| Kontenrahmen: Freigabe durch zwei Personen | Ein | Ein; Aus | M10-01 | hier (Recht Buchhaltung freigeben, mit Begründung) |
| Kontenrahmen: Abrechnungsart und Mehrschlüsselverteilung | Vorschläge bleiben offen, bis der Kontenrahmen freigegeben ist | keine Auswahl | P07-04, P07-05 | nur in der Fachmaske |
| Steuerabzug auf Habenzinsen | Keine Steuerkonten, Abzüge 0,00 EUR | keine Auswahl | P01-01 | nur in der Fachmaske |
| Prüfpunkte für Fristen der Heizkostenverordnung | Keine Einträge | keine Auswahl | AB10-01 | nur in der Fachmaske |

**Abrechnung Miete**

| Schalter | Standard | Varianten | Offene Frage | Änderung |
| --- | --- | --- | --- | --- |
| Offene Vorauszahlungen bei Erteilung der Abrechnung | Nur Information, Saldo gegen gezahlte Vorauszahlungen | Nur Information, Saldo gegen gezahlte Vorauszahlungen; Offene Posten per Storno gegen die Abrechnung verrechnen; Saldo gegen fällige Vorauszahlungen | AC10-01, M17-03, P06-01 | hier (Recht Buchhaltung ändern) |
| Prüfbericht der Umlagegrundlagen blockiert die Ausgabe | Ein | Ein; Aus | M17-01 | hier (Recht Buchhaltung ändern) |
| Verhalten nach Ablauf der Abrechnungsfrist | Nachforderungen sperren | Nachforderungen sperren; Nur Hinweis | M17-04 | hier (Recht Buchhaltung freigeben) |
| Warnung vor Ablauf der Abrechnungsfrist | Aus | Ein; Aus | M17-04 | hier (Recht Buchhaltung freigeben) |
| Erste Warnung, Tage vor dem Fristende | 60 Tage | Zahl von 1 bis 365 | M17-04 | hier (Recht Buchhaltung freigeben) |
| Zweite Warnung, Tage vor dem Fristende | 30 Tage | Zahl von 1 bis 365 | M17-04 | hier (Recht Buchhaltung freigeben) |
| Textbausteine mit Freigabe | Kein Text freigegeben | keine Auswahl | AA11-01, AA11-02 | nur in der Fachmaske |

**WEG**

| Schalter | Standard | Varianten | Offene Frage | Änderung |
| --- | --- | --- | --- | --- |
| Anfangsbestand einer Rücklage nach berechneter Abrechnung | Gesperrt | Gesperrt; Änderung mit Protokoll; Änderung mit Freigabe durch eine zweite Person | V01-01 | hier (Recht Mandanteneinstellungen ändern) |
| Steuerliche Einordnung der Rücklagenzuführung | Nicht freigegeben | keine Auswahl | AE07-01 | nur in der Fachmaske |
| Zahlungen je Zweckrücklage | Nur gebundene Zahlungen | Nur gebundene Zahlungen; Aufteilungsvorschlag nach Planverhältnis | P07-02, P07-04 | hier (Recht Mandanteneinstellungen ändern) |
| Unterjährige Planänderung | Nur Hinweis | Nur Hinweis; Differenz sofort fällig; Verrechnung mit der nächsten Rate | M12-L2, P07-01 | hier (Recht Mandanteneinstellungen ändern) |
| Zuordnung bei Eigentümerwechsel: Kauf | Manuelle Freigabe | Manuelle Freigabe; Zuordnung nach Fälligkeit; Zuordnung nach Abrechnungsbeschluss | AA07-01, P01 | hier (Recht Buchhaltung freigeben) |
| Zuordnung bei Eigentümerwechsel: Ersterwerb | Manuelle Freigabe | Manuelle Freigabe; Zuordnung nach Fälligkeit; Zuordnung nach Abrechnungsbeschluss | AA07-01, P01 | hier (Recht Buchhaltung freigeben) |
| Zuordnung bei Eigentümerwechsel: Erbfall | Manuelle Freigabe | Manuelle Freigabe; Zuordnung nach Fälligkeit; Zuordnung nach Abrechnungsbeschluss | AA07-01, P01 | hier (Recht Buchhaltung freigeben) |
| Zuordnung bei Eigentümerwechsel: Zwangsversteigerung | Manuelle Freigabe | Manuelle Freigabe; Zuordnung nach Fälligkeit; Zuordnung nach Abrechnungsbeschluss | AA07-01, P01 | hier (Recht Buchhaltung freigeben) |
| Zuordnung bei Eigentümerwechsel: Schenkung | Manuelle Freigabe | Manuelle Freigabe; Zuordnung nach Fälligkeit; Zuordnung nach Abrechnungsbeschluss | AA07-01, P01 | hier (Recht Buchhaltung freigeben) |
| Zuordnung bei Eigentümerwechsel: sonstiger Erwerb | Manuelle Freigabe | Manuelle Freigabe; Zuordnung nach Fälligkeit; Zuordnung nach Abrechnungsbeschluss | AA07-01, P01 | hier (Recht Buchhaltung freigeben) |
| Virtuelle Versammlung zulassen | Aus | Ein; Aus | V13, AA06-02 | hier (Recht Mandanteneinstellungen ändern) |
| Grundlagenbeschluss: Höchstdauer als Sperre | Aus | Ein; Aus | AA06-02 | hier (Recht Mandanteneinstellungen ändern) |
| Stichtag der Übergangsregel | kein Datum | Datum oder leer | AA06-02 | hier (Recht Mandanteneinstellungen ändern) |
| Online-Versammlung im Portal | Aus | Ein; Aus | AD06-01 | hier (Recht Mandanteneinstellungen ändern) |
| Vollmacht gegen eigene Stimme | Konflikt als Prüfhinweis markieren | Konflikt als Prüfhinweis markieren; Zuerst abgegebene Stimme zählt; Vollmacht hat Vorrang; Eigene Stimme hat Vorrang | AD06-02 | hier (Recht Mandanteneinstellungen ändern) |

**Portal**

| Schalter | Standard | Varianten | Offene Frage | Änderung |
| --- | --- | --- | --- | --- |
| Mieterträge im Eigentümerportal | Aus | Ein; Aus | P13-01, Q10-02 | hier (Recht Mandanteneinstellungen ändern) |
| Tickets im Eigentümerportal | Nur freigegebene Tickets | Keine Tickets; Nur freigegebene Tickets; Alle Tickets zum Objekt | P13-01 | hier (Recht Mandanteneinstellungen ändern) |
| Bewertungen von Dienstleistern | Aus, nur intern | Aus, nur intern; Anzeige nur für die Verwaltung | AA14-02 | hier (Recht Mandanteneinstellungen ändern) |
| Portal-Assistent (Chat-Bot) | Aus | Ein; Aus | AE28-01, AE28-03 | hier (Recht Mandanteneinstellungen ändern) |
| Portal-Assistent: Datenschutzhinweis | Aus | Ein; Aus | AE28-01, AE28-02 | hier (Recht Mandanteneinstellungen ändern) |
| Fassung der Nutzungsbedingungen | Pflege von Hand | Pflege von Hand; Dem freigegebenen Text folgen | AE29-01, AC06-03 | hier (Recht Kontakte freigeben) |

**Sicherheit und Datenschutz**

| Schalter | Standard | Varianten | Offene Frage | Änderung |
| --- | --- | --- | --- | --- |
| Rechtsgrundlage: E-Mail-Zustellung | Einwilligung | Einwilligung; Vertrag; Berechtigtes Interesse | AE34-01, AC06-01 | hier (Recht Kontakte freigeben, mit Begründung) |
| Rechtsgrundlage: Datenweitergabe | Einwilligung | Einwilligung; Vertrag; Berechtigtes Interesse | AE34-01, AC06-01 | hier (Recht Kontakte freigeben, mit Begründung) |
| Rechtsgrundlage: Werbung | Einwilligung | Einwilligung; Berechtigtes Interesse | AE34-02, AC06-01 | hier (Recht Kontakte freigeben, mit Begründung) |
| Rechtsgrundlage: Nutzungsbedingungen des Portals | Einwilligung | Einwilligung; Vertrag | AE34-01, AC06-03 | hier (Recht Kontakte freigeben, mit Begründung) |
| Zweiter Faktor für CRM-Benutzer | Freiwillig | Freiwillig; Pflicht für alle CRM-Rollen; Pflicht für gewählte Rollen | AE27-01 | hier (Recht Mandanteneinstellungen ändern) |
| Zweiter Faktor im Portal | Aus | Ein; Aus | AE27-01 | hier (Recht Mandanteneinstellungen ändern) |
| Auskunftsexport: andere Personen | Nur die Rolle | Nur die Rolle; Mit Namen | AC07-01, AE33-02 | hier (Recht Mandanteneinstellungen ändern) |
| Auskunftsexport: interne Vermerke | Aus | Ein; Aus | AC07-01, AE33-02 | hier (Recht Mandanteneinstellungen ändern) |
| Dokument-Papierkorb | Aus | Ein; Aus | AC07-03, AE33-01 | hier (Recht Mandanteneinstellungen ändern) |
| Dokument-Papierkorb: Frist in Tagen | 30 Tage | Zahl von 1 bis 365 | AC07-03, AE33-01 | hier (Recht Mandanteneinstellungen ändern) |

**Bank und Automatik**

| Schalter | Standard | Varianten | Offene Frage | Änderung |
| --- | --- | --- | --- | --- |
| Buchungsautomatik | Aus | Ein; Aus | BK2-03, M12-09 | nur in der Fachmaske |
| Guthaben aus Abrechnungen als Verbindlichkeitsposten | Aus, keine Verbindlichkeitsposten | Aus, keine Verbindlichkeitsposten; Posten zur gebuchten Gutschrift im Nebenbuch; Umbuchungsentwurf auf das Kreditorenkonto | AE22-01, Q01-01, P04-04 | hier (Recht Mandanteneinstellungen ändern) |
| Verbindlichkeitsposten: Freigabe durch zwei Personen | Ein | Ein; Aus | AE22-01, Q01-01 | hier (Recht Mandanteneinstellungen ändern) |
| EBICS-Anbindung | Aus | Ein; Aus | AE23-01 | hier (Recht Mandanteneinstellungen ändern) |
| EBICS: Ablage des Signaturschlüssels | Extern (Standard) | Extern (Standard); Serverseitig, verschlüsselt abgelegt | AE23-05 | hier (Recht Mandanteneinstellungen ändern) |
| G1 Öffnungsliste | Freigabestufe G1 bleibt geschlossen | keine Auswahl | M12-09 | nur in der Fachmaske |

**Plattform**

| Schalter | Standard | Varianten | Offene Frage | Änderung |
| --- | --- | --- | --- | --- |
| Abnahmeregister | Kein Sollwert gilt ohne Freigabe durch eine zweite Person | keine Auswahl | V16, AE01-01 | nur in der Fachmaske |

Nicht auf dieser Seite stehen Einstellungen, die keine fachlich offene Entscheidung betreffen, und Werte, die je Datensatz gelten (zum Beispiel die Steuerkonten für Zinsabzüge je Buchungskreis, der Zugangsnachweis je Abrechnung oder die Prüfpunkte der Heizkostenverordnung selbst); dafür führt der Link zur Fachmaske.

## Objektakte: Pflichtdokumente und lokales Modell (AF18)

Unter Einstellungen, Objektakte pflegen Sie die Pflichtdokumente je Objektart (Anlegen, Ändern, Löschen) und sehen den Status des lokalen Modells für die Dokumentprüfung samt Vorschlag je Prüffall. Das Modell liefert nur Vorschläge; eine Person übernimmt oder lehnt ab. Importlauf, Texterkennungs-Cache und Importvorschau haben noch keine Bedienmaske und laufen über die Schnittstelle.

## Demo-Band, Mailquellen und API-Schlüssel (AF19)

Gehört der angemeldete Benutzer zu einem Demo-Mandanten, zeigt die Kopfzeile ein Demo-Band. Das Kennzeichen liefert die Schnittstelle `GET /auth/me` im Feld `is_demo`. Unter Einstellungen, Mailquellen legen Sie Eingangs-Webhooks an, aktivieren sie, erneuern das Geheimnis (Anzeige nur einmal) und sehen das Empfangsprotokoll. Unter Einstellungen, API-Schlüssel legen Sie Schlüssel an (Klartext nur einmal sichtbar, danach nur das Präfix) und widerrufen sie. Branding-Vorschau steht in den Mandanteneinstellungen.

## Plattformeinstellungen und Zuordnungsschwellen (Welle 18, AG03)

- Plattformadministratoren sehen unter Plattform den Kasten Plattformeinstellungen mit dem
  Schalter für die Umgehung des Vier-Augen-Prinzips (Standard aus). Eine Änderung verlangt eine
  Bestätigung und wird protokolliert; sie öffnet keine Freigabestufe.
- Unter Einstellungen, Fachliche Regeln stehen die Schwellen des Personenabgleichs der
  Objektübernahme in Prozent (Zuordnung 90, Vorschlag 60). Die Zuordnungsschwelle darf nicht
  unter der Vorschlagsschwelle liegen.
- Die Rolle Versicherungsmakler hat ohne den Schalter "Zugriff der Rolle Versicherungsmakler"
  keine Rechte und ist in der Rollenauswahl entsprechend gekennzeichnet.

## Stapelverarbeitung beim KI-Anbieter (Welle 18, AG04)

Unter Einstellungen, KI-Anbieter, lässt sich je Anbieter die Stapelverarbeitung einschalten
(Standard aus, derzeit nur Anthropic). Zurückgestellte nächtliche Läufe werden dann gesammelt
an den Anbieter gesendet und stündlich abgerufen; das Ergebnis erscheint wie bisher als
Vorschlag. Der Preisfaktor wird aus der Preisliste des Anbieters übernommen (1 bedeutet kein
Abschlag). Jede Änderung hebt die Freigabe auf; die zweite Person muss erneut freigeben.

## Ausgehende Webhooks: Testzustellung, Schlüssel, Fehlschläge (AI07)

Unter Einstellungen, Webhooks bietet jede Zeile zusätzlich Testzustellung (plant das Ereignis webhook_subscription.test nur für dieses Abonnement ein, das Ergebnis steht im Protokoll), Bearbeiten (Ziel-URL und Beschreibung) und Schlüssel erneuern (der neue Signaturschlüssel wird einmal angezeigt, der alte ist sofort ungültig). Schlagen Zustellungen endgültig fehl, zeigt die Zeile einen Warnhinweis mit Anzahl und Zeitpunkt, und Benutzer mit dem Recht webhooks:update erhalten eine Benachrichtigung. Ein automatisches Deaktivieren erfolgt nur, wenn unter Fachliche Regeln der Wert Webhooks nach Fehlschlägen in Folge deaktivieren größer als 0 ist (Standard 0, nur melden). Beim erneuten Aktivieren beginnt die Zählung neu. Dort steht auch der Schalter Objektakte-Webhook nur mit Zeitstempel annehmen (Standard aus).

## Ausweis haushaltsnaher Leistungen und Prüfhinweis Kaution (Welle 20)

Unter Einstellungen, Fachliche Regeln stehen zwei Schalter. "Ausweis haushaltsnaher Leistungen, Auswahl der Rechnungen" wählt zwischen Rechnungsdatum (Standard) und nur bezahlten Rechnungen nach Zahlungsdatum. Jede Zeile des Ausweises zeigt, ob und wann die Rechnung bezahlt wurde. Wird für denselben Vertrag und dasselbe Jahr erneut ein Ausweis erzeugt, erscheint ein Hinweis; gesperrt wird nichts. "Prüfhinweis zur Kautionshöhe und Ratenzahl" (Standard aus) zeigt in der Kautionsübersicht des Vertrags einen Hinweis, wenn die Kaution einer Wohnung über dem Vergleichswert liegt. Beide Schalter treffen keine steuerliche oder rechtliche Festlegung.

## Zweiten Faktor eines Benutzers zurücksetzen (Vier-Augen)

Hat ein Benutzer seinen zweiten Faktor verloren, kann ein Administrator mit dem Recht
Mitglieder ändern einen Antrag stellen (Schnittstelle `POST /auth/mfa-reset/requests` mit
Mitgliedschaft und Begründung, mindestens 10 Zeichen). Voraussetzung ist der Mandantenschalter
`mfa_admin_reset_enabled` (Standard aus, `PUT /auth/mfa-reset/settings`). Ein zweiter
Administrator gibt den Antrag frei oder lehnt ihn ab; der Antragsteller selbst und der
betroffene Benutzer können nicht freigeben. Mit der Freigabe werden TOTP, Passkeys, gemerkte
Geräte und alle Sitzungen des Benutzers widerrufen; er meldet sich mit dem Passwort an und
richtet den zweiten Faktor neu ein. Benutzer und Antragsteller erhalten eine Benachrichtigung.
Die Identität des Benutzers prüfen die Administratoren vorher selbst. Eine Maske im CRM folgt;
die Variantenwahl ist offen (Frage AI09-01).
