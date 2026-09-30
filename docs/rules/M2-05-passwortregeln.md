# M2-05 Passwortregeln: Mindestlänge 12 und Prüfung gegen kompromittierte Passwörter

| Field | Content |
| --- | --- |
| ID | `M2-05` |
| Title | Passwortregel beim Setzen und Ändern: 12 bis 128 Zeichen, keine Leerzeichen am Anfang oder Ende, kein Passwort aus der Liste kompromittierter Passwörter |
| Scope | Alle Stellen, die ein Passwort setzen: eigenes Passwort ändern (`POST /auth/password`), Mitglied anlegen und Passwort zurücksetzen (Mandantenverwaltung), Benutzer anlegen (`mhvp.platform.services`), Einladung annehmen im Portal. Bestehende Passwörter bleiben bis zur nächsten Änderung gültig. Kontosperre (10 Fehlversuche, 15 Minuten) unverändert |
| Source status | Abschnitt 3.4 verlangt Passwortregeln nach BSI-Empfehlung ohne Zahlenwerte; kein Rechtssatz aus Anhang C. Werte sind Betreiberentscheidung 9 a vom 30.09.2026 (Lückenliste 30.09.2026), ersetzt die Entscheidung M2-01 vom 26.09.2026 (Mindestlänge 6) |
| Acceptance case | Kein Fall aus Anhang D; Unit `apps/api/tests/unit/test_m2_security.py`, `apps/api/tests/unit/test_p14_auth_security.py`; Integration `apps/api/tests/integration/test_m2_platform.py::test_password_change_policy_boundaries` |
| Implementation | `mhvp.core.auth.passwords.policy_violation`, `mhvp.core.auth.breached` (mitgelieferte SHA-1-Liste, optionale Hashdatei über `MHVP_BREACHED_PASSWORDS_FILE`, Schnittstelle `BreachedSource`, kein Netzwerkaufruf), CRM `minLength=12`, Portal Einladung 12 Zeichen |
| Change reason | Lückenliste 30.09.2026 Befund M2-05, Entscheidung 9 a |

## Regeln

- Mindestlänge 12, Höchstlänge 128 Zeichen, keine Zusammensetzungsregeln.
- Geprüft wird der SHA-1-Wert (Großbuchstaben, Format der öffentlichen Pwned-Passwords-Listen)
  des eingegebenen Passworts und seiner Kleinschreibung.
- Mitgeliefert wird eine kleine Liste häufiger Passwörter ab 12 Zeichen. Eine größere Liste
  stellt der Betreiber als lokale Datei bereit (eine Zeile je `SHA1` oder `SHA1:Anzahl`).
  Fehlt die Datei oder ist sie nicht lesbar, gilt die mitgelieferte Liste; Anmeldung und
  Passwortänderung scheitern daran nicht.
- Es gibt keinen Netzwerkaufruf, auch nicht über das k-Anonymitätsverfahren.
