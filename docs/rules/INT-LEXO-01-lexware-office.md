# INT-LEXO-01 Lexware Office: Stammdaten nur nach Personenentscheidung in eine Richtung, Rechnungskopien nur an den bekannten Empfänger, Entwürfe ohne finalize

| Field | Content |
| --- | --- |
| ID | `INT-LEXO-01` |
| Title | Lexware Office: Stammdaten nur nach Personenentscheidung in eine Richtung, Rechnungskopien nur an den bekannten Empfänger, Entwürfe ohne finalize |
| Scope | Module `mhvp.integrations.lexoffice_ext`, `mhvp.integrations.lexoffice_async`; Tabellen `lexoffice_tenant_config` (je Gesellschaft), `lexoffice_invoice_kind_mapping`, `lexoffice_contact_link`, `lexoffice_outbox`, `lexoffice_invoice_draft`, `lexoffice_invoice_copy_request`, `lexoffice_recurring_prep`; Schalter je Konfiguration `enabled`, `sync_contacts`, `sync_names`, `invoice_copies`, `invoice_drafts` (Standard aus); G1 für `/export/*` und jedes `finalize=true` unberührt, kein Geldfluss |
| Source status | Produktschutz. Herstellerdokumentation developers.lexware.io, geprüft am 28.09.2026 und 29.09.2026 (Dauerrechnungen nur lesend); keine Norm aus dem Quellenregister. Die AVV Pflicht vor Aktivierung setzt Regel 0.1.13 um und ersetzt keine datenschutzrechtliche Prüfung. |
| Acceptance case | kein Anhang D Fall; Tests `apps/api/tests/integration/test_lexoffice_ext.py`, `apps/api/tests/unit/test_lexoffice_async_client.py`, `test_lexoffice_payloads.py`, `test_lexoffice_matching.py`, `test_lexoffice_ratelimit.py`, `test_mail_invoice_copy.py`, `apps/web-crm/src/components/settings/Lexoffice*.test.tsx`; Abnahmelauf gegen ein Testkonto `docs/acceptance/lexoffice.md` (noch nicht ausgeführt) |
| Implementation | Migration 0233, Fehlercodes `MHVP-LEXO-0006` bis `0017`, Celery `mhvp.integrations.lexoffice.process` (jede Minute), `.match_contacts`, `.purge` (täglich 03:20), Plan `docs/plans/M-lexoffice.md`, Betreiberdoku `docs/integrations/lexoffice.md`, ADR 0013 |
| Change reason | Betreiberauftrag vom 28.09.2026 (mehrere Organisationen je Gesellschaft, Zuordnung Rechnungsart zu Gesellschaft, Abgleich nach Name und E-Mail mit Prüfung, Rechnungskopien nur an bekannte Empfänger, Dauerrechnungen vorbereiten) |

## Regeln

- Aktivieren setzt voraus: AVV Datum und bestätigendes Mitglied (`MHVP-LEXO-0006`), API
  Schlüssel, erfolgreicher Verbindungstest mit dem aktuellen Schlüssel (`MHVP-LEXO-0014`),
  zulässige Basisadresse. Ein neuer Schlüssel setzt die Organisationsbindung zurück und
  deaktiviert bis zum nächsten Test. Eine andere Organisation bei bestehenden Verknüpfungen
  wird abgelehnt (`MHVP-LEXO-0013`).
- Je Gesellschaft eine Organisation mit eigenem Schlüssel; Rechnungsarten (Makler, Beratung,
  Hausverwaltung) werden je Mandant einer Gesellschaft zugeordnet, ohne Firmennamen im Code;
  eine nicht zugeordnete Rechnungsart wird abgelehnt (`MHVP-LEXO-0017`).
- Schalter je Funktion; der Worker prüft je Eintrag erneut (aktiv, AVV, Schalter der Art,
  Schlüssel gültig) und lässt den Eintrag sonst unverändert stehen (fail closed).
- Es wird nie übertragen: IBAN, BIC, Mandate, Steuernummern, Umsatzsteuer-IDs, Notizen,
  Rollen, Nummern, Kontaktpersonen, Lieferadressen, XRechnungsdaten, Archivierung. Ein Payload,
  der ein solches Feld gegenüber dem gelesenen Stand ändern würde, wird abgewiesen
  (`MHVP-LEXO-0007`).
- Eine Richtung: Adresse, E-Mail und Telefon gehen nach Lexware Office, nachdem eine Person
  die Änderung im CRM angewandt hat (PUT oder PATCH am Kontakt, angenommener Vorschlag).
  Importe, Massenaktionen, Automatisierung und Portal lösen keine Übertragung aus; solche
  Kontakte gelten als abweichend und werden ausdrücklich abgeglichen. Namen nur mit
  `sync_names`.
- Vor jedem Schreiben wird der Lexware Datensatz gelesen; die Version stammt aus dem GET, ein
  409 wird bis zu dreimal je Versuch neu gelesen. Weicht der Lexware Stand vom letzten
  bekannten Stand und vom CRM ab, wird nichts überschrieben: Konflikt zur Entscheidung
  (`keep_crm` sendet erzwungen, `keep_lexoffice` übernimmt den Stand als Basis, das CRM wird
  nie verändert).
- Mehrfach belegte Listen, Wechsel zwischen Person und Firma, archivierte oder fehlende
  Kontakte führen zu `manual_required` oder `remote_missing` mit Deeplink; die Plattform legt
  nichts neu an. Ein gelöschter CRM Kontakt löst keinen Aufruf aus (`unlinked_local`).
- Neue Lexware Kontakte entstehen nur durch die ausdrückliche Entscheidung `create_remote` mit
  gewählter Rolle; neue CRM Kontakte aus Lexware nur durch `create_local` je Zeile.
- Rechnungskopien: der Anfragende ist nur bestätigt, wenn der von einer Person zugeordnete
  Kontakt der Mail oder des Tickets der über die Verknüpfung bekannte Rechnungsempfänger ist;
  die Absenderadresse ist nur ein Hinweis (`MHVP-LEXO-0009`). Der Entwurf geht nur an die
  bekannte primäre E-Mail des Empfängers, aus dem Postfach der rechnungsstellenden
  Gesellschaft, mit gesperrtem Empfänger (`MHVP-LEXO-0015`) und Freigabe durch eine zweite
  Person (`author_approval_required`). Entwürfe in Lexware Office werden nicht abgerufen.
- Rechnungsentwürfe: `POST /v1/invoices` ohne `finalize`, nur dokumentierte Felder, Summen
  lokal nur zur Kontrolle. Dauerrechnungen werden vorbereitet, nicht angelegt (API nur lesend).
- Redaktion: Fehlertexte bestehen aus Statuscode, Feld, Verstoß, traceId und eigenem Text;
  `args`, `additionalData`, `message`, Anfragen und E-Mail Adressen werden nie übernommen.
- Auditereignisse `lexoffice.*`: `config_changed`, `key_rotated`, `test_ok`, `test_failed`,
  `token_invalid`, `organization_mismatch`, `link_decided`, `push_sent` (nur Feldnamen),
  `push_failed`, `conflict_resolved`, `invoice_lookup`, `invoice_file_fetched`,
  `invoice_draft_created` (Art. 15 und 30 DSGVO Grundlage).
- Aufbewahrung der Warteschlange 90 Tage (LEXO-12), Anfragelimit zwei je Sekunde je
  Organisation, kein serverseitiger Idempotenzschlüssel bei Lexware (Existenzprüfung nach 504).
- Endpunkte außerhalb der verifizierten Liste in `docs/integrations/lexoffice.md` werden nicht
  aufgerufen; `updatedAtFrom` existiert nicht.
