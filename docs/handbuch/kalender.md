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

## Sprung aus einer Benachrichtigung

Eine Benachrichtigung zu einem Termin öffnet den Kalender im Monat des Termins und zeigt die
Termindetails sofort an (Adresse /kalender?termin=<Kennung>&datum=JJJJ-MM-TT). Liegt der Termin
in einem anderen Zeitraum als dem angezeigten, bleibt die Anzeige beim Blättern auf dem Termin,
sobald er geladen ist.

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

## Heute und Protokoll öffnen am Handy

Der Knopf Heute springt zum aktuellen Monat (in der Wochenansicht zur aktuellen Woche) und
rollt den ersten Eintrag des heutigen Tages unter die Kopfzeile; heutige Einträge sind
hinterlegt. Ein Übergabetermin zeigt am Handy den Knopf Protokoll öffnen als
Hauptaktion und führt direkt zum Übergabeprotokoll; andere erzeugte Einträge behalten
Zur Quelle. Die Hinweise Wiederkehrend und Erinnerung stehen als Text in der Zeile, es gibt
keine Hinweise mehr, die erst beim Überfahren mit der Maus erscheinen. Die Werkzeugleiste
liegt am Handy in zwei Zeilen: Pfeile, Monat und Heute oben, darunter der Wechsel zwischen
Monat und Woche sowie Aktualisieren und Termin anlegen. Termin anlegen und die
Termin-Details öffnen am Handy und am Tablet als Bodenblatt, die Knöpfe Abbrechen und
Termin anlegen bleiben unten über der Tastatur sichtbar. Löschen liegt am Handy hinter
Mehr; am Tablet und am Rechner steht der Knopf wie bisher in der Zeile. Die Wochenansicht
zeigt sieben Spalten erst ab 1024 px, darunter eine Tagesliste.

## Häufige Fehler

- **Google-Kalender erscheint nicht**: Postfach wurde vor Einführung der
  Kalenderfreigabe verbunden; unter Einstellungen, Postfächer erneut mit Google verbinden,
  damit der Kalender-Scope erteilt wird.
- **Einladung an Externe bleibt aus**: Termin ist noch unbestätigt; Status auf bestätigt
  setzen, danach geht die Einladung hinaus.
- **Termin doppelt sichtbar**: Ein Immoware24-Kalender und ein Google-Kalender bilden
  denselben Termin ab; Quelle in der Legende prüfen, im Zweifel den Immoware24-Kalender
  als führend behandeln (Immoware24 bleibt Master der Stammdaten).

## Kalender-Abo für externe Kalender

Unter Kalender kann eine persönliche Abo-Adresse erzeugt werden. Sie wird nur einmal angezeigt und wie ein Passwort behandelt. Eine neue Adresse macht die bisherige ungültig, der Widerruf beendet das Abo. Der Feed enthält eigene und geteilte Termine sowie Fristen, soweit die Person die Rechte dafür hat.
