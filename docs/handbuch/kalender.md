# Kalender

## Zweck

Der Menüpunkt Kalender zeigt Termine in Monats- und Wochenansicht: eigene Termine,
Termine aus Google-Kalendern der Postfächer, fällige Wartungen und Vertragsdaten (Ende,
Kündigung) aus den Stammdaten.

## Google-Kalender

Je Postfach lässt sich ein Google-Kalender anbinden. Vorgabe ist der Kalender des
Standardpostfachs des Mandanten, zusätzlich der dem Benutzer persönlich zugewiesene
Kalender. Die Kalenderfreigabe wird unter Einstellungen, Postfächer je Postfach
aktiviert (Kalenderfreigabe); bei erstmaliger Freigabe ist das Postfach erneut mit Google
zu verbinden, damit die Kalenderberechtigung erteilt wird. Die Anzeige im Kalender nutzt
einen Zwischenspeicher von fünf Minuten mit Aktualisieren-Schaltfläche.

## Termine anlegen und Quelle

Ein Termin lässt sich direkt im Kalender oder aus einem Ticket heraus (Termin anlegen)
erstellen. Die Quelle eines Termins (intern, Standardkalender, eigener Kalender) ist in
der Ansicht erkennbar; Legende und Filter blenden Quellen ein oder aus.

## Einladungen nur nach Bestätigung

Ein neu angelegter Termin ist zunächst unbestätigt. Kalendereinladungen an externe
Teilnehmer (außerhalb der Domains muellerhv.de und mueller-holding.ag) werden erst
versendet, wenn der Termin bestätigt wurde. Bei mehreren Terminvorschlägen (Optionslogik)
gilt: erst nach Zusage des Kunden wird ein Termin final bestätigt und die Einladung
verschickt.

## Fälligkeiten aus Stammdaten

Wartungen und Vertragsdaten stammen aus den Stammdaten (Objekte, Verträge) und werden
dort geändert, nicht im Kalender selbst. Eigene Termine lassen sich im Kalender löschen.

## Was ist Vorschlag, was verbindlich

Ein Termin ist erst mit dem Status bestätigt verbindlich gegenüber Externen. Die
Erinnerung zu Wartungen kommt entsprechend der hinterlegten Vorlaufzeit, sonst 14 Tage
vorher, und ersetzt keine eigene Fristenkontrolle bei rechtlich bedeutsamen Terminen
(siehe Kapitel Datenübernahmen sowie den Umgang mit gerichtlichen Fristen außerhalb
dieser Plattform).

## Häufige Fehler

- **Google-Kalender erscheint nicht**: Postfach wurde vor Einführung der
  Kalenderfreigabe verbunden; unter Einstellungen, Postfächer erneut mit Google verbinden,
  damit der Kalender-Scope erteilt wird.
- **Einladung an Externe bleibt aus**: Termin ist noch unbestätigt; Status auf bestätigt
  setzen, danach geht die Einladung hinaus.
- **Termin doppelt sichtbar**: Ein Immoware24-Kalender und ein Google-Kalender bilden
  denselben Termin ab; Quelle in der Legende prüfen, im Zweifel den Immoware24-Kalender
  als führend behandeln (Immoware24 bleibt Master der Stammdaten).
