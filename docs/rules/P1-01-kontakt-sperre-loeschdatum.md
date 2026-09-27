# P1-01 Kontakt: Sperre mit Sperrdatum, Löschprofil und vorgemerktes Löschdatum

| Field | Content |
| --- | --- |
| ID | `P1-01` |
| Title | Kontakt sperren setzt das Sperrdatum; ein freigegebenes Löschprofil erzeugt ein vorgemerktes Löschdatum; die Löschung bleibt ein manueller Schritt im Vier-Augen-Prinzip, kein automatischer Löschlauf |
| Scope | `mhvp.contacts` (`Contact.blocked_at`, `retention_profile_id`, `delete_after`, Migration 0147), `PUT /contacts/{id}`, `POST /contacts`, `GET /contacts?blocked=true` (Sperrliste), Kontaktseite Stammdaten; alle Mandanten |
| Source status | Fachliche Umsetzung (Masterprompt Ergänzung 27.09.2026, Abschnitt 4.1 Sperre und Löschung) mit Betreiberentscheidung 26.09.2026: Löschdatum nur als Vormerkung. Rechtsgrundlage der Fristen: M6-04 (Prüfung Steuerberatung offen, S05, S06); dieser Eintrag legt keine Frist fest, er übernimmt sie aus dem freigegebenen Profil |
| Acceptance case | `tests/integration/test_contacts_p1.py` (`test_block_sets_date_and_block_list`, `test_retention_profile_reservation_only`, `test_delete_after_arithmetic`, `test_tenant_separation`) |
| Implementation | `services.apply_fields` (Sperrdatum), `services.apply_retention` und `services.delete_after` (Beginn: Sperrdatum, sonst Tag der Zuordnung; Startregeln `end_of_year_*` runden auf den 31.12.; `permanent` ergibt kein Datum; Entwurfsprofile 422). Keine Löschung, kein Job: die Löschung läuft weiter über `DELETE /contacts/{id}` (Recht `contacts:delete`) |
| Change reason | Lückenliste P1 vom 26.09.2026, AP1: Sperrdatum, Löschprofil, Löschdatum und Sperrliste fehlten |

## Produktschutz

Das vorgemerkte Löschdatum ist kein Nachweis einer Löschpflicht und löst keine Aktion aus.
Ein automatischer Löschlauf ist eine offene Entscheidung (Eigentümer: Betreiber, betroffene
Gates keine; Datenschutzprüfung vor Aktivierung erforderlich).
