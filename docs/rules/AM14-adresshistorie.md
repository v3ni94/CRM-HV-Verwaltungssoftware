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
- Portal-Adressvorschlag (AO09): Wird ein angenommener Vorschlag wirksam (Datum erreicht) und ist der Schalter an, wird die bisherige Hauptanschrift geschlossen (`valid_to` = Vortag des neuen Beginns, frühestens `valid_from`, `superseded_at`), statt nur das Hauptkennzeichen zu verlieren. Bei aus bleibt das Verhalten unverändert. Ein Vorschlag mit künftigem Datum schließt noch nichts.
- Kontaktzusammenführung (AO09): Bei an wird eine verschobene Hauptanschrift des Quellkontakts, die das Hauptkennzeichen an die Hauptanschrift des Zielkontakts verliert, geschlossen (`valid_to` = Vortag) und ist damit nicht mehr aktuell. Bei aus bleibt sie als weitere aktuelle Anschrift bestehen. Annahme: Das Schließen ist eine fachliche Einschätzung, die Entscheidung AM14-01 bleibt offen.
- Zeilen ohne `valid_from` erhalten beim Schließen (PUT, Portal, Zusammenführung) `valid_from` = Erstellungsdatum (`created_at`, Datum Europe/Berlin). Vermerk: Die Zeilen-Ids stehen im Ereignis `contact.address_changed` (`valid_from_backfilled_ids`) bzw. im Ergebnis der Zusammenführung (`valid_from_backfilled_ids`, `closed_address_ids`). Tests `test_ao09_address_history_flows.py`.
