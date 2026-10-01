# M26-INDEX-01 Mietspiegelwerte je Gemeinde mit manueller Pflege und CSV-Import

| Field | Content |
| --- | --- |
| ID | `M26-INDEX-01` |
| Title | Mietspiegelwerte je Gemeinde mit manueller Pflege und CSV-Import |
| Scope | Domäne `letting`, Tabelle `rent_index_entry`, Mandantentabelle mit RLS, Rechte `contracts:read` und `contracts:update` |
| Source status | Fachliche Umsetzung, Entscheidung 8 a vom 30.09.2026: keine automatische Quelle. Werte stammen aus dem Mietspiegel der Gemeinde und werden mit Quellenangabe erfasst. Keine Rechtsgrundlage im Quellenregister |
| Acceptance case | keine in Anhang D; Test `test_p20_letting_dispatch_w2.py::test_rent_index_csv_lookup_isolation_and_rights` |
| Implementation | `mhvp.letting.rentindex` (`/letting/rent-index`, `/import`, `/lookup`), `mhvp.letting.models.RentIndexEntry`, Migration 0269 |
| Change reason | Lückenliste 30.09.2026, Befund M26-03, Entscheidung 8 a |

## Regeln

- Je Zeile: Gemeinde, Name und Stand des Mietspiegels, optionale Klassen (Baujahr, Wohnfläche, Ausstattung), Spanne je m² und Monat (von, Mittel, bis), Pflichtfeld Quelle.
- CSV mit Semikolon, Spalten gemeinde, name, stand, baujahr_von, baujahr_bis, flaeche_von, flaeche_bis, ausstattung, min, mittel, max, quelle; Dezimalkomma und Datum TT.MM.JJJJ werden gelesen. Die Vorschau schreibt nichts; bei Fehlerzeilen wird nichts übernommen; identische Zeilen werden übersprungen.
- Die Abfrage liefert die Zeilen des jüngsten gültigen Mietspiegels, die zu den angegebenen Merkmalen passen. Fehlt ein Merkmal, das eine Klasse braucht, wird die Zeile nicht geraten, sondern als nicht prüfbar vermerkt. Ohne Treffer gibt es keinen Ersatzwert.
- Die Einordnung in die Spanne und die ortsübliche Vergleichsmiete bleiben eine Entscheidung der Verwaltung.

## Nachtrag 30.09.2026 (Q14, M26-03)

- Die Werte werden im CRM unter Vermietung, Mietspiegel gepflegt (Erfassen, Löschen, CSV mit Vorschau).
- Im Mieterhöhungsfall im Status Entwurf mit Begründung Mietspiegel oder Vergleich kann die Spanne eines
  Wertes übernommen werden (`POST /letting/rent-increases/{id}/adopt-rent-index`, Position Untergrenze,
  Mittelwert oder Obergrenze). Übernommen werden Vergleichsmiete je m², Name und Stand des Mietspiegels,
  Begründung und Quellenvermerk; die Prüfung läuft neu. Die Wahl der Position trifft die Sachbearbeitung, die
  Plattform ordnet keine ortsübliche Vergleichsmiete zu.
