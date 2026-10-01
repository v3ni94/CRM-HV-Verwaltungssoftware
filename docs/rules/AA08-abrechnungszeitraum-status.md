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
     Einladungszeitpunkt. `expired` (Einladung abgelaufen) und `locked` (Anmeldung gesperrt)
     werden beim Lesen abgeleitet, gespeichert bleibt invited oder active. `revoked` bleibt
     als Endzustand erhalten (Abweichung von 6.1, siehe A-AA08-01).
- Quellenstatus (Anhang C): keine Rechtsgrundlage; Fachliche Umsetzung nach 6.1 und 6.2.
- Abnahmefall: kein Fall in Anhang D; Tests `tests/integration/test_aa08_property_status_docs.py`
  und `tests/integration/test_aa08_portal_account.py`.
- Änderungsgrund: Lückenliste 01.10.2026, GA02-01, GA02-03, GA02-04, GA02-07.
