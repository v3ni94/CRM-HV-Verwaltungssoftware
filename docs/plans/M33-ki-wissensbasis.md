# M33 KI-Wissensbasis je Mandant und Objekt, Mail-Vorbereitung (Welle 3 Punkt 14)

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
- Backend-Tests: `apps/api/tests/integration/test_m33_ai_knowledge.py` (Wissensbasis CRUD,
  Mandantentrennung, Berechtigungen; Mail-Vorbereitung mit gefaktem KI-Anbieter, ohne
  DMS-Verbindung, daher ohne Netzwerkzugriff; Korrektur legt einen gelernten Wissenseintrag an).
  `ruff check` und `mypy --strict` sauber für die geänderten Module.
- Alles hier ist ein Vorschlag (Regel 0.1.6): kein automatischer Versand, keine automatische
  Buchung; jede Annahme oder Korrektur bleibt eine Handlung einer Person.

## Offene Punkte

Siehe `docs/OPEN_QUESTIONS.md` (M33-01 Freigabeworkflow für Wissenseinträge, M33-02
Google-Drive-Suche noch nicht gegen einen echten Drive-Account verifiziert, M33-03 Umgang mit
mehrdeutigen Rollen bei mehreren aktiven Verträgen derselben Partei).
