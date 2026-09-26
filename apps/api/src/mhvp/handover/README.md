# handover

Übergabeprotokolle (M30) im Bereich Makler: digitale Wohnungsübergabe für Vermietung,
Verkauf und allgemeine Übergaben. Plan: `docs/plans/M30-uebergabeprotokoll.md`, Regel:
`docs/rules/M30-01.md`.

| Datei | Inhalt |
| --- | --- |
| `models.py` | `handover_protocol` mit Adress- und Einheitensnapshot, Kaution, interne Felder, Abschluss und PDF-Verweis; Teildatensätze `handover_participant` (optional Kontakt), `handover_meter` (optional Zähler der Stammdaten), `handover_room`, `handover_defect`, `handover_key`, `handover_item`, `handover_note`; `handover_signature` (PNG-Dokument, SHA-256, Zeitpunkt) |
| `services.py` | Nummernvergabe `UP-JJJJMMTT-NNN`, Vorbelegung aus Einheit und Objekt, Laden aller Teildaten samt Dokumenten, Hinweise vor dem Abschluss, neue Version mit Dateireferenzen statt Kopien, PDF-Ablage als Dokument |
| `pdf.py` | PDF mit reportlab auf dem Briefbogen des Mandanten (Firmendaten und Farbband aus `tenant_settings`), alle Abschnitte auch wenn leer, Fotos je Teildatensatz, Unterschriften mit Hash, Entwurfs- und Stornovermerk |
| `routers.py` | `/api/v1/handover/protocols`: Liste, Vorbelegung, Anlage, Feldänderung, Teildatensätze je Abschnitt (`/{section}`, `/{section}/{item_id}`, `/{section}/order`), Fotos und Anhänge (`/documents`), Unterschriften (`/signatures`), Hinweise, Abschluss, PDF, Versionen, Status, Zustellung, Portalzugang je Beteiligtem (`/participants/{id}/portal-access`) |
| `portal.py` | `/api/v1/portal/handover`: Sicht des Beteiligten mit Portalkonto und Recht `handover` (Stufe 3). Liste, Lesen ohne interne Felder, Felder ändern, Teildatensätze, Fotos, Unterschriften, Hinweise, Abschluss (danach Recht `read` für `READ_DAYS`), PDF; Schreiboperationen delegieren an `routers.py` |

Rechte: `contracts:read` lesen, `contracts:create` anlegen und neue Version,
`contracts:update` bearbeiten und abschließen, `contracts:delete` für die Stornierung
abgeschlossener Protokolle. Dateien liegen als Dokumente (M6) mit Verknüpfung
`handover_protocol` und je Teildatensatz `handover_meter`, `handover_room`,
`handover_defect`, `handover_item` (`documents.services.LINKABLE`).

Nicht enthalten (offen): Zustellung des Einladungscodes für den Portalzugang (M30-01 in
`docs/OPEN_QUESTIONS.md`), Datenübernahme aus U-Protokoll (M30-03), Entfernen von
Bildmetadaten (M30-04), zweiter Faktor für Gehilfen (M30-05).

## Mitarbeiterportal und Import-Fortschreibung (26.09.2026)

- `portal_staff.py`: `GET /api/v1/portal/handover-protocols`, `/{id}`, `/{id}/pdf` für
  Mitgliedschaften mit dem Portalrecht `handover:read` (`mhvp.portal.staff_access`), nur lesend,
  gleicher Feldfilter wie für Beteiligte; externe Portalnutzer erhalten 403.
- `uprotokoll_import.py`: zweiter Durchlauf verknüpft Protokollversionen mit dem Vorgänger
  (`parent_protocol_id` -> `parent_id`) und übernimmt `protocol_emails` als interne Hinweise
  (Zeitpunkt, Empfänger, Betreff, Status, kein Mailtext), beides idempotent.
