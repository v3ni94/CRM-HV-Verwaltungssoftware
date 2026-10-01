# M5-08 Verknüpfung von Mieterhöhungsfall, Vertragssperre und KI-Prüfung

| Field | Content |
| --- | --- |
| ID | `M5-08` |
| Title | Verknüpfung von Mieterhöhungsfall, Vertragssperre und KI-Prüfung |
| Scope | Domänen `letting` und `contracts`, Tabelle `rent_increase_case` (Migration 0281), CRM Vertragsformular |
| Source status | Keine Rechtsnorm im Quellenregister (annex C); Fachliche Umsetzung nach Abschnitt 6.3. Der Fallcheck prüft nur die erfasste Sperre |
| Acceptance case | Test `apps/api/tests/integration/test_q14_letting_w3.py::test_adopt_rent_index_and_ai_check_link`, Vitest `LettingW3.test.tsx` |
| Implementation | `RentIncreaseCase.ai_check_id`, `PUT /letting/rent-increases/{id}/ai-check`, CRM `RentIncreaseLinks` im Vertragsformular |
| Change reason | Lückenliste 30.09.2026 M5-08: keine Sicht vom Vertrag auf die Fälle, kein Verweis auf die KI-Prüfung |

## Regeln

- Das Vertragsformular zeigt die Mieterhöhungsfälle des Vertrags mit Verweis auf den Fall und warnt, wenn ein
  offener Fall vor Ablauf von `rent_increase_block_until` wirksam wird. Die Sperre selbst prüft weiterhin der
  Fallcheck der API (Hinweis, Freigabe gesperrt).
- `ai_check_id` verweist auf den KI-Vorschlag (`ai_proposal`) zum Fall; Löschen des Vorschlags setzt den
  Verweis auf leer. Das JSONB `check` bleibt die deterministische Prüfung. Die KI entscheidet nichts.
