# M9-02 Regel-Engine: Ereignis- und Zeitplanregeln, Aktionen ohne Geldwirkung, Tiefe 1, Testlauf ohne Wirkung

| Field | Content |
| --- | --- |
| ID | `M9-02` |
| Title | Regel-Engine Stufe 1 (Auslöser Ereignistyp, Bedingungen als JSON-Logik, Aktionen Ticket aus Vorlage, interne Benachrichtigung, Ticketfeld setzen) und Stufe 2 (Auslöser Zeitplan, Aktionen Webhook, E-Mail-Entwurf, Brief-Entwurf, KI-Aufgabe), Ausführungsprotokoll, Testlauf |
| Scope | Domäne `automation`, Tabellen `automation_rule`, `automation_run`, `automation_watermark`; alle Mandanten; Ereignisse aus `domain_event` und Zeitplanfenster; Aktionen auf `ticket`, `notification`, `message` (nur Entwurf), `document` (Brief), `ai_task_run` (nur Vorschlag) und ausgehende signierte Webhooks |
| Source status | Keine Rechtsnorm im Quellenregister (annex C) einschlägig; Produktschutz nach Regel 0.1.6 und 0.1.7 (keine Buchung, Zahlung, Freigabe oder Versand durch Regeln, keine autonomen Wirkungen mit Geldbezug; Webhook-Zielprüfung nach Abschnitt 12) |
| Acceptance case | keine in annex D; Tests `apps/api/tests/unit/test_automation_rules.py`, `apps/api/tests/unit/test_automation_schedule.py`, `apps/api/tests/unit/test_automation_letter_draft.py`, `apps/api/tests/integration/test_m9_automation.py`, `apps/api/tests/integration/test_m9_automation_stage2.py`, `apps/api/tests/integration/test_m9_automation_related.py`, `apps/web-crm/src/components/settings/AutomationAdmin.test.tsx` |
| Implementation | `mhvp.automation` (`models`, `rules`, `schedule`, `schemas`, `services`, `tasks`, `routers`), Migrationen 0100 und 0110, Beat `automation-process-events` in `mhvp/worker.py`, CRM `einstellungen/automatisierung` |
| Change reason | Aufgabe A38 der Lückenliste vom 26.09.2026 (Paket `mhvp.automation` war laut README nicht umgesetzt; Voraussetzung für die Ablösung von Müller FLOW, 13.4); Stufe 2 nach Aufgabe A39 (Webhook, Entwürfe, KI-Aufgabe, Zeitplan, Regelformular) am 26.09.2026; A81 (Bedingungen auf verknüpfte Stammdaten) und A83 (Kennzeichnung automatisch erzeugter Briefe) am 26.09.2026 |

## Regeln

- Eine Regel (`automation_rule`, mandantengebunden, Name je Mandant eindeutig) hat einen
  Auslöser (Ereignistyp wie `ticket.created`), einen Bedingungsbaum und eine geordnete Liste
  von Aktionen. Neue Regeln sind inaktiv (`active = false`); nur aktive Regeln laufen.
- Bedingungen sind ein Baum aus Gruppen (`and`, `or`) und Blättern (`field`, `op`, `value`)
  mit den Operatoren gleich, ungleich, enthält, größer, kleiner über die Felder des
  Ereignisses (`type`, `entity_type`, `entity_id`, `payload.*`), die aktuellen Felder des
  betroffenen Tickets (`entity.*`) und, seit A81, die verknüpften Stammdaten (siehe
  "Bedingungen auf verknüpfte Stammdaten"). Höchstens 5 Ebenen und 50 Blätter; ein leerer Baum trifft
  auf jedes Ereignis des Auslösers zu. Vergleiche sind deterministisch (Zahlen als Zahlen,
  UUIDs und Aufzählungen als Text, `contains` ohne Groß- und Kleinschreibung).
- Aktionen der Stufe 1: `create_ticket` (Vorlage, Titel mit Platzhaltern, Felder als
  Festwert oder Verweis auf ein Ereignisfeld), `notify` (Benutzer und/oder Rollen, Titel,
  Text), `set_ticket_field` (nur `priority`, `team_id`, `category`, `assignee_user_id`).
  Jede andere Aktion und jedes andere Feld wird mit 422 abgelehnt. Regeln buchen nicht,
  zahlen nicht, geben nichts frei, versenden keine E-Mail und ändern keinen Ticketstatus
  (Regel 0.1.6, 0.1.7).
- Aktionen der Stufe 2 (A39), Katalog abschließend:
  - `webhook`: signierter Aufruf (`X-MHVP-Signature`, HMAC SHA-256 wie in
    `mhvp.core.webhooks`) an eine Ziel-URL je Regel mit Regel, Ereignis, Ticketfeldern und
    optionalen Zusatzfeldern. Das Geheimnis (mindestens 16 Zeichen) wird beim Speichern mit
    dem Mandantenschlüssel verschlüsselt abgelegt (`secret_enc`) und von der API nie
    zurückgegeben (`has_secret`); ein Wechsel der URL ohne neues Geheimnis wird abgelehnt.
    Ziele nur `https`; private oder nicht auflösbare Ziele nur mit der Einstellung
    `webhook_allow_private_targets` (in Staging und Produktion erzwungen aus). Ein
    Aufruf je Lauf, Zeitlimit 10 Sekunden, keine Wiederholung; ein Fehlschlag wird als
    fehlgeschlagener Lauf protokolliert.
  - `mail_draft`: E-Mail-Entwurf aus einer Antwortvorlage der Tickets (M20) im Postfach des
    Tickets (`message.status = draft`, Empfänger aus letzter eingehender Mail oder
    Hauptadresse des Kontakts). Kein Versand, keine Einreichung; Freigabe und Versand bleiben
    manuell im Vier-Augen-Prinzip. Nur für Ereignisse zu einem Ticket.
  - `letter_draft`: Brief aus einer Briefvorlage (M6/M23) auf dem Briefbogen des Mandanten,
    als erzeugtes Dokument abgelegt und mit Kontakt, Objekt, Einheit und Ticket verknüpft.
    Empfänger ist der feste Kontakt der Aktion oder der Kontakt des Tickets; fehlende
    Firmendaten, Anschrift oder Platzhalter lassen die Aktion fehlschlagen. Kein Versand.
    Kennzeichnung (A83, M9-10): das Dokument wird in der Kategorie "Entwurf" (Code
    `entwurf`, je Mandant beim ersten Lauf angelegt) abgelegt, nicht in der Kategorie der
    Vorlage; das PDF trägt auf jeder Seite die Kopfzeile "ENTWURF, automatisch erzeugt am
    TT.MM.JJJJ durch Regel <Name>, nicht versendet" und ein helles diagonales Wasserzeichen
    "ENTWURF" (`Letter.draft_notice` in `mhvp.documents.letters`, für alle anderen Aufrufer
    standardmäßig aus). Die Metadaten des Dokuments (`source_meta`) enthalten `is_draft`,
    `automation_rule_id`, `automation_rule_name`, `automation_event_id`, `generated_at`,
    `template_code`, `template_category_id` und den Hinweistext, damit Dokumentliste und
    Ticket den Entwurf filtern können. Der Hinweis steht im Textlayer und ist über die
    Volltextsuche auffindbar. Versand bleibt ein manueller Schritt mit Sichtprüfung (M23).
  - `ai_task`: legt einen KI-Lauf über den unveränderten Gateway-Weg an (`summarize`,
    `draft_reply`, `answer_question`, `classify_email`; keine Kontierung, keine
    Belegextraktion, keine Stammdatenänderung). Ergebnis ist nur ein Vorschlag; keine
    Entscheidung, keine Freigabe. Ohne Worker (`ai_inline`) bleibt der Lauf in der
    Warteschlange.
- Auslöser Zeitplan (`trigger_kind = schedule`): täglich, wöchentlich (Wochentag) oder
  monatlich (Tag 1 bis 28) zu einer Uhrzeit in Europe/Berlin. Der Beat-Job führt eine fällige
  Regel genau einmal je Termin aus: Wasserstand `last_scheduled_at` je Regel plus
  deterministische Lauf-ID aus Regel und Termin (`uq_automation_run_event`). Der erste Lauf
  nach Aktivierung setzt nur den Wasserstand (Termine davor sind Historie), eine Änderung des
  Zeitplans setzt ihn zurück. Aktionen, die ein Ticket brauchen (`set_ticket_field`,
  `mail_draft`), sind auf einem Zeitplan nicht erlaubt; `letter_draft` braucht dort einen
  festen Empfänger. Der Kontext eines Zeitplanlaufs ist `schedule.due` mit `payload.due_at`.
- Ausführung asynchron durch den Beat-Job `mhvp.automation.process_events` (jede Minute) über
  einen Wasserstand je Mandant in `domain_event`; das Ereignissystem selbst bleibt
  unverändert. Der erste Lauf eines Mandanten setzt nur den Wasserstand; ältere Ereignisse
  sind Historie und lösen nichts aus.
- Idempotenz: je Regel und Ereignis höchstens ein Lauf (`automation_run`, eindeutig über
  Mandant, Regel, Ereignis). Jeder Lauf protokolliert Zeitpunkt, Ergebnis (`executed`,
  `failed`), Fehlertext und die ausgeführten Aktionen mit betroffener Entität. Eine
  fehlgeschlagene Regel wird zurückgerollt (Savepoint) und protokolliert; die übrigen Regeln
  und der Wasserstand laufen weiter.
- Schleifenschutz mit Tiefe 1: Ereignisse, die eine Regelaktion schreibt (`ticket.created`,
  `ticket.field_set`), tragen die Markierung `payload.automation` und werden vom Job
  übersprungen. Regelaktionen lösen damit keine weitere Regel aus.
- Testlauf (`POST /automation/rules/{id}/test`): bewertet die Regel gegen ein
  Beispielereignis (frei eingegebene Ticketfelder oder ein bestehendes Ticket) und liefert
  die Vorschau der Aktionen; es wird nichts angelegt, gesetzt, benachrichtigt oder
  protokolliert.
- Rechte: Pflege, Aktivieren und Testlauf mit `tenant_settings:update`; Löschen mit
  `tenant_settings:delete` (nur Administrator, `M2-07`); Regeln und Protokoll lesen mit
  `tenant_settings:read` oder `tickets:read`. Mandantentrennung durch RLS auf allen drei
  Tabellen; Regeln eines Mandanten sehen nur dessen Ereignisse, Vorlagen und Kontakte
  (Vorlagen anderer Mandanten sind für die Aktion nicht auffindbar).
- Regelformular im CRM: strukturierte Erfassung mit Auswahlfeldern (Auslöserart, Ereignistyp,
  Zeitplan, Bedingungsfelder, Priorität, Team, Vorlagen, KI-Aufgabe) und Regelsatz als
  Vorschau ("Wenn Ticket angelegt mit Ticket Kategorie gleich Wasserschaden, dann Priorität
  Hoch, Team Objektbetreuung."). Verschachtelte Bedingungen nur in der Expertenansicht (JSON).

## Bedingungen auf verknüpfte Stammdaten (A81)

- Feldpfade `property.*`, `unit.*`, `contact.*` und `contract.*` lesen die Stammdaten, die
  über das Ticket (`property_id`, `unit_id`, `contact_id` oder `initiator_contact_id`), das
  Ereignis (`payload.property_id` usw.) oder die Entität selbst (Ereignisse zu Objekt,
  Einheit, Kontakt) verknüpft sind. Der Katalog ist abschließend (`RELATED_FIELDS` in
  `mhvp.automation.rules`, Gruppen und Felder über `GET /automation/meta` als
  `related_fields`): Objekt `number`, `name`, `management_type`, `management_mode`, `status`,
  `city`, `postal_code`, `manager_user_id`; Einheit `number`, `unit_type`, `floor`, `label`,
  `city`, `is_fictional`; Kontakt `kind`, `roles`, `tags` (Namen der Schlagworte),
  `blocked`, `language`, `preferred_channel`, `display_name`; Vertrag `kind`, `status`,
  `number`, `start_date`, `end_date`, `termination_date`, `sev_enabled`. Keine Geldwerte,
  Salden, Bankdaten oder Mietbeträge; ein unbekanntes Feld einer Gruppe wird beim Speichern
  mit 422 abgelehnt.
- Auflösung beim Auswerten: je Ereignis wird der Kontext einmal gebildet und nur um die
  Gruppen ergänzt, die die Regeln des Ereignistyps tatsächlich verwenden (eine Abfrage je
  Gruppe, Schlagworte und Vertragsparteien gebündelt). Fehlt die Verknüpfung, ist die Gruppe
  leer und jedes Feld `null`; `eq` trifft dann nicht, `ne` trifft.
- Vertrag: Verträge werden über die Einheit des Tickets gelesen. Bei mehreren Verträgen
  gilt deterministisch der Vertrag, dessen Partei den Kontakt des Tickets enthält, sonst der
  laufende vor dem beendeten, Mietvertrag vor Eigentum, jüngster Beginn zuerst, danach die
  ID. `contract.status` ist kein gespeichertes Feld, sondern wird aus den Vertragsdaten zum
  Auswertungstag (Europe/Berlin) abgeleitet: `future` (Beginn in der Zukunft), `ended`
  (Ende vor heute), `terminated` (Kündigungsdatum gesetzt, noch nicht beendet), sonst
  `active`.
- Mandantentrennung: die Abfragen laufen in der Mandantensitzung (RLS) und zusätzlich mit
  explizitem Mandantenfilter; die Objekt-ID eines fremden Mandanten liefert eine leere
  Gruppe (Test `tests/integration/test_m9_automation_related.py`).
- Testlauf: die Beispieldaten dürfen `property_id`, `unit_id` und `contact_id` enthalten;
  die verknüpften Daten werden wie im Echtlauf geladen und im Kontext zurückgegeben.
- Regelformular: Feldauswahl gruppiert nach Ticket, Ereignis, Objekt, Einheit, Kontakt und
  Vertrag; Auswahlfelder mit festen Werten für Verwaltungsart, Objektstatus, Kontaktrolle,
  Vertragsart und Vertragsstatus; freier Feldpfad weiterhin über "Anderes Feld".

## Offen

- Bedingungen auf verknüpfte Stammdaten sind auf den Katalog oben beschränkt; weitere
  Felder (zum Beispiel Gebäude, Schlüssel, Zähler) nur nach Erweiterung des Katalogs.
- Die Dokumentliste zeigt den Entwurfsstatus über die Kategorie "Entwurf"; ein eigener
  Listenfilter `is_draft` in der Dokumenten-API (aus `source_meta`) ist noch nicht
  umgesetzt (Dokumentdomäne, nicht Regel-Engine).
- Regel-Webhooks kennen keine Wiederholung (anders als Abonnements nach Abschnitt 12); ob
  ein Wiederholungsplan gewünscht ist, entscheidet der Betreiber (`docs/OPEN_QUESTIONS.md`
  M9-08).
- Ein Ereignis `ticket.updated` existiert im Ticketrouter nicht; Regeln auf Feldänderungen
  eines Tickets sind daher erst mit einem solchen Ereignis möglich (Erweiterung der
  Ticketdomäne, nicht der Regel-Engine).
