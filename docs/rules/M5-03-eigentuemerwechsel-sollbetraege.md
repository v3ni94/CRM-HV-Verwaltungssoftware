# M5-03 Eigentümerwechsel in der Oberfläche mit Übernahme der laufenden Sollbeträge

| Field | Content |
| --- | --- |
| ID | `M5-03` |
| Title | Eigentümerwechsel als Dialog auf Vertrags- und Einheitenseite; das bisherige Eigentum endet am Vortag des Eigentumsübergangs, das neue beginnt am Übergang; die am Übergang gültigen Sollbeträge, der Zahlungsplan und die vertragsbezogenen Umlagewerte werden als tatsächliche Kopie ab dem Übergang übernommen |
| Scope | `GET /contracts/{id}/ownership-transfer/preview?title_transfer_date=` (`contracts:read`, nur lesend), `POST /contracts/{id}/ownership-transfer` (`contracts:update`) mit `new_party_id` oder `new_contact_id` (eigene Partei des Kontakts wird ermittelt oder angelegt), `carry_over_amounts` (Standard an), `notes`, `document_id` (Nachweis, Verknüpfung `evidence` am neuen Vertrag); Web `OwnershipTransfer` auf `/vertraege/{id}` und `/vermietung/einheit/{id}`; alle Mandanten, kein Geldfluss, keine Buchung |
| Source status | Fachliche Umsetzung (Master-Prompt 6.9.2, Fälle D15 bis D17: Erwerber erhält ein eigenes Debitorenkonto, alte offene Posten bleiben beim Veräußerer). Die Übernahme der Sollbeträge ist eine Datenübernahme ohne rechtliche Aussage: wer Vorschussschuldner ist und wie die Abrechnungsspitze zwischen Veräußerer und Erwerber zu adressieren ist, regelt W07 (7.8), die nicht freigegeben ist; Rechtsprechungsabgleich P01 offen (`docs/OPEN_QUESTIONS.md`, M24-01). Keine Aufteilung von Beträgen zwischen Veräußerer und Erwerber |
| Acceptance case | D16, D17 (bestehend, `test_m5_contracts.py`); Tests `apps/api/tests/integration/test_ownership_transfer.py` (Vorschau ohne Wirkung, Übernahme mit festen Erwartungswerten: Hausgeld 300,00 und Rücklage 50,00 ab 01.04.2026 offen, Vorwerte enden 31.03.2026, Historie 250,00 bis 31.12.2024 unverändert, Zahlungsplan und Umlagewert Personen 2 übernommen, Kontakt als Erwerber mit eigener Partei, Nachweis verknüpft, Übernahme abwählbar, zweiter Wechsel 422, Datum vor Beginn 422, genau eine Erwerberangabe 422, unbekannter Kontakt oder Dokument 404 ohne Änderung, Leserolle 403, Fremdmandant 404), Vitest `OwnershipTransfer.test.tsx` |
| Implementation | Keine Migration. `mhvp.contracts.services.standing_amounts`, `carry_over_standing_amounts`, `close_allocation_values`; `mhvp.contacts.services.party_for_contact`; Fehlercode `MHVP-CONTR-0001` (Eigentümerwechsel nicht möglich: kein Eigentum, bereits beendet, Übergang nicht nach Beginn, Erwerber gleich Veräußerer); Ereignis `contract.ownership_transferred` mit Anzahl übernommener Zeilen und Dokument; BFF-Allowlist ergänzt; i18n `OwnershipTransfer` |
| Change reason | Betreiberwunsch 28.09.2026 (Lücken in der Software, Anleitung Eigentümerwechsel): keine Schaltfläche in der Oberfläche, Sollbeträge mussten nach dem Wechsel von Hand nacherfasst werden |

## Regeln

- Übertragbar ist nur ein offenes Eigentumsverhältnis; der Eigentumsübergang muss nach dem
  Beginn des bisherigen Eigentums liegen; der Erwerber darf nicht die bisherige Partei sein
  (422 `MHVP-CONTR-0001`).
- Das bisherige Eigentum endet am Vortag: Zahlungen und Zahlungspläne enden dort wie bei
  jeder Beendigung (`end_contract`), vertragsbezogene Umlagewerte ebenso
  (`close_allocation_values`; Werte mit Beginn nach dem Ende bleiben unverändert). Zahlungen
  oder Zahlungspläne mit Beginn nach dem Übergang lehnen den Wechsel wie bisher ab.
- Übernahme (Standard an): jede am Übergang gültige Zahlung, der gültige Zahlungsplan und
  jeder gültige Umlagewert werden mit `valid_from = Übergang` und dem ursprünglichen
  `valid_to` (offen bleibt offen) am neuen Vertrag angelegt; Beträge, Steuersatz,
  Zahlungsart, Grund, Schlüssel und Werte bleiben unverändert. Ohne Übernahme entsteht der
  neue Vertrag ohne Sollbeträge.
- Der Erwerber kann als Partei oder als Kontakt angegeben werden; bei einem Kontakt wird die
  Partei verwendet, deren einziges Mitglied der Kontakt in der Rolle primary ist, sonst wird
  sie angelegt. Gemeinschaftsparteien (mehrere Mitglieder) werden nie automatisch gebildet.
- Notiz und Nachweis: `notes` wird am neuen Vertrag gespeichert; `document_id` verknüpft das
  Dokument als `evidence` mit dem neuen Vertrag (Dokument muss im Mandanten existieren, 404).
- Keine Aufteilung der Jahresabrechnung, keine Umbuchung von Rückständen, keine Buchung: der
  Wechsel ist eine Stammdatenänderung. Der Dialog nennt das ausdrücklich (W07, P01).
