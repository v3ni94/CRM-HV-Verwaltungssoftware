# Regel M13-fee-fields: Verwalterhonorar Felder, Rechnungsplan Automatikkennzeichen, Standardregel

- ID: M13-fee-fields
- Geltungsbereich: Verwalterhonorar (`admin_fee_setting`), Rechnungsplan (`recurring_invoice_plan`), Dienstleisterverhältnis (`service_provider_relation.create_default_bank_rule`)
- Quellenstatus: Fachliche Umsetzung aus Master-Prompt 6.2, 6.4 und 6.9.4; keine Rechtsnorm aus Anhang C. Fälligkeit folgt dem Vertrag, keine Frist wird angenommen.
- Abnahmefall: `tests/unit/test_aa10_fee_plan.py` (SE-Betrag 3 x 12,50 EUR = 37,50 EUR netto, USt 19 % = 7,13 EUR; Fälligkeit; Kündigungsdatum), `tests/unit/test_format_versions_pin.py`
- Änderungsgrund: Befunde GA03-06, GA03-07, GA02-05, GA03-09 der Lückenliste 01.10.2026

## Regeln

1. Das Kündigungsdatum (`termination_date`) und das Ende (`end_date`) begrenzen den Lauf; maßgeblich ist das frühere Datum.
2. `due_day_rule` ergibt die Fälligkeit im Monat des Leistungszeitraums (`day`, `last_day`, `day_next_month`); ohne Regel keine Fälligkeit (Vertrag entscheidet). Arbeitstagsregel nicht freigegeben.
3. Eine SE-Gebühr mit `sev_fee_amount` berechnet diesen Nettobetrag je Einheit; die WEG-Gebühr bleibt bei `amounts_per_unit_type`.
4. `auto_post` am Rechnungsplan ist Standard aus, nur bei `auto_posting_enabled` setzbar und löst keine Buchung aus (OPEN_QUESTIONS AA10-01).
5. Die Standard-Bankregel je Dienstleister entsteht nur als Vorschlag, nie aktiv (G1, Vier-Augen).
