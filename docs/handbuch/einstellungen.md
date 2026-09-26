# Einstellungen

## Zweck

Einstellungen bündelt alles, was den Mandanten und seinen Betrieb betrifft: Benutzer,
Rollen, Postfächer, DMS- und Google-Verbindung, SLA, KI, Immoware24-Anbindung, Bank und
Ticketvorlagen.

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
