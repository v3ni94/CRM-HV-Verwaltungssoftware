# AO04: Spalten Erlöskonto und Stichtag der Sonderumlage (GAK-205, Rest aus AN19)

| Feld | Inhalt |
| --- | --- |
| ID | AO04 (GAK-205) |
| Titel | `special_levy.revenue_account_id` und `special_levy.reference_date` als Spalten |
| Geltungsbereich | Tabelle `special_levy` (Modul `mhvp.hoa`), alle Mandanten; betrifft G4 (Eigentümerabrechnungen), keine neue Zahlungsfunktion |
| Quellenstatus | Produktschutz und Fachliche Umsetzung; keine Rechtsnorm aus Anhang C. Offene Entscheidung: maßgeblicher Stichtag der Eigentümerzuordnung bei Eigentümerwechsel zwischen Stichtag und Fälligkeit (AN19-03, Gate G4, Eigentümer Betreiber) |
| Abnahmefall | Annex D nicht unmittelbar; Nachweis durch `apps/api/tests/integration/test_migration_0457_special_levy_columns.py` und `apps/api/tests/integration/test_w09_special_levy.py` |
| Umsetzung | Migration `0457_ao04_special_levy_columns.py` |
| Änderungsgrund | Werte lagen nur in `snapshot.terms`; als Spalten sind sie prüfbar (Fremdschlüssel auf das Erlöskonto, CHECK Stichtag nicht nach Erstfälligkeit). Eintrag 03.10.2026 (GAM-810) |

## Regeln

- `revenue_account_id` verweist auf `ledger_account`, `reference_date` darf nicht nach `first_due` liegen (CHECK `ck_special_levy_reference_date_order`).
- Die Werte werden aus `snapshot.terms` übernommen, `snapshot.terms` bleibt für den Beschlusshash unverändert. Zeilen mit unbekanntem Konto oder Stichtag nach Erstfälligkeit behalten NULL (Protokoll der Migration).
- Eine Rechtsentscheidung zum Stichtag wird nicht getroffen, siehe AN19-03.
