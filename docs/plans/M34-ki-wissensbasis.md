# M34 KI-Wissensbasis je Mandant und Objekt, Mail-Vorbereitung (Welle 3 Punkt 14)

Stand 25.09.2026. Betreiberauftrag: eine Wissensbasis je Mandant und optional je Objekt (Ablageregeln,
Arbeitsabläufe, Korrekturen, Fakten), die als Kontext in KI-Läufe einfließt, plus eine sofortige
Vorbereitung eingehender Mails (Absender, Rolle, Einheit, passende Dokumente, Antwortentwurf).

## Umfang

1. Migration `0051_ai_knowledge_entry` (Tabelle `ai_knowledge_entry`, RLS je Mandant, optional
   `property_id`, `kind` filing_rule/workflow/correction/fact, `source` manual/learned).
2. API `/api/v1/ai/knowledge` (Liste mit Filter `property_id`/`kind`, Anlegen, Ändern, weiches
   Löschen). Rechte wie bestehende KI-Endpunkte (`ai:read`, `ai:create`, `ai:delete`).
3. Mail-Vorbereitung (`mhvp.communication.preparation`):
   - `resolve_contact`: löst den Absender über den bereits beim Mailempfang zugeordneten Kontakt
     (`Message.contact_id`) auf eine Vertragspartei, einen aktiven Vertrag, eine Einheit und eine
     Rolle (Eigentümer/Mieter) auf (`PartyMember`, `Contract`).
   - Dokumentsuche strikt je Objekt, lokal (`DocumentLink`) und extern (Paperless-Custom-Field,
     Google-Drive-Objektordner), siehe `docs/rules/M20-05.md`.
   - KI-Lauf über `mhvp.ai.gateway` (bestehende Freigabe-, Budget- und Tier-Logik) mit den
     Wissenseinträgen des Mandanten und des Objekts als Kontext; Antwortentwurf über das bestehende
     Schema `MailSuggestion` (`AiTask.CLASSIFY_EMAIL`, Feld `reply_draft`).
   - Ergebnis wird unter `Message.suggestion["preparation"]` gespeichert (bestehender Mechanismus
     aus M20, keine neue Spalte): Kontakt, Einheit, Objekt, Rolle, Dokumente, Entwurf, Konfidenz,
     Begründungen.
   - Endpunkte `POST/GET /mail/messages/{id}/preparation` und
     `POST /mail/messages/{id}/preparation/correct` (Korrektur legt einen gelernten
     Wissenseintrag `kind=correction` an).
   - Celery-Task `mhvp.communication.prepare_mail` für den asynchronen Betrieb (`ai_inline=false`).
4. CRM-Oberfläche: Abschnitt „Wissensbasis" unter Einstellungen, KI (Liste, Anlegen, Ändern,
   Löschen, Filter nach Objekt); Panel „Vorbereitung" in der Mail-Detailansicht mit den Aktionen
   „Übernehmen" (öffnet den Entwurf im bestehenden Antwortfluss) und „Korrigieren".

## Ergebnis

- Migration angewendet (`alembic upgrade head`), kein Autogenerate-Diff
  (`test_no_autogenerate_drift`), kein Namenskonflikt im OpenAPI-Dokument
  (`test_no_new_schema_name_collisions`).
- Backend-Tests: `apps/api/tests/integration/test_m34_ai_knowledge.py` (Wissensbasis CRUD,
  Mandantentrennung, Berechtigungen; Mail-Vorbereitung mit gefaktem KI-Anbieter, ohne
  DMS-Verbindung, daher ohne Netzwerkzugriff; Korrektur legt einen gelernten Wissenseintrag an).
  `ruff check` und `mypy --strict` sauber für die geänderten Module.
- Alles hier ist ein Vorschlag (Regel 0.1.6): kein automatischer Versand, keine automatische
  Buchung; jede Annahme oder Korrektur bleibt eine Handlung einer Person.

## Offene Punkte

Siehe `docs/OPEN_QUESTIONS.md` (M34-01 Freigabeworkflow für Wissenseinträge, M34-02
Google-Drive-Suche noch nicht gegen einen echten Drive-Account verifiziert, M34-03 Umgang mit
mehrdeutigen Rollen bei mehreren aktiven Verträgen derselben Partei).

## Stand 26.09.2026

Zusammenfassung aus den Nachträgen dieses Plans, dem `CHANGELOG.md` (1.19.0 bis 1.22.1) und der Lückenliste `docs/plans/LUECKENLISTE-2026-09-26.md`; keine neuen Sachverhalte.

* Im Code: `ai_knowledge_entry` (Migration 0051), API `/api/v1/ai/knowledge`, Mail-Vorbereitung `mhvp.communication.preparation` mit Dokumentsuche strikt je Objekt (Regel M20-05), Korrektur als gelernter Eintrag, CRM-Abschnitt Wissensbasis und Panel Vorbereitung.
* Tests: `test_m34_ai_knowledge.py`.
* Offen: M34-01 bis M34-03 wie oben.

## Nachtrag 26.09.2026 (1.25.0): Seite Wissen

* Übernommen aus der Parallelsitzung (1.24.0): Seite `/einstellungen/wissen` mit gelernten Playbooks (Trefferzahl, letzte Nutzung aus `playbook.last_used_at`, Deaktivieren mit `communication:update`) und Lernbeispielen (`GET /ai/examples`, Filter nach Aufgabe, `tenant_settings:read`). Die Wissenseinträge (`ai_knowledge_entry`) bleiben unverändert; die Seite zeigt gelernte Artefakte, keine Freigabe. Handbuch `docs/handbuch/einstellungen.md`, Abschnitt Wissen; Datenschutz der Lernbeispiele in ADR 0010 und M7-04.

## Nachtrag 29.09.2026: Audit Wissensdatenbank und Playbooks

Betreiberfrage: "Playbooks und Wissensdatenbank wirklich effizient und effektiv?" Befund mit
Belegen im Ergebnisbericht der Sitzung; hier der umgesetzte Umfang.

Befund (Auszug, Stand vor dem Nachtrag):

* Der Assistent (`answer_question`) hat die Wissensbasis nicht genutzt: `gateway.build_input`
  holte nur Dokumente (`retrieve`), die freigegebenen Einträge flossen ausschließlich in die
  Mail-Vorbereitung (`communication.preparation._knowledge_context`) ein.
* Kein Zeichenlimit für den Wissenskontext (30 Einträge beliebiger Länge), keine Dedupe je
  `group_id`; zusammen mit `MAX_INPUT_CHARS` 1.500.000 (rund 375.000 Token) ein Baustein des
  Produktionsfehlers 29.09.2026 "Input tokens exceed the configured limit of 272000" (die
  Token-Budgetierung selbst wird in einer parallelen Sitzung in `gateway.py` korrigiert).
* Playbook-Zuordnung nur über Schlagwortüberlappung, ohne Bezug zur Kategorie der Mail;
  Playbooks wurden je Vorschlag zweimal geladen.
* Keine Rückmeldung, ob eine Antwort oder ein Playbook geholfen hat; Wissenseinträge ohne
  Nutzungszähler; kein Hinweis auf lange nicht geprüfte Einträge.

Umsetzung:

1. `mhvp.ai.knowledge` (neu): gemeinsame Auswahl der Einträge für Mail-Vorbereitung und Chat
   (nur `approved`, gültig, ein Eintrag je Gruppe, Ähnlichkeitsranking wenn Einbettungen
   vorhanden, Obergrenzen 30 Einträge, 20.000 Zeichen, 2.000 Zeichen je Eintrag mit sichtbarer
   Kürzung). Nutzung je Eintrag (`usage_count`, `last_used_at`), verwendete Ids am Lauf
   (`input_ref["knowledge_ids"]`, `RunOut.knowledge_ids`).
2. Chat: freigegebene Wissensbasis steht vor den Dokumenten im Datenblock ("Vorrang vor
   Dokumenttext"); Objektbezug aus dem Kontext (`entity_type = property`).
3. Rückmeldung "hilfreich / nicht hilfreich": `POST /ai/runs/{id}/feedback` (nur Urheber des
   Laufs; zweite Abgabe ersetzt die erste, Zähler der verwendeten Einträge folgen),
   `POST /ai/knowledge/{id}/feedback`, `POST /mail/playbooks/{id}/feedback`. Zähler ohne
   Folgen: Freigabeworkflow und Status unverändert. Ereignisse `ai_run.feedback`,
   `ai_knowledge.feedback`, `playbook.feedback`.
4. Hinweis "Lange nicht geprüft" (`KnowledgeEntryOut.stale`): freigegeben und seit mehr als 180
   Tagen unverändert (`knowledge.STALE_AFTER_DAYS`, Produktschutz, keine Rechtsbedeutung).
5. Playbooks: `rank_playbooks` mit Kategorie-Bonus 0,2 für die deterministische Mailkategorie
   (`mail.category`); ohne Schlagworttreffer kein Vorschlag, auch nicht über die Kategorie.
   Einmaliges Laden der Playbooks je Vorschlag.
6. Migration `0237_knowledge_usage_feedback` (Zähler, `ai_task_run.feedback`, Teilindex
   `ix_ai_knowledge_entry_live_approved`).
7. CRM: Zähler und Hinweis in Einstellungen, KI, Wissensbasis; Spalte Rückmeldung in
   Einstellungen, Wissen (Playbooks); Schaltflächen im Chat (Antwort) und in der Mail
   (KI-Vorschlag, Playbook).

Bewusst nicht geändert: `MAX_COSINE_DISTANCE` 0,8 (ohne Auswertung mit echten Daten kein
belastbarer neuer Wert, A-051 bleibt); Token-Budget in `gateway.py` (parallele Sitzung);
Antwortpanel im Ticket (bleibt bei deterministischen Antwortvorlagen, Playbooks dort nur als
Empfehlung); Dublettenprüfung der Wissenseinträge; Verzicht auf einen zweiten Einbettungsaufruf
je Chatfrage (Dokumente und Wissensbasis betten die Frage getrennt ein, siehe Empfehlungen).

Tests: `tests/unit/test_ai_knowledge.py`, `tests/integration/test_kb_audit_feedback.py`,
`apps/web-crm/src/components/ai/AssistantMessage.test.tsx`, `KnowledgeSettings.test.tsx`,
BFF-Allowlist (`route.test.ts`, Abdeckungstest).
