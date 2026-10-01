# AA08 Abrechnungszeitraum mit Status, Dokumentverweise, Portalzugang

- ID: AA08-abrechnungszeitraum-status (GA02-01, GA02-03, GA02-04, GA02-07)
- Geltungsbereich: Objektstammdaten (`property_billing_period`, `building`, `maintenance_item`,
  `service_provider_relation`) und Portalzugänge (`portal_account`) je Mandant.
- Regeln:
  1. Abrechnungszeitraum: Status offen, Ergebnisse erstellt, bestätigt, abgeschlossen
     (`open`, `results_created`, `confirmed`, `closed`). Wechsel nur um einen Schritt vor oder
     zurück, nie aus `closed`. `closed` setzt `locked_at` und verbietet das Löschen
     (`MHVP-PROP-0006`, `MHVP-PROP-0007`). Bei Betriebskostenzeiträumen braucht der Schritt
     zu `results_created` eine berechnete Abrechnung des Objekts im Zeitraum und der Schritt
     zu `closed` darf keine Abrechnung im Entwurf mehr im Zeitraum haben. Der Status ist ein
     Stammdatenkennzeichen, er bucht nichts und öffnet kein Gate (G3 bleibt maßgeblich).
  2. Energieausweis: Verweis auf ein Dokument des Mandanten (`energy_certificate_document_id`),
     nur Referenz, keine Ableitung von Kennwerten.
  3. Wartungsposten und Dienstleisterverhältnis: Dokumentverweise (`documents`), geprüft gegen
     den Mandanten, keine Duplikate.
  4. Portalzugang: `roles` folgt den Zugriffsrechten (tenant, owner), `invited_at` ist der
     Einladungszeitpunkt. Seit AB08 (Version 1.58.0) wird das Statusmodell 6.2 gespeichert
     (`mhvp.portal.status`, Beat-Job `mhvp.portal.sync_account_status` alle 15 Minuten):

     | Von | Nach | Auslöser | Schreibt |
     | --- | --- | --- | --- |
     | (neu) | `not_invited` | Anlage mit `send_invitation=false` | keine Einladung, `invited_at` leer |
     | (neu) | `invited` | Anlage mit Einladung | `invited_at`, Ablaufzeitpunkt |
     | `not_invited` | `invited` | Einladung per Mail oder Brief | `invited_at` neu |
     | `invited` | `active` | Annahme der Einladung | `activated_at`, Code entwertet |
     | `invited` | `expired` | Beat-Job, Ablaufzeitpunkt überschritten | nur Status |
     | `expired` | `invited` | erneute Einladung (Mail oder Brief) | neuer Code, `invited_at` |
     | `active` | `locked` | Beat-Job, Benutzer gesperrt oder deaktiviert | nur Status |
     | `locked` | `active` | Beat-Job, Sperre aufgehoben, Konto war aktiviert | nur Status |
     | jeder Wert | `revoked` | Entzug des Mitarbeiterzugangs (Plattform) | Status, Endzustand |

     Der Job ist idempotent (zweiter Lauf ändert nichts) und fasst `revoked` nie an. Zwischen
     zwei Läufen wendet die Liste dieselbe Regel beim Lesen an. Eine gesperrte Anmeldung wird
     erst nach Ablauf der Sperre wieder angenommen, weil `locked` die Portalanmeldung weiter
     zulässt (die Anmeldung selbst prüft die Sperre). `last_login_at` steht am Benutzer und
     wird bei jeder erfolgreichen Anmeldung (Passwort, Magic Link, TOTP) gesetzt. Es werden nie
     Werte außerhalb der Check-Constraint `ck_portal_account_status` (Migration 0310)
     geschrieben. `revoked` bleibt als Endzustand erhalten (Abweichung von 6.1, A-AA08-01).
- Quellenstatus (Anhang C): keine Rechtsgrundlage; Fachliche Umsetzung nach 6.1 und 6.2.
- Abnahmefall: kein Fall in Anhang D; Tests `tests/integration/test_aa08_property_status_docs.py`
  `tests/integration/test_aa08_portal_account.py` und `tests/integration/test_ab08_portal_status.py`.
- Änderungsgrund: Lückenliste 01.10.2026, GA02-01, GA02-03, GA02-04, GA02-07.
