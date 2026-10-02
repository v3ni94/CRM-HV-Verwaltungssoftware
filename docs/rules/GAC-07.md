# GAC-07 Systemrolle Versicherungsmakler hinter Mandantenschalter

| Field | Content |
| --- | --- |
| ID | `GAC-07` |
| Title | Rechte der Systemrolle `insurance_broker` nur bei gesetztem Mandantenschalter |
| Scope | Jeder Mandant; Berechtigungsermittlung `mhvp.core.auth.permissions.effective_permissions`, Schalter in `tenant_settings.sources` |
| Source status | Keine Rechtsnorm im Quellenregister (annex C); Produktschutz nach Anhang A.4. Umfang der Makler-Sicht ist eine offene Entscheidung (OPEN_QUESTIONS GAC-07) |
| Acceptance case | keiner in annex D; Test `apps/api/tests/integration/test_ag03_broker_access.py` |
| Change reason | Lückenanalyse GAC-07: die Rolle hatte keine Berechtigung und keinen erkennbaren Zugriffsweg |

## Regeln

- Standard: Mandantenschalter `insurance_broker_access` aus, die Rolle hält kein Recht.
- Schalter an: die Rolle erhält `insurance:read` und `claims:read` (nur lesend). Die Objektbindung
  erfolgt über die Objektzuordnung des Mitglieds (`membership.property_ids`).
- Die Fachendpunkte für Versicherungsverträge und Schadenfälle sind an die Rechte noch nicht
  angeschlossen. Der Schalter öffnet daher keinen Datenzugriff, bis die Entscheidung gefallen ist.
- Änderung nur mit `tenant_settings:update`, Wirkung sofort (Rechtecache wird geleert).
- Rollenauswahl im CRM: "ohne Zugriff (Entscheidung offen)".
