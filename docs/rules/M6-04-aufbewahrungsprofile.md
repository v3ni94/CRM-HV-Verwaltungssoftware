# M6-04 Standard-Aufbewahrungsprofile je Mandant als Entwurf, Löschung bleibt gesperrt

| Field | Content |
| --- | --- |
| ID | `M6-04` |
| Title | Standardprofile der Aufbewahrungsmatrix (V17) werden je Mandant als Entwurf angelegt ("Entwurf, Prüfung Steuerberatung offen"); ein Entwurf gibt keine Löschung frei; Freigabe je Mandant nur mit `tenant_settings:update`, im Vier-Augen-Prinzip und protokolliert |
| Scope | `mhvp.documents.defaults.ensure_retention_defaults` (läuft bei `provision_tenant`, also `make seed` und Mandantenanlage), Tabelle `retention_profile` (Migration 0139: `retention_months`, `permanent`, `review_note`, Startregel `purpose_end`), `GET/POST /retention-profiles`, `POST /retention-profiles/{id}/release`, `deletion_blocker` (Dokumentlöschung, KI-Import-Rückgängig); alle Mandanten |
| Source status | Offene Entscheidung. Betreiberentscheidung 26.09.2026 zu den Fristen (Werte unten), fachliche Prüfung durch die Steuerberatung offen (Eigentümer: Steuerberatung, betroffene Gates G1, G3, G4, G5). Quellen aus Anhang C (R17, R18, R21, S05, S06) sind zu verifizieren, keine Norm wird als geprüft zitiert; die Profile tragen daher `legal_basis` mit dem Vermerk "Prüfung Steuerberatung offen" |
| Acceptance case | D43, D46 (Löschung nur mit freigegebenem Profil): `tests/integration/test_m6_documents.py` (`test_m6_04_*`: Seed als Entwurf, Idempotenz ohne Überschreiben von Betreiberänderungen, Entwurf sperrt Löschung, Freigabe wirkt nur im eigenen Mandanten, Rechte, Mandantentrennung, Dauerunterlagen nie löschbar, Profil ohne Frist 422) |
| Implementation | `mhvp.documents.defaults.STANDARD_RETENTION_PROFILES`, `mhvp.documents.models.RetentionProfile`, `mhvp.documents.schemas.RetentionProfileOut.status` (`entwurf` oder `freigegeben`), Ereignis `retention_profile.released` mit den freigegebenen Werten; Problem-Code MHVP-DOC-0001 (RETENTION_LOCKED) |
| Change reason | Lückenliste 26.09.2026, M6-04: bislang war kein Aufbewahrungsprofil hinterlegt |

## Standardprofile (Betreiberentscheidung 26.09.2026, Entwurf)

| Unterlagenklasse (`document_class`) | Frist | Beginn (`start_rule`) |
| --- | --- | --- |
| `accounting_records` Buchungsbelege | 10 Jahre | Ende des Entstehungsjahres |
| `journals` Journale | 10 Jahre | Ende des Jahres der letzten Eintragung |
| `statements` Abrechnungen | 10 Jahre | Erstellung der Abrechnung |
| `business_letters` Geschäftsbriefe | 6 Jahre | Ende des Entstehungsjahres |
| `tickets` Vorgänge | 6 Jahre | Ende des Jahres der letzten Eintragung |
| `mails` E-Mails | 6 Jahre | Ende des Entstehungsjahres |
| `contracts` Verträge | 10 Jahre | Vertragsende |
| `portal_data` Portaldaten | 6 Monate | Zweckende (`purpose_end`) |
| `applicant_data` Bewerberdaten | 6 Monate | Zweckende (`purpose_end`) |
| `hoa_minutes` WEG-Protokolle | dauerhaft (`permanent`) | keine Löschung |
| `hoa_resolutions` WEG-Beschlüsse | dauerhaft (`permanent`) | keine Löschung |

## Regeln

- Der Seed legt je Mandant nur fehlende Klassen an (Prüfung je `document_class` ohne
  Rechtsträgerart). Bestehende Zeilen, auch vom Betreiber geänderte oder freigegebene, werden
  nie überschrieben oder zurückgesetzt; ein zweiter Lauf fügt nichts hinzu.
- Jeder Entwurf trägt `review_note` "Entwurf, Prüfung Steuerberatung offen" und `status`
  `entwurf`. Solange ein Profil Entwurf ist, bleibt die Löschung jedes zugeordneten Dokuments
  gesperrt (MHVP-DOC-0001); das gilt auch für Löschjobs, Importe und KI-Rückgängig, weil
  alle über `deletion_blocker` laufen.
- Freigabe: `POST /retention-profiles/{id}/release` verlangt `tenant_settings:update`, die
  freigebende Person darf den Entwurf nicht selbst angelegt haben (Vier-Augen-Prinzip,
  Produktschutz), die Freigabe wirkt nur im aufrufenden Mandanten (RLS) und wird als
  `retention_profile.released` mit Klasse, Frist, Startregel, Rechtsgrundlage und bisheriger
  Prüfnotiz protokolliert. Die Prüfnotiz wird bei Freigabe geleert.
- Dauerunterlagen (`permanent`) geben auch nach Freigabe keine Löschung frei.
- Ein Profil ohne Frist (0 Jahre, 0 Monate) ist nur mit `permanent` zulässig (422 sonst).
- Die Zuordnung von Dokumenten zu einem Profil und die Berechnung von `retention_until` bleiben
  manuell (Feld am Dokument); eine automatische Ableitung aus Kategorie oder Rechtsträger ist
  nicht Teil dieser Regel (offen, V17).
- CRM: Seite Einstellungen, Aufbewahrung (Profile bearbeiten, freigeben, Kategorien zuordnen)
  und Seite Dokumente, Löschvorschläge (Nachtrag 27.09.2026 unten). Die Seiten ändern nichts an
  der Sperre: ohne freigegebenes Profil wird kein Dokument gelöscht.

## Nachtrag 27.09.2026: Aufbewahrungsmatrix produktiv (Migration 0175)

Quellenstatus unverändert: Offene Entscheidung, zu prüfen durch Steuerberater (V17). Die
folgenden Regeln sind Fachliche Umsetzung und Produktschutz, keine Rechtsgrundlage.

- Zuordnung Dokumentkategorie zu Profil (`document_category.retention_profile_id`,
  `PATCH /document-categories/{id}`). Ein Dokument erhält beim Speichern oder beim Wechsel der
  Kategorie das zugeordnete Profil und die berechnete Frist; `POST /retention-profiles/apply`
  ordnet den Bestand ohne Profil nach (`all_documents=true` berechnet alle neu). Eine manuell
  gesetzte `retention_until` wird nicht überschrieben.
- Fristberechnung (`mhvp.documents.retention.compute_retention_until`, Annahme A-058):
  `end_of_year_created` 31.12. des Entstehungsjahres plus Frist; `contract_end`,
  `end_of_year_last_entry`, `statement_issued` 31.12. des Jahres des Basisdatums
  `document.retention_base_on` plus Frist; `purpose_end` Basisdatum plus Frist tagesgenau;
  `permanent` kein Datum. Fehlt das Basisdatum, bleibt die Frist leer und das Dokument gesperrt
  ("Der Fristbeginn fehlt").
- Sperre je Vorgang: `POST/DELETE /tickets/{id}/retention-hold` (`documents:update` setzen,
  `documents:approve` aufheben, Ereignisse `ticket.hold_set`, `ticket.hold_cleared`). Jedes an
  den Vorgang gebundene Dokument ist gesperrt, solange die Sperre besteht; die Sperre je
  Dokument bleibt unverändert.
- Löschvorschlagslauf: Beat `mhvp.documents.deletion_proposals` (monatlich, 2. des Monats
  04:20) oder `POST /deletion-proposals` (manuell, `documents:delete`). Er listet nur Dokumente
  mit freigegebenem Profil, abgelaufener Frist vor dem Stichtag und ohne Sperre, die nicht
  bereits in einem offenen Vorschlag stehen; er löscht nichts. Ohne fällige Dokumente entsteht
  kein Vorschlag.
- Vier-Augen-Prinzip: Freigabe (`/approve`, `documents:approve`) nicht durch die Person, die
  den Lauf gestartet hat; Ausführung (`/execute`, `documents:delete`) nicht durch den Freigeber.
  Beim Beat-Lauf sind damit immer zwei Personen beteiligt. Ablehnung (`/reject`) mit Notiz.
- Ausführung: jedes Dokument wird am Ausführungstag erneut mit `deletion_blocker` geprüft
  (Sperre, Vorgangssperre, Frist, Profil) und bei geändertem Inhaltshash zurückgehalten;
  zurückgehaltene Dokumente bleiben mit Grund im Protokoll (`skipped`) und lösen
  `document.deletion_refused` aus. Gelöschte Dokumente laufen über denselben Weg wie
  `DELETE /documents/{id}` (`retention.delete_now`: Index, Original, Spiegelschritte nach
  M6-03: Drive löschen, Paperless Schlagwort "gelöscht").
- Löschprotokoll: `deletion_proposal_item` je Dokument mit Titel, SHA-256, Kategorie,
  Unterlagenklasse, Fristende, Status, Zeitpunkt, ausführender Person und Anzahl der
  Spiegelschritte; der Vorschlag trägt Ersteller, Freigeber und Ausführenden. Das Ereignis
  `document.deleted` enthält zusätzlich `proposal_id` und `approved_by`, so dass das
  Löschjournal (A44) den Lauf nachvollziehen kann.
- Profil bearbeiten (`PATCH /retention-profiles/{id}`): ein freigegebenes Profil wird wieder
  zum Entwurf mit dem Bearbeiter als Ersteller und braucht eine neue Freigabe durch eine
  zweite Person (`retention_profile.updated`); bereits berechnete Fristen bleiben, bis das
  Profil erneut angewendet wird.
- Tests: `tests/unit/test_retention_period.py` (Fristberechnung),
  `tests/integration/test_m6_04_retention_matrix.py` (Zuordnung und Frist, Vorgangssperre,
  Vier-Augen bei Freigabe und Ausführung, Protokoll, Nachprüfung bei Ausführung, monatlicher
  Lauf, Mandantentrennung).
