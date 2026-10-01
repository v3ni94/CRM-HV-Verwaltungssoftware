# M20-04-IN Eingehender Webhook für klassifizierte Mails des Bestandsprogramms

| Field | Content |
| --- | --- |
| ID | `M20-04-IN` |
| Title | Signierter, idempotenter Eingang klassifizierter Mails je Quelle, mandantengebunden, nur mit API-Schlüssel und eigenem Recht |
| Scope | `mhvp.communication.inbound_webhook` (Endpunkte unter `/api/v1/mail/inbound`), Tabellen `inbound_mail_source` und `inbound_mail_event`, Recht `mail_inbound:ingest` (`mhvp.core.auth.permissions.MAIL_INBOUND_INGEST`), Problemcodes `MHVP-HOOK-0002`, `MHVP-HOOK-0004`, `MHVP-HOOK-0005`, `MHVP-HOOK-0006`. Gilt für jedes Fremdsystem, das Mails vorklassifiziert liefert; das Bestandsprogramm "Mail optimierung" ist der erste Anwendungsfall. Nicht Gegenstand: Anhänge als Dateien, Versand, Buchung, verbindliche Übernahme der Fremdklassifikation. |
| Source status | Keine Rechtsnorm einschlägig. Produktschutz (Integrität und Nachvollziehbarkeit von Eingängen, keine Fremdschreibzugriffe ohne Nachweis der Herkunft) und Fachliche Umsetzung aus Master-Prompt 13.4 (Mailprogramm als Webhook-Quelle oder API-Client). Offene Entscheidung: Übernahme als Modul oder Webhook-Quelle (Lückenliste M20-04, Frage AE38-01 in `docs/OPEN_QUESTIONS.md`). Datenschutz: Mailinhalt steht nur in `message`, das Ereignisprotokoll hält Kennungen und Hash. |
| Acceptance case | keine in Anhang D; Tests `apps/api/tests/integration/test_ae38_inbound_mail_webhook.py` und `apps/api/tests/unit/test_ae38_inbound_mail.py` |
| Implementation | Migration `0394`, `mhvp.communication.inbound_webhook`, Anpassung `ingest_parsed` (ohne Rohmail und ohne Blob-Speicher aufrufbar), Vertrag `docs/integrations/inbound-mail-webhook.md` |
| Change reason | Auftrag Welle 16, Paket AE38, Punkt 28 der Prioritätenliste vom 01.10.2026 (M20-04, AA16-03) |

## Regeln

1. **Zwei Nachweise je Aufruf**: API-Schlüssel des Mandanten mit dem Recht `mail_inbound:ingest`
   und HMAC-SHA256 der Quelle (`X-MHVP-Signature: t=<unix>,v1=<hex>`, gleiche Funktion wie bei den
   ausgehenden Webhooks). Ein Benutzer-Token genügt nie (403), auch nicht mit dem Recht.
2. **Prüfreihenfolge**: Schlüssel (401, 403), Größe (413, 1 MiB), Quelle im Mandanten (404, auch
   für Quellen anderer Mandanten), Signatur (401), Schalter der Quelle (409), Schema (422),
   Idempotenz. Ohne gültige Signatur erfährt der Aufrufer weder den Schalter noch etwas zum
   Inhalt.
3. **Signatur**: zeitkonstanter Vergleich, Zeitfenster 300 Sekunden in beide Richtungen, Header
   mit Nicht-ASCII-Zeichen, überlange oder unlesbare Header ergeben 401, nie einen Fehler.
4. **Idempotenz**: `event_id` je Quelle eindeutig (Datenbankindex). Dasselbe Ereignis mit
   gleichem kanonischem Inhalt: 200, gespeicherte Kennungen, nichts Neues. Anderer Inhalt unter
   derselben `event_id`: 409. Ereignis und Mail entstehen in einer Transaktion; bei einem Fehler
   bleibt beides ungespeichert und die Wiederholung wirkt.
5. **Verarbeitung wie jede eingehende Mail** (`ingest_parsed`): Zuordnung, Thread, Ticketregel
   vom 25.09.2026 (Schalter `auto_ticket` der Quelle, Standard an), Ereignis `message.received`
   für die Automation. Eine bekannte Message-ID erzeugt keine zweite Nachricht.
6. **Fremdklassifikation ist ein Vorschlag**: sie liegt unter `classification.external` und
   `classification.source`, überschreibt keine eigene Klassifikation und löst keine Freigabe, Buchung,
   Versendung oder Löschung aus (Regel 0.1.6, KI und Fremdsysteme liefern Vorschläge).
7. **Geheimnis**: verschlüsselt gespeichert, nur bei Anlage und Erneuerung sichtbar, Erneuerung
   macht das alte Geheimnis sofort ungültig. Quellen werden deaktiviert, nicht gelöscht.

## Konservative Standardwerte

Eine Quelle existiert erst nach ausdrücklicher Anlage durch `tenant_settings:update`; ohne Quelle
und ohne Schlüssel nimmt die Plattform nichts an. Ein neuer Schlüssel erhält nur den einen
Geltungsbereich, den Administratorrollen vergeben können. `auto_ticket` folgt der entschiedenen
Regel; wer keine Tickets aus dieser Quelle will, schaltet es je Quelle aus.
