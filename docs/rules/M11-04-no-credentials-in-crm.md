# M11-04 Keine Bankzugangsdaten im CRM

| Field | Content |
| --- | --- |
| ID | M11-04 |
| Title | Bank-PIN und TAN gehen bei der finAPI-Anbindung nie durch die Plattform; die gespeicherten finAPI-Zugangsdaten sind Anwendungs- und Benutzerkennung, keine Bankzugangsdaten |
| Scope | Modul `banking`, Konnektor finAPI, alle Mandanten; die FinTS-Anbindung mit PIN/TAN ist eine gesonderte Regel (`docs/rules/M11-07-fints-pin-tan.md`) |
| Source status | Produktschutz und Datensparsamkeit, keine Rechtsnorm aus dem Quellenregister. Die Anmeldung bei der Bank erfolgt im WebForm des Aggregators unter dem Benutzertoken |
| Acceptance case | keiner in Anhang D; Tests im Modul banking (finAPI) |
| Implementation | `mhvp.banking.finapi` (`FinApiCredentials`, `FinApiConnector`, nur lesend), `mhvp.banking.routers` (WebForm), Anwendungskennungen und Benutzerdaten verschlüsselt je Mandant gespeichert; `docs/integrations/finapi.md` |
| Change reason | Registereintrag nachgetragen am 02.10.2026 (GAI-517): Quelltext verweist auf diese Datei, sie fehlte. Keine Verhaltensänderung |
