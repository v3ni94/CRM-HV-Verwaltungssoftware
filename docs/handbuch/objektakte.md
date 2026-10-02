# Objektakte (Prüfcenter der Übernahme)

Seite Objektakte (`/objektakte`). Stand: 02.10.2026. Sichtbar mit dem Recht objektakte:read, Pflege mit
objektakte:update. Die Ordnerstruktur und die Zuordnung von Unterlagen beschreibt die Handlungsanweisung
[Objektordner, Mieterakte und Objektdaten](anleitung-objektordner.md); der technische Hintergrund steht in
[Dokumente und DMS](dokumente-dms.md).

## Zweck

Das Bestandsprojekt objektakte wird im Parallelbetrieb in das CRM übernommen. Die Seite ist das Prüfcenter für die
dreistufige Klassifikation der übernommenen Dokumente (Regeln, KI-Vorschlag, Prüfung durch eine Person). Sie
verändert keine Buchungen. Jede Klassifikation durch die KI ist ein Vorschlag und wird erst durch eine Person
bestätigt.

## Bereiche der Seite

| Bereich | Inhalt |
| --- | --- |
| Prüfcenter | Offene Fälle je Kategorie; Klasse bestätigen, manuell setzen oder verwerfen |
| Listen aus der Objektakte | Anforderungslisten fehlender Unterlagen je Objekt oder über alle Objekte, Dokumentenübersicht je Kategorie, Export als CSV (nur lesend) |
| KI-Kosten der Altanwendung | Kosten, Token und Anzahl externer KI-Aufrufe aus dem objektakte-Protokoll je Objekt und Monat (nur lesend, neue KI-Aufrufe des CRM erscheinen hier nicht) |
| Abgleich objektakte gegen CRM | Dokumente je Objekt in beiden Systemen, fehlende Dokumente auf beiden Seiten, abweichende Prüfsummen (nur lesend) |

Weitere Bereiche, die je nach Einrichtung erscheinen: Importläufe mit Datum und Zahlen (inklusive "OCR-Cache
leeren", entfernt nur den übernommenen Text, Dokumente bleiben), Vorschaubilder übernehmen, Klassifikationsregeln,
Synchronisationsstand (täglicher Differenzimport, Standard aus) und Benutzerabbildung (Vorschlag je
objektakte-Benutzer, es wird nie automatisch ein Benutzer oder eine Rolle angelegt).

## Ablauf

1. Prüfcenter öffnen und Fälle nach Kategorie bearbeiten.
2. Anforderungslisten für fehlende Unterlagen erzeugen und bei Bedarf als CSV herunterladen. Ein Nachforderungsschreiben
   entsteht nur als Entwurf, nicht versendet.
3. Abgleich prüfen und Abweichungen über den Differenzimport oder von Hand auflösen.

## Grenzen

* Die Seite ist ein Werkzeug der Übernahme und kein Archiv. Aufbewahrung und Löschung richten sich nach den
  freigegebenen Profilen (siehe [Datenschutz im CRM](datenschutz.md), Löschkonzept im Entwurf).
* Wenn die Dossier-Angaben zum Bestandsprojekt noch Platzhalter tragen (V1), ist die Übernahme nur so weit belastbar,
  wie der Abgleich zeigt.
