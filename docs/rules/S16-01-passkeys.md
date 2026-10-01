# S16-01 Passkeys (WebAuthn): zweiter Faktor und optionale Anmeldung ohne Passwort

| Field | Content |
| --- | --- |
| ID | `S16-01` |
| Title | Passkey als zweiter Faktor neben TOTP; je Passkey optional Anmeldung ohne Passwort (nur CRM) |
| Scope | Alle Benutzer mit eigenem Konto. Schalter `MHVP_WEBAUTHN_ENABLED` (Standard aus) plus RP ID und erlaubte Origins. Portal: nur zweiter Faktor, die Registrierung im Portal erzwingt `passwordless: false` |
| Source status | Abschnitt 3.4 (WebAuthn/Passkeys optional), Betreiberentscheidung 9 a vom 30.09.2026; Produktschutz. Protokollprüfung nach WebAuthn Level 2 (Abschnitte 7.1 und 7.2) in eigenem Code, Signaturprüfung über die freigegebene Bibliothek `cryptography`; keine Rechtsgrundlage |
| Rules | Challenge 32 Byte, 300 Sekunden gültig, genau einmal verwendbar (vor jeder Prüfung gelöscht); `type`, `challenge` und `origin` des clientDataJSON müssen passen, `crossOrigin` wird abgelehnt; RP-ID-Hash muss passen; Benutzeranwesenheit Pflicht, Benutzerverifikation Pflicht ohne Passwort; Signaturzähler muss streng steigen (nur beide 0 ist zulässig), sonst Ablehnung als möglicher Klon; Attestierung nur `none`; Fehlversuche zählen zur Kontosperre |
| Acceptance case | Kein Fall aus Anhang D; Unit `tests/unit/test_webauthn_verify.py`; Integration `tests/integration/test_s16_webauthn_login.py`; Frontend `Passkeys.test.tsx` (CRM und Portal), `lib/webauthn.test.ts` |
| Implementation | `mhvp.core.auth.webauthn`, `core/auth/routers.py` (`/auth/webauthn/register/*`, `/auth/login/webauthn/*`), Spalte `webauthn_credential.passwordless` (Migration 0298), CRM Anmeldung und Meine Daten, Portal zweiter Faktor und Sicherheit |
| Change reason | Lückenliste 30.09.2026 S16-01 und Rest M2-03; ersetzt den Stand "vorbereitet" der Regel M2-03 |
