# Einstellungen

## Zweck

Einstellungen bündelt alles, was den Mandanten und seinen Betrieb betrifft: Benutzer,
Rollen, Postfächer, DMS- und Google-Verbindung, SLA, KI, Immoware24-Anbindung, Bank und
Ticketvorlagen.

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
Monatsbudget ausgeschöpft, werden neue KI-Aufträge gesperrt. Die KI-Wissensbasis (Kapitel
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
