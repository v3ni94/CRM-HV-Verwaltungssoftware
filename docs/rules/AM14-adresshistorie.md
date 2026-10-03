# AM14-adresshistorie Adresshistorie der Kontakte

| Field | Content |
| --- | --- |
| ID | `AM14-adresshistorie` |
| Title | Frühere Anschriften eines Kontakts werden bei aktivem Mandantenschalter geschlossen statt gelöscht und sind zum Stichtag abrufbar |
| Scope | `mhvp.contacts.address_history`, `services.write_children`, `GET /contacts/{id}/addresses` (`as_of`, `include_history`), `GET/PUT /contact-address-history`, ORM-Filter in `mhvp.contacts.models`; CRM `AddressHistoryPanel` (Kontakt, Stammdaten), Regel `contact-address-history` auf der Seite Fachliche Regeln. Migration 0452 |
| Source status | Fachliche Umsetzung und Produktschutz (Zustellnachweis an die damalige Anschrift). Keine Rechtsregel: Umfang (nur Postanschrift oder alle Arten), Aufbewahrungsdauer früherer Anschriften und Behandlung bestehender Zeilen ohne `valid_from` sind offen (OPEN_QUESTIONS AM14-01, Betreiber und Datenschutz). Daher Schalter, Standard aus (heutiges Ersetzen); das Löschkonzept bleibt unverändert |
| Acceptance case | Keiner in Anhang D. Tests `apps/api/tests/integration/test_an05_address_history.py` (Schalter aus unverändert und 422, Schalter an schließt Hilden mit gültig bis Vortag, Stichtag Vortag liefert Hilden und Mettmann, heute Erkrath und Mettmann, Fremdmandant 404, Leserecht 403 beim Schalter, Validierung 422, Round-Trip Migration 0452), CRM vitest `AddressHistoryPanel.test.tsx` |
| Change reason | GAJ-610 Rest aus Welle 23 (AM14): Schema-Entwurf umgesetzt, Entscheidung weiterhin offen |

## Regeln

- Schalter aus: Anschriften werden beim vollständigen Ändern ersetzt; Stichtag und Historie antworten 422 `MHVP-CONT-0034`.
- Schalter an: unveränderte Anschriften (gleiche Art und gleicher Inhalt) bleiben bestehen, geänderte oder entfernte erhalten `valid_to` = Vortag (frühestens `valid_from`) und `superseded_at`, neue erhalten `valid_from` = heute (Europe/Berlin).
- Stichtag: `valid_from` leer oder kleiner gleich Stichtag und `valid_to` leer oder größer gleich Stichtag. Wird eine Anschrift am Tag ihres Beginns ersetzt, gelten an diesem Tag alte und neue Anschrift.
- Geschlossene Zeilen sind für Briefe, Exporte und Abgleiche unsichtbar; eine Löschung nach Art. 17 DSGVO entfernt auch sie. Ausschalten löscht nichts.
