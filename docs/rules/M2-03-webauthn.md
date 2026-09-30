# M2-03 Passkeys (WebAuthn) als optionaler zweiter Faktor

| Field | Content |
| --- | --- |
| ID | `M2-03` |
| Title | WebAuthn/Passkeys optional neben TOTP; vorbereitet, nicht freigeschaltet |
| Scope | Alle Benutzer. TOTP bleibt freiwillig (Betreiberentscheidung 9 a). Solange keine Prüfbibliothek freigegeben ist, antworten Registrierung und Prüfung mit `MHVP-AUTH-0012` (503); ein Passkey ersetzt keinen zweiten Faktor |
| Source status | Abschnitt 3.4 (WebAuthn/Passkeys optional); Produktschutz. Eine selbst geschriebene Prüfung (CBOR/COSE, Signatur, Origin, Zähler) wäre eine ungeprüfte Sicherheitskomponente und wird nicht gebaut |
| Acceptance case | Kein Fall aus Anhang D; Unit `test_p14_auth_security.py::test_webauthn_not_available`; Integration `test_p14_member_scope_webauthn.py::test_webauthn_prepared_not_available` |
| Implementation | Tabelle `webauthn_credential` (Migration 0263, Plattformtabelle ohne RLS wie `trusted_device`), `mhvp.core.auth.webauthn`, Endpunkte `GET /auth/webauthn/status`, `GET /auth/webauthn/credentials`, `DELETE /auth/webauthn/credentials/{id}`, `POST /auth/webauthn/register/options` und `/register/verify` (503) |
| Change reason | Lückenliste 30.09.2026 Befunde M2-03 und S16-01, Entscheidung 9 a; Bibliothek nicht in `uv.lock` (docs/OPEN_QUESTIONS.md P14-02) |
