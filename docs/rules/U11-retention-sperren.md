# U11 Automatische Löschungssperre bei offenem Verfahren und Vier-Augen-Aufhebung

| Feld | Inhalt |
| --- | --- |
| ID | `U11` (Rest S711-06, Spezifikation 7.11 S04/S05) |
| Geltungsbereich | Mandant, Dokumente (`documents/retention.py`, `documents/services.deletion_blocker`), Vorgänge (Ticket-Sperre) |
| Regeltyp | Produktschutz (0.2), keine Rechtsgrundlage behauptet |
| Quellenstatus Anhang C | keine neue Frist; Fristwerte der Profile bleiben Entwurf (Regel M6-04, Prüfung Steuerberater) |
| Abnahmefall | D43, D46 (Sperre schlägt Frist), Test `tests/integration/test_u11_retention_procedure_holds.py` |
| Änderungsgrund | Lückenliste 30.09.2026, S711-06 teilweise: Verknüpfung mit Verfahren und Aufhebung im Vier-Augen-Prinzip fehlten |

## Regel

1. Automatische Sperre: Ist ein Dokument mit einem Vertrag verknüpft und besteht auf einem offenen Posten dieses Vertrags eine aktive Mahnsperre mit Grund `litigation` (Prozess) oder `insolvency` (Insolvenz) aus der Buchhaltung (M16-03), wird das Dokument nicht gelöscht, weder einzeln noch über Löschvorschläge. Grund im Sperrtext: "Automatische Löschungssperre: offenes Verfahren (...)". Mit Aufhebung der Mahnsperre in der Buchhaltung entfällt die automatische Sperre; die übrigen Prüfungen (Frist, Profil, Dauerunterlage) gelten weiter.
2. Bestrittene Posten, Ratenplan und Aufrechnung lösen keine Sperre aus.
3. Vier Augen: Eine manuelle Sperre am Dokument oder am Vorgang hebt nur eine andere Person auf als die, die sie zuletzt gesetzt hat (Ereignis `document.hold_set` bzw. `ticket.hold_set`). Sonst Fehler `MHVP-GATE-0002` (403).
4. Status: `GET /documents/{id}/retention-status` zeigt manuelle Sperre, Sperrart, automatische Verfahrenssperre, Vorgangssperre, WEG-Dauerunterlage und den aktuellen Löschhinderungsgrund.

5. Keine Überschreibung (V11-07): `POST /documents/{id}/hold` bei bestehender aktiver Sperre antwortet 409 (`CONFLICT`); Grund, Sperrart und die für Vier Augen zählende Person bleiben erhalten. Eine Änderung der Sperrart setzt die Aufhebung durch eine zweite Person und eine neue Sperre voraus.
6. Startregel Beschluss (U11-01, Migration 0300): Wert `resolution` der Aufzählung `retention_start`; das Dokument verweist über `retention_resolution_id` auf einen Beschluss (WEG), dessen Beschlussdatum nach `retention_base_on` übernommen wird. Die Frist beginnt mit dem 31.12. des Beschlussjahres (Jahresende, verkürzt nie, gekennzeichnete Annahme wie bei den anderen Basen) zuzüglich der Profilfrist. Ohne Bezug bleibt das Dokument gesperrt ("Fristbeginn fehlt"). Fristwerte der Profile bleiben Entwurf. Quellenstatus Anhang C: Produktschutz, keine Rechtsquelle. Abnahmefall: Test `test_resolution_start_rule_takes_the_decision_date`. Änderungsgrund: U11-01-Rest.
7. Anzeige im CRM (Dokumentdetail): Karte "Aufbewahrung und Sperren" mit Fristende, Beschlussbezug, Sperrgrund, Sperrart, Löschhinderungsgrund und Vier-Augen-Hinweis (`hold_set_by_four_eyes_required` ist wahr, solange eine manuelle Sperre besteht).

## Nicht geregelt (offen)

* Steuerliche Verfahren (Außenprüfung, Einspruch) haben kein Datenmodell; Sperre bis dahin manuell mit Sperrart `tax_procedure`.
