# M11-finapi-authorization Sichtbarkeit unzugeordneter Konten und Verbindungsrechte

| Field | Content |
| --- | --- |
| ID | `M11-finapi-authorization` |
| Title | Neues Recht `banking:approve`; unzugeordnete finAPI-Konten nur für Banking-Administratoren |
| Scope | Domäne `banking`, Endpunkte `/banking/finapi/...`; alle Mandanten |
| Source status | Keine Rechtsnorm im Quellenregister einschlägig; Produktschutz (Abschnitt 4 des Banking-Zusatz-Master-Prompts: Softwarerolle ersetzt keine Bankvollmacht) |
| Acceptance case | Abnahmefall 15 des Banking-Zusatz-Master-Prompts; Tests `apps/api/tests/banking/test_finapi.py` |
| Implementation | `mhvp.core.auth.permissions` (Ressource `banking`, Rolle `accountant_banking` erhält `banking:approve`), `mhvp.banking.routers._can_see_unassigned` |
| Change reason | Banking-Zusatz-Master-Prompt Abschnitt 4 und 12, Auftrag 25.09.2026 |

## Regeln

- Bankverbindung anlegen, Konten zuordnen, erneute Freigabe starten und Verbindung trennen
  verlangen `banking:approve`. Lesen von Verbindungen und Konten sowie das Anstoßen eines
  Umsatzabrufs für ein bereits zugeordnetes Konto genügen die vorhandenen
  `accounting:read`/`accounting:update` Rechte.
- Ein `finapi_account_link` ohne `property_bank_account_id` (noch keinem Buchungskreis
  zugeordnet) wird in `GET /banking/finapi/connections` nur an Personen mit `banking:approve`
  oder `tenant_settings:update` ausgeliefert; für alle anderen Anfragenden erscheint das Konto
  nicht in der Liste (kein Unsichtbarmachen durch bloßes Ausblenden im Frontend).
- Mandantentrennung gilt unverändert über RLS (`tenant_rls_statements`) auf allen drei neuen
  Tabellen (`finapi_tenant_config`, `finapi_connection`, `finapi_account_link`); ein direkter
  Zugriff über eine fremde ID liefert `MHVP-CORE-0002` (nicht gefunden), nie einen Datensatz
  eines anderen Mandanten.
