# INT-SDT-01 Schadenbearbeiter: Austausch von Schadentickets nur nach AVV, nur ausdrücklich gewählte Inhalte

| Field | Content |
| --- | --- |
| ID | `INT-SDT-01` |
| Title | Anbindung an den externen Schadenbearbeiter (Schadenstool, MDV/midive): Aktivierung erst nach bestätigtem AVV, Übermittlung nur ausdrücklich gewählter Inhalte, Übernahme fremder Tickets nur nach Bestätigung |
| Scope | Modul `mhvp.integrations.schadenstool`, Tabellen `schadenstool_tenant_config`, `schadenstool_ticket_link`, `schadenstool_item_link`, `schadenstool_outbox`, `schadenstool_event`; alle Mandanten, je Mandant Schalter `enabled` (Standard aus); keine Buchung, kein Geldfluss, Gates G1 bis G5 unberührt |
| Source status | Produktschutz. Vertragsentwurf `docs/integrations/schadenstool-hv-api-v1-vertrag.md` (Stand 28.09.2026, Entwurf der Gegenseite); keine Norm aus dem Quellenregister. Die AVV-Pflicht vor Aktivierung setzt Regel 0.1.13 um, sie ersetzt keine datenschutzrechtliche Prüfung. |
| Acceptance case | kein Anhang-D-Fall; Tests `apps/api/tests/integration/test_schadenstool.py`, `apps/api/tests/unit/test_schadenstool_unit.py`, `apps/web-crm/src/components/settings/SchadenstoolSettings.test.tsx`, `apps/web-crm/src/components/tickets/SchadenstoolPanel.test.tsx` |
| Implementation | Migration 0222, Fehlercodes `MHVP-SDT-0001` bis `0006`, Celery `mhvp.integrations.schadenstool.process` (jede Minute) und `.pull` (alle 15 Minuten), Plan `docs/plans/M-schadenstool.md`, Betreiberdoku `docs/integrations/schadenstool.md` |
| Change reason | Betreiberauftrag vom 28.09.2026 (Schadenbearbeiter bidirektional anbinden) |

## Regeln

- Aktivieren (`enabled=true`) setzt voraus: Basisadresse, Integrationstoken, Webhook-Geheimnis
  und die AVV-Bestätigung (Datum und bestätigendes Mitglied, `MHVP-SDT-0005`). Ob der AVV
  tatsächlich vorliegt, bestätigt der Betreiber (offene Frage SDT-01); der Eintrag allein ist
  kein Nachweis.
- Ist der Schalter aus, ruft weder eine Nutzeraktion noch ein Job den Schadenbearbeiter auf,
  und der Webhook antwortet 404.
- Token, HMAC-Geheimnis und Webhook-Geheimnis liegen verschlüsselt (Master-Key, Mandantenbereich)
  und werden nie ausgegeben (nur "gesetzt" und die letzten vier Zeichen des Tokens). Protokolle
  enthalten Methode, Pfad und Status, keine Tokens und keine Inhalte.
- Übergabe (`POST /tickets`): Ticket-ID als `externalTicketId`, Objektnummer als
  `objectExternalId`, Einheitennummer als `unitExternalId`, Titel, öffentliche Beschreibung,
  Meldender und Schadendaten (Datum, Art, Ort) nur aus dem Formular. Die interne Beschreibung
  wird nie gesendet. Versicherungs- und Policendaten werden nicht erfunden und in v1 nicht
  gesendet.
- Kommentare und Dokumente verlassen die Plattform nur, wenn ein Mitglied sie ausdrücklich
  sendet. Interne Notizen werden nicht automatisch übertragen.
- Jede schreibende Anfrage trägt einen stabilen `Idempotency-Key` (`mhvp-ticket-<id>`,
  `mhvp-comment-<id>`, `mhvp-attachment-<id>`, `mhvp-status-<zeile>`); eine Wiederholung
  sendet denselben Schlüssel. Wiederholungen folgen dem Webhook-Plan (1 min, 5 min, 30 min,
  2 h, 6 h, 24 h), `Retry-After` bei 429 wird eingehalten, andere 4xx sind endgültig. Ein 401
  setzt "Token ungültig" und hält die Warteschlange an, bis ein neuer Token hinterlegt ist.
- Webhook: HMAC-SHA256 über `${timestamp}.${rawBody}` mit Zeitfenster 5 Minuten, Dublette
  per `eventId` ohne Wirkung. Die Nutzlast gilt als Hinweis; der Inhalt wird beim
  Schadenbearbeiter abgerufen.
- Eingehende Kommentare werden interne Ticketkommentare mit dem Namen des Verfassers am
  Austauschdatensatz; eingehende Anhänge werden über `store_document` (Virenprüfung) im DMS
  abgelegt und mit dem Ticket verknüpft. Eigene Inhalte, die zurückkommen (`externalCommentId`,
  `externalAttachmentId` oder bekannte Fremd-ID), werden nicht erneut angelegt.
- Ein Status des Schadenbearbeiters wird roh gespeichert und angezeigt; er ändert den lokalen
  Status in v1 nie.
- Fremde Tickets ohne Zuordnung landen in der Übernahmeliste mit Vorschlägen (Objekt über
  Objektnummer, Ticket über `externalId`). Angelegt oder verknüpft wird nur nach Bestätigung je
  Ticket.

## Statusabbildung (Annahme A-072, bis zur Bestätigung der Statusliste, SDT-03)

| Lokaler Status | Wert an den Schadenbearbeiter | Anzeige eines empfangenen Werts |
| --- | --- | --- |
| `new` | `open` | Offen |
| `in_progress` | `in_progress` | In Bearbeitung |
| `waiting` | `waiting` | Wartet |
| `done` | `resolved` | Erledigt |
| `closed` | `closed` | Geschlossen |
| `rejected` | wird nicht gesendet | |
| unbekannter Wert | | unverändert angezeigt |

## Nicht in v1

Objekt-, Policen- und Schadenhistorien-Upserts (Vertrag Abschnitt 5), Priorität und
Zuständige, Löschungen, Übernahme des fremden Status in den lokalen Status.
