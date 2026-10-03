# AN18 Mieterhöhungssperre, Erhöhungsvorschläge, Versionsverlauf, Interessentenlöschung

| Field | Content |
| --- | --- |
| ID | `AN18` (Befunde GAK-201, GAK-202, GAK-203, GAK-207) |
| Title | Sperrvorschlag nach Anwendung, Zahlungsgrund je Begründung, Rechenkern Staffel und Index, Löschvorschlag für Interessentenkontakte, Versionsverlauf im Vertragsdetail |
| Scope | Domänen `letting` und `contracts`, `tenant_settings.sources` (keine Schemaänderung), CRM Vertragsdetail und Mieterhöhungsfall |
| Source status | Keine Rechtsnorm im Quellenregister (Anhang C) für Sperrdauer, Wartefrist oder Indexquelle; Fachliche Umsetzung nach 6.3 und 18 M26; Werte offen (AN18-01, AN18-02) |
| Acceptance case | `apps/api/tests/integration/test_an18_rent_increase_block.py`, `apps/api/tests/unit/test_an18_increase.py`, Vitest `ContractVersionHistory.test.tsx`, `RentIncreaseBlock.test.tsx` |
| Change reason | Lückenanalyse GAK (03.10.2026): Grund immer increase, Sperre nicht fortgeschrieben, keine Staffel und Indexvorschläge, Kontakt und Dokumente bleiben nach Interessentenlöschung unbeachtet, keine Versionsliste |

## Regeln

- Die neue Mietzeile der Aktion apply trägt den Grund aus der Begründung des Falls: index, graduated, sonst increase.
- Nach apply schlägt der Fall ein Sperrdatum nur vor, wenn der Mandant für die Begründung eine Dauer in Monaten
  hinterlegt hat (`rent_increase_block_months.<basis>`, Standard leer). Datum am Vertrag erst mit Aktion
  `set_block` (contracts:approve, Datum nicht vor Wirksamkeit), protokolliert als contract.updated mit alt und neu.
- `rent_increase_proposals` (Standard off) schaltet die spätere Vorbereitung von Staffel und Indexvorschlägen als
  Entwurf; der Rechenkern (`letting/increase_proposals.py`) rundet kaufmännisch und wendet nie an. Strukturierte
  Vertragsfelder (Indexklausel, Staffeltabelle) und die VPI-Tabelle brauchen eine Migration (offen).
- Löschen eines Interessenten (manuell oder Löschlauf) erzeugt für den Kontakt nur mit Rolle Interessent einen
  Löschvorschlag im Datenschutzprozess (Status proposed) mit den verknüpften Dokumenten; nichts wird automatisch
  gelöscht. Kontakte mit weiteren Rollen, offenen Anträgen oder weiteren Interessentenzeilen bleiben ohne Vorschlag.
- Das Vertragsdetail zeigt alle Versionen mit Gültigkeit, Link auf Vorversionen und neu oder entfallen gegenüber
  der Vorversion bei den Zahlungszeilen (nur Anzeige).
