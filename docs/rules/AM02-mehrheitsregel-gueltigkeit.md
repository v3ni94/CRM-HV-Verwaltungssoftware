# AM02: Gültigkeit der Versammlungs-Mehrheitsregel und Zeitraumprüfung

- ID: AM02 (Befunde GAJ-601, GAJ-604)
- Geltungsbereich: hoa/meetings (`majority_rule`), Tabellen property_owner, property_contact, contact_relation, deposit, majority_rule
- Anforderungstyp: Produktschutz (keine Rechtsgrundlage behauptet)
- Quellenstatus Anhang C: keine neue Norm; die Schwellen der Regel stammen weiterhin aus den Unterlagen der GdWE (M25-01)
- Abnahmefall: kein eigener Anhang-D-Fall; geprüft in tests/integration/test_m25_meeting.py und tests/unit/test_am02_majority_rule_validity.py

## Regel

1. Eine Mehrheitsregel `majority_rule` ist nur an Tagen von valid_from bis einschließlich valid_to (offen, wenn leer) anwendbar.
2. Zuordnung zum Tagesordnungspunkt und Auszählung (auch Protokollentwurf) prüfen die Regel gegen den Versammlungstag (Datum von scheduled_at). Außerhalb der Gültigkeit antwortet die API mit 422 und Problemcode MHVP-HOA-0039.
3. Eingabeschemata lehnen valid_to vor valid_from ab (MajorityRuleIn, DepositIn; die übrigen Schemata prüften bereits).
4. Datenbank: CHECK `ck_<tabelle>_period_order` (valid_to IS NULL OR valid_to >= valid_from) auf den fünf Tabellen, Migration 0449; angelegt NOT VALID und validiert, wenn keine Bestandszeile verstößt. Importe und Jobs können die Regel damit nicht umgehen.

## Änderungsgrund

Lückenanalyse GAJ (03.10.2026): Regel wurde ohne Gültigkeitsprüfung verwendet; Zeitraumprüfung fehlte auf Datenbankebene.

## Ergänzung AN06 (GAJ-602): Vier-Augen-Freigabe hinter Mandantenschalter

- Schalter `tenant_settings.hoa_majority_rule_four_eyes` (API `GET/PUT /hoa/majority-rule-four-eyes`, Recht tenant_settings), Standard aus: Verhalten wie vor AN06.
- Bei eingeschaltetem Schalter wird eine neue Regel mit `requires_approval = true` als Entwurf angelegt. Freigabe über `POST /hoa/majority-rules/{id}/approve` nur durch eine zweite Person mit Recht `hoa:approve` (setzt approved_by, approved_at); die anlegende Person erhält 409 MHVP-HOA-0041.
- Eine nicht freigegebene Regel wird weder einem Tagesordnungspunkt zugeordnet noch in der Auszählung angewendet (422 MHVP-HOA-0040). Regeln, die vor dem Einschalten angelegt wurden, bleiben unverändert anwendbar.
- Der Versammlungstag für die Gültigkeitsprüfung ist das fachliche Datum in Europe/Berlin (mhvp.core.clock.local_date), nicht das UTC-Datum (Befund AN14-09).
- Migration 0453. Die Modellfrage AM02-01 bleibt offen; Prüfung: tests/integration/test_an06_majority_rule_four_eyes.py, tests/unit/test_am02_majority_rule_validity.py.
