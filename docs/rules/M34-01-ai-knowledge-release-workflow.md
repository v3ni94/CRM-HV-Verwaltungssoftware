# M34-01 Freigabeworkflow und Versionierung für Wissenseinträge

| Field | Content |
| --- | --- |
| ID | `M34-01` |
| Title | Freigabeworkflow (Entwurf, zur Prüfung, freigegeben, zurückgezogen), Versionierung und Vier-Augen-Freigabe für `ai_knowledge_entry` |
| Scope | Domäne `mhvp.ai`, Tabelle `ai_knowledge_entry`; Mandanten mit Recht `ai:read`/`ai:create`/`ai:approve`/`ai:delete` |
| Source status | Keine Rechtsnorm im Quellenregister (annex C) einschlägig; Produktschutz (rule 0.1.6: KI liefert nur Vorschläge, keine autonome KI-Buchung oder ungeprüfte Wissensquelle; Vier-Augen als interner Qualitätsstandard) |
| Acceptance case | keine in annex D; Tests `apps/api/tests/integration/test_m34_ai_knowledge.py` |
| Implementation | `mhvp.ai.models.AiKnowledgeEntry` (`status`, `group_id`, `version`, `superseded_at`, `valid_from`/`valid_until`, `source_document_id`, `submitted_by/at`, `approved_by/at`, `withdrawn_by/at`), `mhvp.ai.routers` (`/ai/knowledge/{id}/submit`, `/approve`, `/withdraw`, `/versions`), `mhvp.communication.preparation._knowledge_context`, Migration 0178 |
| Change reason | Betreiberauftrag, offener Punkt M34-01 aus `docs/plans/M34-ki-wissensbasis.md` |

## Regeln

- Ein Wissenseintrag hat den Status `draft` (Entwurf), `in_review` (zur Prüfung),
  `approved` (freigegeben) oder `withdrawn` (zurückgezogen). Übergänge: `draft` ->
  `in_review` (`POST /ai/knowledge/{id}/submit`, Recht `ai:create`), `in_review` ->
  `approved` (`POST /ai/knowledge/{id}/approve`, Recht `ai:approve`), jeder Status ->
  `withdrawn` (`POST /ai/knowledge/{id}/withdraw`, Recht `ai:approve`).
- Vier-Augen-Prinzip: die freigebende Person (`approved_by`) darf nicht die Verfasserin der
  geprüften Version (`created_by`) sein; sonst 403 (`FORBIDDEN`). Es gibt keine
  Ausnahmeregel für Administratoren; eine zweite Person muss die Freigabe erteilen.
- Versionierung: eine Änderung an einem Eintrag, der bereits `in_review`, `approved` oder
  `withdrawn` ist, legt eine neue Zeile derselben Gruppe (`group_id`, `version` + 1) an; die
  vorige Version erhält `superseded_at` und bleibt unverändert lesbar (Versionsverlauf
  `GET /ai/knowledge/{id}/versions`). Die neue Version startet wieder als `draft` und
  durchläuft den Freigabeworkflow erneut. Ein Eintrag, der noch nicht über den eigenen
  Entwurf hinausgekommen ist (`status=draft`), wird dagegen in der bestehenden Zeile
  geändert (keine Versionshistorie ohne Freigabewert).
- Gültigkeitszeitraum (`valid_from`/`valid_until`, optional) und Quelle/Beleg
  (`source_document_id`, optionaler Link auf ein Dokument) werden je Version gepflegt.
- Geltungsbereich: Mandant (RLS, unverändert), Objekt (`property_id`, optional) und
  Kategorie (`kind`: `filing_rule`/`workflow`/`correction`/`fact`), wie vor M34-01.
- Nur in KI-Läufe fließen Einträge mit `status=approved`, `superseded_at IS NULL`,
  `deleted_at IS NULL` und, falls gesetzt, innerhalb `valid_from`/`valid_until` zum
  Zeitpunkt des Laufs (`mhvp.communication.preparation._knowledge_context`). Ein Entwurf,
  ein Eintrag zur Prüfung oder ein zurückgezogener Eintrag wird nie als Kontext verwendet.
- Die verwendeten Einträge (ID, `group_id`, Version, Titel) werden im Ergebnis der
  Mail-Vorbereitung unter `preparation.knowledge_used` als Nachweis mitgegeben (Rule
  0.1.7/0.1.8: nachvollziehbare Grundlage der KI-Antwort).
- Ein gelernter Eintrag aus einer Korrektur (`source=learned`) startet ebenfalls als
  `draft` und braucht dieselbe Freigabe, bevor er in künftige KI-Läufe einfließt; eine
  Korrektur ist keine automatische Freigabe (rule 0.1.6).
- Löschen (`DELETE /ai/knowledge/{id}`, Recht `ai:delete`) bleibt ein weiches Löschen
  (`deleted_at`) unabhängig vom Status und wirkt nur auf die angegebene Version.

## Offen

- Ob eine `in_review`-Version bei Ablehnung explizit auf `draft` zurückgesetzt werden kann
  (Reject-Aktion), ist nicht Teil dieses Umfangs; aktuell bleibt nur `withdraw`. Siehe
  `docs/OPEN_QUESTIONS.md`.
