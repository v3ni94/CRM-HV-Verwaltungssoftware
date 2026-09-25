# M11-05 Zugangsdaten nie im CRM (Bank-WebForm)

| Field | Content |
| --- | --- |
| ID | `M11-05` |
| Title | Bank-PIN, TAN und Online-Banking-Zugangsdaten passieren die Plattform nie |
| Scope | Domäne `banking`, jede Online-Banking-Anbindung (heute: finAPI Access als Aggregator); alle Mandanten |
| Source status | Keine Rechtsnorm im Quellenregister einschlägig; Produktschutz (Banking-Zusatz-Master-Prompt Abschnitt 6, PSD2/XS2A Grundprinzip der Drittanbieteranbindung ohne eigene Kontoführung) |
| Acceptance case | Banking-Zusatz-Master-Prompt Abschnitt 6 und 8; Tests `apps/api/tests/unit/test_banking_connectors.py`, `apps/api/tests/integration/test_m11_finapi.py` |
| Implementation | `mhvp.banking.connectors.BankConnector` (`start_connection`/`refresh_consent` geben nur eine Anbieter-URL zurück), `mhvp.banking.finapi.FinApiConnector`, CRM-Wizard `apps/web-crm/src/components/banking/FinApiConnections.tsx` |
| Change reason | M11-finapi Umbau auf PSD2/XS2A als Primärweg (Betreiberentscheidung 25.09.2026) |

## Regeln

- Jede WebForm-basierte Bankanbindung (`start_connection`, `refresh_consent`) liefert
  ausschließlich eine vom Anbieter gehostete Freigabe-URL (`WebFormHandle.url`). Der Browser
  wird dorthin umgeleitet; Bank-Login, PIN, TAN und Kontofreigabe finden ausschließlich auf
  dieser Anbieterseite statt.
- Kein Endpunkt, kein Formularfeld und keine gespeicherte Konfiguration der Plattform nimmt
  eine Bank-PIN, TAN oder ein Bank-Passwort entgegen. `FinApiTenantConfig` speichert nur die
  Anwendungs-Zugangsdaten des Mandanten gegenüber dem Aggregator (`client_id`,
  `client_secret`), verschlüsselt (`EncryptedText`), niemals eine Bank-Zugangsdaten des
  Endkunden.
- Ein zurückkehrender Browser-Redirect aus dem WebForm ist kein Vertrauensbeweis: der Status
  wird serverseitig mit den eigenen Anbieter-Zugangsdaten erneut abgefragt
  (`complete_connection`/`check`), bevor ein Konto oder ein Saldo übernommen wird
  (Banking-Zusatz-Master-Prompt Abschnitt 6 und 8).
- Eine serverseitige Banksuche wird nicht nachgebildet, solange kein verifizierter
  Such-Endpunkt vorliegt (`docs/integrations/finapi.md`): die Bankauswahl geschieht innerhalb
  des WebForms selbst, nicht durch eine erfundene Anfrage der Plattform.
