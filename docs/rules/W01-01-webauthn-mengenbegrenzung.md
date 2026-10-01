# W01-01 Mengenbegrenzung der Passkey-Optionen

- ID: W01-01
- Geltungsbereich: `POST /auth/login/webauthn/options` und `POST /auth/webauthn/register/options`.
- Regel: Festes Zeitfenster (Standard 300 s) je Client-Adresse (Standard 60 Aufrufe) und je Benutzer (Standard 20 Aufrufe, bei Anmeldung nur mit `mfa_token`, bei Registrierung immer). Überschreitung ergibt 429 mit Code MHVP-CORE-0006 und `Retry-After`. Konfigurierbar über `webauthn_options_limit_per_ip`, `webauthn_options_limit_per_user`, `webauthn_options_window_seconds`.
- Quellenstatus Anhang C: Produktschutz, keine Rechtsgrundlage. Die Challenge-TTL von 300 s bleibt unverändert.
- Abnahmefall: Tests `test_webauthn_options_rate_limit` und `test_webauthn_login_options_ip_limit` (Grenze erreicht, Reset nach Fenster).
- Änderungsgrund: Schutz vor Challenge-Flut in Redis (U04-01 Prüfung).
