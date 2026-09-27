# Globale Suche und Verknüpfungen

## Zweck

Die globale Suche (Strg+K, auf macOS Cmd+K) findet Kontakte, Objekte, Gebäude, Einheiten,
Verträge, Dokumente, Tickets und Buchungen über alle Daten des Mandanten, ohne dass vorher
ein Objekt geöffnet werden muss. Angezeigt werden nur Trefferarten, für die der Benutzer das
Leserecht hat; Buchungen zusätzlich nur aus Buchhaltungen, deren Rechtsträger dem Benutzer
zugeordnet sind.

## Befehlspalette

Seit dem 27.09.2026 (Betreiberentscheidung, Gestaltungsvorschlag 1) ist die Suche eine
Befehlspalette. Neben den Trefferarten oben bietet sie:

* Aktionen: Ticket anlegen, Kontakt anlegen, Mahnlauf starten, Zur Auswertung Tickets. Eine
  Aktion erscheint nur mit der passenden Berechtigung (zum Beispiel Tickets anlegen,
  Kontakte anlegen, Buchhaltung anlegen). Mahnlauf starten führt zur Mahnwesen-Seite, dort
  wird die Vorschau mit Stichtag erzeugt; die Freigabe bleibt ein eigener Schritt.
* Navigation: jeder Eintrag der Hauptnavigation, gefiltert nach dem eingegebenen Text.
* Zuletzt geöffnet: bis zu acht zuletzt über die Palette geöffnete Datensätze, je Benutzer
  im Browser gespeichert (nicht auf dem Server), sichtbar solange das Eingabefeld leer ist.

Die Palette ist ein Dialog mit Fokusfalle: Tab bleibt innerhalb des Dialogs, Escape schließt
ihn und setzt den Fokus auf die aufrufende Schaltfläche zurück.

## Bedienung

* Mindestens zwei Zeichen eingeben. Tickets sind auch über ihre Nummer, Buchungen über
  Buchungsnummer, Buchungstext und Referenz auffindbar.
* Pfeiltasten wählen den Treffer, Eingabe öffnet ihn, Escape schließt die Suche.
* Gebäude öffnen die Gebäudeseite des Objekts, Buchungen das Journal der Buchhaltung.

## Verknüpfungsleiste

Jede Detailseite zeigt oben ihre verbundenen Datensätze als Links (Objekt, Einheit, Kontakt,
übergeordnetes Ticket und weitere je Seite). Der Rücksprung erfolgt über die Brotkrumen oder
die Verknüpfungsleiste der Zielseite.

## Ereignisprotokoll

Unten auf der Detailseite steht das Ereignisprotokoll des Datensatzes: Zeitpunkt, Feld,
Wert vorher, Wert nachher und Benutzer. Die Schaltfläche CSV exportieren lädt das Protokoll
als Datei (Trennzeichen Semikolon, UTF-8). Das Protokoll setzt die Berechtigung
Änderungsprotokoll lesen (`audit:read`) voraus; ohne sie erscheint ein Hinweis.
