# ADR 0028: Gemeinsamer Signaturhelfer für Webhooks mit Zeitfenster

- Status: Accepted
- Date: 2026-10-02

## Context

Eingehende und ausgehende Webhooks (Objektakte, Paperless, Telefonie, Schadenstool, ausgehende Webhooks) hatten je eigene HMAC-Prüfungen mit unterschiedlicher Zeitfensterlogik (Befund GAH-215, Nachtrag zu GAI-516).

## Decision

`apps/api/src/mhvp/core/hmac_signature.py` ist der einzige Ort für Signatur, Zeitfenster und Vergleich:

- Signiert wird `"{timestamp}." + Rohkörper` mit HMAC-SHA256 (`mac_hex`).
- Zeitfenster 300 Sekunden (`DEFAULT_WINDOW_SECONDS`), geprüft mit Betrag der Differenz (`within_window`).
- Vergleich in konstanter Zeit (`hmac.compare_digest` in `equal`).
- `check` liefert `None` oder `missing`, `stale`, `bad`.
- Die Aufrufer behalten ihr Wire-Format: `sha256=<hex>` mit eigenem Zeitstempel-Header (`objektakte/webhook.py`, `documents/paperless_webhook.py`, `communication/telephony.py`, `integrations/schadenstool/signature.py`) oder `t=<ts>,v1=<hex>` in einem Header (`core/webhooks.py:159`).

## Consequences

- Eine Korrektur wirkt für alle Webhooks. Ein neuer Webhook nutzt den Helfer, keine eigene Prüfung.
- Das Zeitfenster schützt vor Wiedereinspielung nur begrenzt; Idempotenz (B08) bleibt Aufgabe des Empfängers.
- Das Wire-Format bleibt je Gegenstelle verschieden, eine Vereinheitlichung bräuchte Abstimmung mit den Partnern.

## Alternatives considered

- Einheitliches Wire-Format für alle: bricht bestehende Gegenstellen.
- Je Modul eigene Prüfung: Doppelung und Abweichungen, Anlass der Änderung.

## References

- `docs/MASTER-PROMPT.md` Kapitel 16 (Sicherheit)
