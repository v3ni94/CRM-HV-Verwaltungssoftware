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
eingeschränkt. Stand 30.09.2026 wird die Zuordnung gespeichert und protokolliert, die
Filterung der Objekt-, Vertrags- und Ticketlisten folgt (Regel M2-02).

## Passkeys

Passkeys (WebAuthn) als zusätzlicher zweiter Faktor sind vorbereitet, aber noch nicht
freigeschaltet (Regel M2-03). Bis dahin dient TOTP als zweiter Faktor.

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
ausschalten verlangt das aktuelle Passwort und entfernt alle gemerkten Geräte. Der zweite
Faktor ist für niemanden Pflicht, auch nicht für Administratoren.

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

Unter Buchhaltung, DATEV steht zusätzlich die formale Prüfung des Buchungsstapels
(Prüfbericht je Export, Testdatei für den Importtest, Prüfung beliebiger Dateien); siehe
[DATEV-Importtest](datev-importtest.md).

## Lexware Office

Organisationen je Gesellschaft mit API Schlüssel, AVV, Postfach und Schaltern, Zuordnung der
Rechnungsarten, Kontaktabgleich, Warteschlange und vorbereitete Dauerrechnungen unter
Schnittstellen, Lexware Office; siehe [Lexware Office](lexware-office.md).
