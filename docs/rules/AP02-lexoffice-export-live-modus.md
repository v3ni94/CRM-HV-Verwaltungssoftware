# AP02 lexoffice: Export ohne Doppelbeleg, Schlüssel nur an den Anbieter, Live-Betrieb je Schnittstelle

| Field | Content |
| --- | --- |
| ID | `AP02-lexoffice-export-live-modus` |
| Title | lexoffice Export idempotent, Basisadresse nur Lexware, Fehler ohne Fremddaten, Live-Betrieb je Schnittstelle als Mandantenschalter |
| Scope | `mhvp.integrations.lexoffice`, `mhvp.integrations.routers` (`/integrations/lexoffice/*`), `mhvp.integrations.lexoffice_ext.services.check_base_url` und `client_for`, `mhvp.integrations.live_mode` (`/integrations/live-modes`), `mhvp.communication.postal` (Umstellung auf live, Einreichung); Tabellen `lexoffice_export_link` (Spalten `status`, `idempotency_key`, `voucher_number`), `integration_live_mode`; Schalter `integrations.live_mode` |
| Source status | Produktschutz. Abschnitt 12 (Idempotenz, Sicherheit der Zugänge, Fehler nach RFC 9457), Regel 0.1.1 und 0.1.13, ADR 0004; keine Norm aus dem Quellenregister. Die Gatebindung des Live-Betriebs ist offen (AP02-01, Betreiber, G1/G2). |
| Acceptance case | Anhang D Fall 11 sinngemäß (schreibender Timeout); Tests `apps/api/tests/integration/test_ap02_lexoffice_idempotency.py`, `apps/api/tests/unit/test_ap02_lexoffice_hardening.py`, `apps/web-crm/src/lib/gam710-sums.test.ts` |
| Implementation | Migration 0459, Fehlercodes `MHVP-LEXO-0018` (Ergebnis ungeklärt), `MHVP-LEXO-0019` (Live-Betrieb gesperrt) |
| Change reason | Lückenanalyse GAL-201, GAL-202, GAL-203, GAL-207 und GAM-710 (Welle 26) |

## Regeln

- Export (Belege, Kontakte): Ein schreibender Aufruf ohne Antwort (Zeitüberschreitung, 504)
  hinterlässt den Exportsatz im Zustand `unknown`. Eine Wiederholung sendet keinen zweiten
  Anlageaufruf. Belege mit Belegnummer werden über die Belegliste gesucht und bei genau einem
  Treffer übernommen (dieselbe Lexware-Id); sonst bleibt der Satz ungeklärt, bis eine Person
  ausdrücklich mit `force` erneut exportiert. Jeder Versuch trägt einen festen
  Idempotenzschlüssel je Mandant, Art und Datensatz.
- Basisadresse: immer https, ohne Zugangsdaten in der Adresse, ohne Query; in Staging und
  Produktion nur `api.lexware.io` oder `api.lexoffice.io` ohne Pfad und Port. Geprüft beim
  Speichern und erneut vor jedem Aufruf, damit kein gespeicherter Altwert den Schlüssel
  an Dritte sendet.
- Fehler: Die Rohantwort des Anbieters erscheint nie in der Problemantwort; nur Status,
  Feldnamen der Fehlerliste und die Namen bekannter Schlüssel. `Retry-After` bei 429 wird als
  Erweiterung und Kopfzeile weitergegeben.
- Live-Betrieb: Schalter je Mandant und Schnittstelle (lexoffice, LetterXpress, finAPI).
  Ohne Eintrag gilt das heutige Verhalten. `live_allowed=false` sperrt, `required_gate` bindet
  an eine Freigabestufe. Welche Bindung gilt, entscheidet der Betreiber (AP02-01); finAPI wird
  nur angezeigt.
- Beträge im CRM werden in ganzen Cent summiert und mit `formatEur` ausgegeben (GAM-710).
