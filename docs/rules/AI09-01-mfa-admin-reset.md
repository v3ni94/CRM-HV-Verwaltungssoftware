# AI09-01 Zurücksetzen des zweiten Faktors durch Mandantenadministratoren und Sicherheitsereignisse der Anmeldung

| Field | Content |
| --- | --- |
| ID | `AI09-01` |
| Title | Zurücksetzen des zweiten Faktors im Vier-Augen-Verfahren (Schalter `mfa_admin_reset_enabled`, Standard aus) und Protokoll der Anmeldeereignisse |
| Scope | Endpunkte `GET/PUT /auth/mfa-reset/settings`, `GET/POST /auth/mfa-reset/requests`, `POST /auth/mfa-reset/requests/{id}/approve` und `/reject`; Tabellen `auth_mfa_reset_setting` und `auth_mfa_reset_request` (RLS, Migration 0442); Ereignisse `auth.login_succeeded`, `auth.login_failed`, `auth.account_locked`, `auth.password_changed`, `auth.totp_enabled`, `auth.totp_disabled`, `auth.passkey_registered`, `auth.passkey_revoked`, `auth.session_revoked`, `auth.oidc_token_issued`, `auth.mfa_reset` in jedem Mandanten mit aktiver Mitgliedschaft |
| Source status | Keine Rechtsnorm im Quellenregister (annex C). Fachliche Umsetzung von Abschnitt 3.4 und 16 (Sicherheit, Audit); Vier-Augen und Standard aus sind Produktschutz. Variantenwahl (Wiederherstellungscodes, Admin-Zurücksetzen oder beides) ist offen: Frage AI09-01 in `docs/OPEN_QUESTIONS.md`, Eigentümer Timo Müller |
| Acceptance case | keine in annex D; Test `apps/api/tests/integration/test_ai09_auth_audit_mfa_reset.py` (Ereignisse ohne Passwort und Code, Sperre, Schalter aus 409, Recht 403, Mandantentrennung 404, Antragsteller darf nicht freigeben 409, nach Freigabe Anmeldung nur mit Passwort, Benachrichtigung) |
| Implementation | `mhvp.core.auth.audit`, `mhvp.core.auth.mfa_reset`, Fehlercodes `MHVP-AUTH-0016` bis `0018` |
| Change reason | Welle 20, Paket AI09, Befunde GAH-301 und GAH-302 |
