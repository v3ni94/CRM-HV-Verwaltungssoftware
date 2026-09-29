# Geräteprüfung Handy und Tablet (M31 WP4)

Manuelle Abnahme der Bedienung auf echten Geräten. Ergänzt die Playwright Projekte phone (390x844), tablet (820x1180) und tablet-landscape (1024x768), die nur Chromium mit emuliertem Touch prüfen. Safari und iPadOS laufen in der CI nicht (kein WebKit), deshalb ist diese Liste die einzige Prüfung für Fokus Zoom, Kamera, HEIC und das Verhalten beim Drehen auf Apple Geräten. Produktschutz nach CLAUDE.md Abschnitt 5, keine Rechtspflicht. Gates G1 bis G5 bleiben geschlossen; die Prüfung nutzt nur Testdaten.

Stand: Version 1.45.0, Liste erstellt am 29.09.2026. Alle Punkte sind nicht ausgeführt, bis der Betreiber Datum, Gerät und Ergebnis einträgt (Regel 0.1.9). Ergebnisfelder: "bestanden", "abweichend (Text)" oder "nicht ausgeführt".

## Vorbereitung

- Staging mit einem Testmandanten, ein Übergabeprotokoll mit zwei Beteiligten und einer Einheit, ein Ticket, ein Kontakt, ein Objekt mit Einheiten.
- Geräte: iPad (Safari, Hoch und Quer, Gerät mit 1024 px Breite im Querformat), iPhone (Safari, 390 px), Android Handy (Chrome). Jeweils im Browser und, wo vorhanden, als installierte App (Zum Home Bildschirm).
- Netzwerk Tab beziehungsweise Safari Web Inspector am Mac für die Punkte mit Anfragen (Thumbnail, PATCH current_step, Upload Größe).

## Prüfpunkte

| Nr | Prüfung | Erwartung | iPad Safari Hoch | iPad Safari Quer | iPhone Safari | Android Chrome | Datum, Prüfer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Anmeldefeld antippen | Seite zoomt nicht (16 px Schrift), Feld mindestens 44 px hoch | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 2 | Kopfzeile auf /start | eine Zeile, Hamburger (unter 1024 px) oder Symbolrail (ab 1024 px), Suche, Glocke und Avatar je 44 px, nichts ragt über den rechten Rand | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 3 | Drawer und Symbolrail | Drawer öffnet mit Fokus auf Schließen, Gruppen klappen, Mandantenwechsel bei zwei Mandanten; im Querformat öffnet der Knopf oben in der Rail den Drawer | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 4 | Bodenleiste im Übergabeeditor | Zurück und Weiter liegen über dem Home Indikator und links vom KI Startknopf; bei geöffneter Tastatur bleibt Speichern erreichbar (visualViewport Verhalten notieren) | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 5 | Schrittleiste | wischbare Zeile, aktiver Chip nach dem Wechsel sichtbar, Wechsel auf Mängel sendet PATCH current_step mit 200 | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 6 | Tastaturen je Feld | Telefon öffnet die Telefontastatur, Zählerstand die Dezimaltastatur, PLZ die Zifferntastatur, IBAN Großbuchstaben ohne Autokorrektur | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 7 | Foto aufnehmen | Kamera öffnet direkt, Foto erscheint als Kachel nach dem Speichern des Eintrags, Statuszeile zeigt Fertig | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 8 | Aus Galerie wählen inklusive HEIC | Mehrfachauswahl möglich, HEIC wird angenommen, Server speichert JPEG | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 9 | Upload Größe | ein 8 MB Foto überträgt unter 1 MB, Serverbild höchstens 2000 px lange Kante | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 10 | Thumbnails | Kacheln 96 px, Anfrage über den Thumbnail Pfad mit Cache-Control no-store, kein Eintrag im Browser Cache | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 11 | Galerie | Tippen öffnet das Foto im Vollbild, Wischen wechselt, Zähler stimmt, Schließen 44 px | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 12 | Foto entfernen | Rückfrage mit dem Text zur endgültigen Löschung, Trefffläche 44 px, Nachbar bleibt unberührt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 13 | Unterschrift beim Drehen | Vollbild mit Einwilligungstext, Canvas mindestens 45 Prozent der Höhe, Drehen während der Unterschrift erhält die Striche unverzerrt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 14 | Rückgängig und Leeren | Rückgängig entfernt den letzten Strich, Leeren alle, Speichern ohne Strich zeigt den Hinweis | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 15 | Zweite Unterschrift desselben Beteiligten | Meldung (409), Striche bleiben erhalten | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 16 | PDF im selben Tab | PDF ansehen öffnet im selben Tab, Zurück führt zum Protokoll; in der installierten App bleibt die Sitzung erhalten | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 17 | Ungespeicherte Eingaben | Schrittwechsel fragt nach, Hier bleiben behält die Eingabe, Verwerfen wechselt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 18 | Offline Hinweis | Flugmodus während Speichern zeigt den Hinweis, der Wert bleibt im Feld, Erneut senden speichert nach Wiederherstellung | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 19 | Sitzungsablauf während einer langen Übergabe | nach Ablauf antwortet die Speicherung mit 401; Verhalten notieren (Meldung, Weiterleitung zur Anmeldung, Verbleib der Eingaben) | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 20 | Tab Wiederherstellung nach Kamerawechsel | nach Rückkehr aus der Kamera App ist das Formular samt Eingaben noch da; bei Neuladen durch das System Verhalten notieren | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 21 | Leseansicht | abgeschlossenes Protokoll ohne Eingabefelder, Anrufen per tel:, Mängel unter dem Raum gruppiert, interne Bemerkungen mit Intern, keine Wörter zugestellt, gelesen oder rechtsgültig | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 22 | Datenseiten | Kalender Werkzeugleiste, Kontakt Reiter, Einheitenkarten, Ticket Abschnittsnavigation, Dokumentenliste ohne abgeschnittene Spalten | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 23 | Installierte App | Start auf /start im Vollbild ohne Farbsprung, Abendmodus in der Statusleiste, Offline Seite ohne Netz, Cache Storage ohne API Antworten oder Dokumente | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |
| 24 | Portal Gehilfe | Menüeintrag Übergabe, Protokoll ohne Überlauf, Kamera und Galerie, Unterschrift, keine Links in neuem Tab | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | nicht ausgeführt | |

## Schutzregeln, die bei jedem Durchlauf mitgeprüft werden

- Kaution bleibt Erfassung ohne Buchung; kein Geldweg wird ausgelöst (G1, G2 geschlossen).
- Gesperrte Protokolle bieten keine Bearbeitung an; Zustellung vorbereiten erzeugt nur Entwürfe.
- Nach Schließen des Tabs liegt kein Foto und keine Unterschrift im Gerät (kein localStorage, keine IndexedDB, kein Cache Eintrag).

## Ergebnis

Zusammenfassung je Gerät (Datum, Version, offene Abweichungen mit Verweis auf docs/OPEN_QUESTIONS.md):

- iPad Safari: nicht ausgeführt
- iPhone Safari: nicht ausgeführt
- Android Chrome: nicht ausgeführt
