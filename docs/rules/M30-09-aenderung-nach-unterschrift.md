# M30-09 Übergabeprotokoll: Inhaltssperre nach der ersten Unterschrift, Änderung nur mit Grund (Produktschutz)

| Field | Content |
| --- | --- |
| ID | `M30-09` |
| Title | Nach der ersten Unterschrift ist der Inhalt gesperrt; Änderungen nur über die Aktion Änderung nach Unterschrift mit Pflichtgrund, Zeitpunkt und Bearbeiter im Protokollverlauf; alle Unterschriften gelten danach als vor der Änderung geleistet und müssen wiederholt werden |
| Scope | Domäne `handover`, Tabellen `handover_change` (neu), `handover_signature.invalidated_at`, `invalidated_change_id`; CRM und Portal Schreibpfade (`routers.py`, `portal.py` delegiert); alle Mandanten, alle Protokollarten; vor dem Abschluss (Status `draft`, `in_progress`, `signature_pending`) |
| Source status | Keine Rechtsnorm im Quellenregister (annex C) einschlägig; Betreiberentscheidung 28.09.2026 (Plan M31, offene Frage 3) als Produktschutz für den Beweiswert des Protokolls. Die rechtliche Bewertung digitaler Unterschriften bleibt M30-02 |
| Acceptance case | keine in annex D; Test `apps/api/tests/integration/test_m30_handover.py::test_change_after_signature_locks_content_and_records_history` (feste Erwartung: vor der Unterschrift frei änderbar, danach 409 für Räume, Zähler, Schlüssel, Reihenfolge, Fotos und Protokollfelder; Beteiligte, interne Felder und Schrittzeiger bleiben offen; nach der Aktion ist eine Unterschrift ungültig, der Verlauf hat einen Eintrag, das PDF druckt ihn) |
| Implementation | `mhvp.handover.services.content_locked`, `require_content_unlocked`, `record_change`, `changes_of`, `valid_signatures`, `CONTENT_FREE_FIELDS`; `mhvp.handover.routers.change_after_signature` (`POST /handover/protocols/{id}/changes`), `_require_section_writable`; `mhvp.handover.pdf` (Abschnitt Änderungen nach Unterschrift, Kennzeichnung ungültiger Unterschriften); Migration 0239; CRM `HandoverEditor.tsx` (Hinweis, Sheet mit Änderungsgrund), `HandoverSummary.tsx` (Verlauf, Kennzeichnung) |
| Change reason | Betreiberentscheidung 28.09.2026 (M31 WP2): bisher erlaubte der Server bis zum Abschluss jede Änderung, auch nach einer Unterschrift |

## Regeln

- Vor der ersten Unterschrift ist alles frei änderbar (M30-01 unverändert).
- Inhaltssperre: sobald eine gültige (nicht als ungültig gekennzeichnete) Unterschrift am
  offenen Protokoll vorliegt, antworten Anlegen, Ändern, Löschen und Umsortieren der
  Abschnitte Zähler, Räume, Mängel, Schlüssel, Gegenstände und Bemerkungen, Hochladen und
  Entfernen von Fotos und Anhängen sowie Änderungen der Protokollfelder mit 409 und dem
  Hinweis auf die Aktion. Frei bleiben `current_step`, die internen Felder
  (`internal_contact`, `internal_note`, `management_number`, nie im PDF), die Beteiligten
  (eine weitere Person kann noch unterschreiben) und die Unterschriften selbst. Die
  Antwort `content_locked` im Vollausgabeformat zeigt den Zustand; die Oberfläche bietet
  dann keine Bearbeitung an.
- Aktion Änderung nach Unterschrift (`POST /handover/protocols/{id}/changes`, Recht
  `contracts:update`): der Änderungsgrund ist Pflicht (mindestens drei Zeichen). Der Server
  schreibt einen Eintrag `handover_change` mit Grund, Zeitpunkt (`changed_at`, UTC),
  Bearbeiter (`changed_by`, `changed_by_name`) und der Zahl der betroffenen Unterschriften,
  setzt an jeder gültigen Unterschrift `invalidated_at` und `invalidated_change_id`, führt
  den Status `signature_pending` auf `in_progress` zurück und gibt den Inhalt frei. Ohne
  gültige Unterschrift oder nach dem Abschluss antwortet die Aktion 409. Das Ereignis
  `handover.changed_after_signature` wird ausgelöst.
- Ungültige Unterschriften bleiben als Beweis erhalten (Datei, Prüfsumme, Zeitpunkt), zählen
  aber nicht mehr: der Hinweis `signatures_invalidated` ersetzt `no_signature`, die
  Dublettenprüfung je Beteiligtem betrachtet nur gültige Unterschriften, die Leseansicht
  und das PDF kennzeichnen sie mit dem Zeitpunkt der Änderung als vor der Änderung
  geleistet und erneut erforderlich. Das PDF druckt den Verlauf (Zeitpunkt, Bearbeiter,
  Grund, Zahl der ungültigen Unterschriften).
- Eine neue Version (M30-01) kopiert die Unterschriften mit ihrer Kennzeichnung, aber ohne
  Verweis auf den Verlaufseintrag der Vorversion; der Verlauf bleibt bei der Fassung, in
  der er entstanden ist.
- Gehilfen im Portal unterliegen derselben Sperre (Schreibpfade delegieren an den CRM
  Router); die Aktion Änderung nach Unterschrift steht nur im CRM zur Verfügung.
