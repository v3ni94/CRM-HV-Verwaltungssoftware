# AO03 Indexklausel, Staffelstufen, Verbraucherpreisindex und Vorschläge des Tagesjobs

| Feld | Inhalt |
| --- | --- |
| ID | AO03 (GAK-203, Rest aus AN18) |
| Title | Strukturierte Indexklausel und Staffel am Mietvertrag, Plattformtabelle Verbraucherpreisindex, Tagesjob für Entwurfsvorschläge |
| Scope | Domänen `letting`, `contracts`, `platform`; Migration 0456; CRM Vertragsdetail |
| Source status | Keine Rechtsnorm im Quellenregister (Anhang C) für Wartefrist, Wirksamkeit, Indexquelle oder Mitteilungsform; Fachliche Umsetzung nach 6.3 und 18 M26; Werte offen (AN18-01) |
| Acceptance case | `apps/api/tests/integration/test_ao03_index_graduated_proposals.py`, `apps/api/tests/unit/test_ao03_cpi_parsing.py`, `apps/api/tests/integration/test_migration_0456_index_graduated_cpi.py`, Vitest `ContractIndexTermsPanel.test.tsx` |
| Change reason | GAK-203 war nach Welle 24 nur als Rechenkern umgesetzt; Vertragsfelder, Indextabelle und Job fehlten |

## Regeln

- `contract.index_agreement` (JSONB): Indexreihe, Basisindex (Stand der letzten Anpassung), Basismonat (Monatserster), Quelle. Indexklausel und Staffel schließen sich je Vertrag aus. Nur Mietverträge.
- `contract_graduated_step`: Staffelstufen je Vertrag (Datum, Nettomiete, eindeutig je Datum), RLS je Mandant.
- `consumer_price_index`: Plattformtabelle ohne Mandant. Schreiben nur Plattform-Admin per CSV-Import (Monat;Wert) mit Pflichtangabe Quelle und Datenstand; keine automatische Quelle. Neue Werte sind nicht freigegeben; ein geänderter Wert setzt die Freigabe zurück. Freigabe je Reihe bis Monat. Nur freigegebene Werte zählen.
- Tagesjob `mhvp.letting.propose_rent_increases` (04:40) und `POST /letting/rent-increase-proposals/run` laufen nur mit `rent_increase_proposals = draft` (Standard off). Sie legen `rent_increase_case` im Status draft mit `check.proposal = true` an: Staffelstufen innerhalb von 60 Tagen (Produktschutz, kein Rechtswert) ohne Mietzeile oder Fall zum Datum; Index, wenn der letzte freigegebene Wert nach dem Basismonat über dem Basisindex liegt: Miete mal neuer Index durch Basisindex, kaufmännisch auf Cent gerundet. Derselbe Indexwert wird je Vertrag nur einmal vorgeschlagen.
- Das vorgeschlagene Wirksamkeitsdatum (Monatserster nach dem Lauf beziehungsweise Stufendatum) ist ein Platzhalter; Wartefrist, Form und Wirksamkeit prüft der Nutzer (AN18-01). Nichts wird angewendet, versendet oder gebucht; der weitere Weg ist der bestehende Mieterhöhungsfall.
