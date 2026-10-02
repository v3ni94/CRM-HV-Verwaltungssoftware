# ADR 0026: Dokumentierte Stackabweichungen von Abschnitt 4

- Status: Proposed (Freigabe durch den Betreiber offen, OPEN_QUESTIONS GAI-108-01)
- Date: 2026-10-02

## Context

ADR 0001 Punkt 1 hält fest, der Stack der Abschnitte 3 und 4 werde unverändert verwendet. Der Code weicht in mehreren Punkten ab (Befund GAI-108, Konflikt E16). Die Abweichungen sind bisher nur verstreut in Nachträgen von ADR 0001 oder gar nicht begründet. Dieser ADR stellt den Ist-Stand fest und legt ihn dem Betreiber zur Entscheidung vor. Er ändert keinen Code.

## Decision

Ist-Stand gegenüber `docs/MASTER-PROMPT.md` Abschnitt 4 (Zeile 207) und Abschnitt 3 (Zeile 170):

| Vorgabe der Spezifikation | Ist-Stand | Beleg |
| --- | --- | --- |
| WeasyPrint oder Gotenberg für PDF | `reportlab` direkt im Prozess, kein Gotenberg-Dienst | `apps/api/pyproject.toml` (`reportlab>=4.4,<5`), `platform/market_readiness.py:265`, `hoa/statement_pdf.py`, `handover/pdf.py` |
| `sepaxml` oder `fintech.sepa` für pain-Dateien | eigene XML-Erzeugung mit `xml.etree`, Prüfung eingelesener XML mit `defusedxml`; Formatversionen pain.008.001.02 und .08 sowie pain.001.001.09 | `accounting/direct_debit.py:23-25,44-45`, `banking/models.py:527`; Formatversionen siehe ADR 0020 |
| Authlib | `pyjwt[crypto]` für Token, eigene OIDC-Logik | `apps/api/pyproject.toml:34` |
| `pdfplumber` (neben `pypdf`) | nur `pypdf` | `apps/api/pyproject.toml:36` |
| factory_boy, Testcontainers | nicht verwendet (Spezifikation nennt sie für Tests, Abschnitt 4) | `apps/api/pyproject.toml` ohne Treffer |
| TanStack Query und Table, shadcn/Radix | nicht verwendet; Formulare mit `react-hook-form` und `zod`, eigene Komponenten in `packages/ui` | `apps/web-crm/package.json`, Abschnitt `dependencies` |
| pgvector-Python-Paket | nicht verwendet, SQL direkt; Begründung im Modulkopf | `apps/api/src/mhvp/ai/vector.py:1` |

Vorgeschlagene Entscheidung (Einschätzung, der Betreiber entscheidet): Die Abweichungen bei PDF (reportlab) und SEPA (eigene XML-Erzeugung) werden als bewusste Abweichung geführt, solange die Abnahmefälle aus Anhang D und die Formatprüfung bestehen. Für die übrigen Punkte gilt: dokumentiert, keine Angleichung geplant. Nichts davon darf als rechtliche Pflicht dargestellt werden (Produktschutz oder Fachliche Umsetzung nach 0.2).

## Consequences

- ADR 0001 erhält einen Ergänzungsabschnitt mit Verweis auf diesen ADR; sein Punkt 1 gilt nur mit den hier genannten Abweichungen.
- Eigene SEPA-XML-Erzeugung trägt das Risiko von Schemafehlern. Gegenmaßnahmen sind Schemaprüfung in Tests und die Zustimmung der Bank zur Formatversion (PaymentBankConfig). Ein Einsatz im Zahlungsverkehr bleibt hinter Gate G2.
- reportlab erzeugt Layout im Code und ist weniger flexibel als HTML zu PDF. Barrierefreie Ausgabe (PDF/UA) ist damit nicht abgedeckt, eine Entscheidung dazu ist offen.
- Wird die Abweichung nicht freigegeben, entsteht ein Umbauauftrag (Aufwand groß, eigene Planung und eigener ADR).

## Alternatives considered

- Angleichung an die Spezifikation (WeasyPrint oder Gotenberg, `sepaxml`): höherer Aufwand und Regressionsrisiko bei bestehenden Abnahmefällen, kein erkennbarer fachlicher Gewinn.
- Spezifikation anpassen: widerspricht der Regel, Anforderungen nicht abzuschwächen (CLAUDE.md Abschnitt 6).

## References

- `docs/MASTER-PROMPT.md` Abschnitte 3, 4, 6.9.14 (E16)
- ADR 0001, ADR 0020
