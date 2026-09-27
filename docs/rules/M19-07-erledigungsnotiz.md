# M19-07 Erledigungsnotiz beim Abschluss und Lernbeispiel je Abschluss

| Field | Content |
| --- | --- |
| ID | `M19-07` |
| Title | Jeder Abschlussstatus (done, closed, rejected) verlangt eine Erledigungsnotiz aus der je Mandant wirksamen Artenliste (eingebaute Arten, abschaltbar, plus eigene Arten) und Freitext; jeder Abschluss wird als Lernbeispiel gespeichert |
| Scope | `mhvp.tickets.status` (`ResolutionKind`, `ResolutionIn`, `transition_status`, `record_resolution_example`), `mhvp.tickets.resolution_kinds` (`BUILTIN_RESOLUTION_KINDS`, `ResolutionKindsConfig`, `assert_resolution_kind_allowed`), `mhvp.tickets.routers` (`PATCH /tickets/{id}`, `POST /tickets/bulk-status`, `POST /tickets/merge`, `GET /tickets/resolution-kinds`), `mhvp.platform` (`TenantSettings.resolution_kinds`, `PATCH /tenant/settings`), `mhvp.communication.suggest` (`resolution_example`, `resolution_hint`, `with_resolution_step`, `learn_playbook_from_ticket`); alle Mandanten, kein Geldfluss, keine Freigabestufe betroffen |
| Source status | Fachliche Umsetzung (Betreiberauftrag 26.09.2026, Version 1.24.0, Migration 0130 nach Zusammenführung 1.25.0; Betreiberentscheidung M19-04 vom 26.09.2026: erweiterte und je Mandant pflegbare Artenliste, Migration 0136). Kein Eintrag im Quellenregister (annex C). Produktschutz: Lernbeispiel ohne KI-Lauf, Vorschläge nur als Hinweistext; Datenschutzfrage zu den gespeicherten Beispielen offen (M7-04, ADR 0010) |
| Acceptance case | keine in annex D; Tests `apps/api/tests/integration/test_ticket_resolution.py` (Abschluss ohne Notiz 422, Speicherung nur bei gesetztem Mandantenschalter, Löschung der Beispiele mit dem Kontakt, Bulk mit gemeinsamer Notiz, Zusammenführen setzt Notiz, Statusereignis und Lernbeispiel der Quelltickets, mit und ohne mitgegebene Notiz), `apps/api/tests/integration/test_ticket_resolution_kinds.py` (Standardliste mit den vier neuen Arten, Mandantenkonfiguration, Abschluss mit eigener Art, deaktivierte und unbekannte Art 422 auch bei Sammelaktion und Zusammenführen, geschützte Arten und Obergrenze, Mandantentrennung), `apps/api/tests/unit/test_ticket_resolution_learning.py` (Freitextpflicht nur bei sonstiges, Schritt Erledigung, Hinweis nur aus ähnlichen Beispielen, Merkmale mit erkannten Entitäten), Vitest `ResolutionDialog.test.tsx` (Liste aus dem Endpunkt, deaktivierte Arten ausgeblendet, eigene Art wählbar), `ResolutionKindsSettings.test.tsx`, `KnowledgeBase.test.tsx` |
| Implementation | Migration `0130_ticket_resolution`, `0134_ai_learning_examples_flag` (Mandantenschalter), `mhvp.ai.examples` (`ticket.resolution_kind`, `resolution_note`, `resolved_by`, `playbook.last_used_at`, Enumwert `ai_task.ticket_resolution`), Migration `0136_tenant_resolution_kinds` (`tenant_settings.resolution_kinds`), `mhvp.tickets.status`, `mhvp.tickets.resolution_kinds`, `mhvp.communication.suggest`, Web `ResolutionDialog`, `ResolutionKindsSettings` (Seite `/einstellungen/mandant`), Seite `/einstellungen/wissen` |
| Change reason | Betreiberauftrag 26.09.2026: Abschluss soll dokumentieren, was getan wurde, und die Plattform soll daraus für ähnliche Vorgänge lernen. Betreiberentscheidung M19-04 vom 26.09.2026: die feste Liste reicht nicht für alle Mandanten und Auswertungen, daher vier weitere eingebaute Arten und Pflege je Mandant |

## Regeln

- Ein Wechsel auf `done`, `closed` oder `rejected` ohne `resolution` wird mit 422 abgewiesen
  (`MHVP` Validierungsfehler, Text "Beim Abschluss ist eine Erledigungsnotiz (resolution)
  erforderlich."). Die Flussprüfung (409 bei unzulässigem Wechsel) und die Abschlussprüfungen
  aus M19-02 (Checkliste, Pflichtfelder) laufen vorher; der Administrator-Bypass des Flusses
  (`skip_flow`, siehe M19-09) hebt die Notizpflicht nicht auf.
- Eingebaute Arten (`ResolutionKind`, `BUILTIN_RESOLUTION_KINDS`): `stammdaten_ergaenzt`,
  `handwerker_beauftragt`, `auskunft_erteilt`, `weitergeleitet`, `kein_handlungsbedarf`,
  `abgelehnt`, `zahlung_geklaert`, `termin_vereinbart`, `mangel_behoben`,
  `vertrag_geaendert`, `zusammengefuehrt`, `sonstiges` (die vier Arten Zahlung geklärt,
  Termin vereinbart, Mangel behoben, Vertrag geändert seit der Entscheidung M19-04 vom
  26.09.2026). `note` (höchstens 4000 Zeichen) ist bei `sonstiges` Pflicht, sonst freiwillig.
  `zusammengefuehrt` ist nur für Quelltickets einer Zusammenführung vorgesehen:
  `POST /tickets/merge` setzt sie ohne mitgegebene `resolution` mit dem Text
  "Zusammengeführt in Ticket <nummer>.".
- Artenliste je Mandant (Entscheidung M19-04, 26.09.2026): `TenantSettings.resolution_kinds`
  (JSONB, Migration 0136) mit `disabled` (Codes eingebauter Arten, die der Mandant nicht
  anbietet; `sonstiges` und `zusammengefuehrt` sind nicht abschaltbar) und `custom`
  (höchstens 30 eigene Arten mit Code `^[a-z0-9][a-z0-9_]{1,31}$`, der keiner eingebauten
  Art entspricht, und deutscher Bezeichnung bis 60 Zeichen). Pflege über
  `PATCH /tenant/settings` (`tenant_settings:update`, Änderung als `tenant_settings.updated`
  protokolliert) und in der Oberfläche unter Einstellungen, Mandant und Briefbogen.
  `GET /tickets/resolution-kinds` (`tickets:read`) liefert alle eingebauten Arten mit
  `active` und die eigenen Arten; der Abschlussdialog lädt diese Liste statt einer festen.
- Prüfung des Codes: `ResolutionIn.kind` nimmt jeden Slug an; `transition_status` (und
  `POST /tickets/merge` für die mitgegebene Notiz) prüft gegen die wirksame Liste des
  Mandanten und weist eine deaktivierte, entfernte oder fremde Art mit 422 ab (Text
  "Erledigungsart <code> ist für diesen Mandanten nicht verfügbar."). Die Sammelaktion
  weist die betroffenen Zeilen einzeln aus. Bereits abgeschlossene Tickets behalten ihre Art
  auch nach dem Abschalten oder Entfernen; Verlauf, Lernbeispiele und `resolution_hint`
  arbeiten mit jedem Code, eine entfernte eigene Art wird mit ihrem Code angezeigt.
- `POST /tickets/merge` protokolliert den Abschluss der Quelltickets wie `transition_status`
  (Dokumentationsprüfung 1.25.0): je Quellticket ein `TicketEvent` `status` mit `from`, `to`
  (`closed`), `merge: true` und `data.resolution` (Art und Notiz) sowie ein Lernbeispiel.
  Das gilt mit und ohne mitgegebene `resolution`, also auch für die Standardnotiz
  `zusammengefuehrt`. Die Sammelaktion und der Einzelwechsel schreiben dieselben Einträge;
  ein Quellticket liest sich im Verlauf damit wie jedes andere abgeschlossene Ticket.
- Gespeichert werden `ticket.resolution_kind`, `resolution_note`, `resolved_by` und die
  Notiz im `TicketEvent` `status` (`data.resolution`). Ein Wechsel auf einen offenen Status
  leert die drei Felder; der Verlauf bleibt.
- Die Sammelaktion `POST /tickets/bulk-status` nimmt eine gemeinsame `resolution` für alle
  Tickets des Aufrufs; Zeilen, für die der Abschluss scheitert, werden einzeln ausgewiesen.
- Je Abschluss entsteht nur bei gesetztem Mandantenschalter
  `tenant_settings.ai_learning_examples_enabled` (Migration 0134, Standard aus, `PATCH
  /tenant/settings`, Seite Einstellungen, Mandant; Nachtrag 26.09.2026, ADR 0010) ein
  `AiExample` (Aufgabe `ticket_resolution`, `created_by` ist der Abschließende) mit Eingabe Betreff (300 Zeichen), Anliegen (1000 Zeichen), Kategorie,
  Thema, IDs von Objekt, Einheit und Kontakt sowie Ticket-ID und Ergebnis Art, Notiz, Status
  und die zuletzt versendete Antwort (2000 Zeichen). Es läuft kein KI-Aufruf. Die Speicherung
  liegt in einem eigenen Savepoint; ein Fehler dort stört den Statuswechsel nie. Bei
  ausgeschaltetem Schalter wird nichts gespeichert; vorhandene Beispiele bleiben.
- Löschung mit der Quelle (Nachtrag 26.09.2026, `mhvp.ai.examples`): `DELETE /contacts/{id}`
  löscht in derselben Transaktion die `ticket_resolution` Beispiele der Tickets dieses
  Kontakts (`features.entitaeten.contact_id`). Für einen Ticketlöschpfad steht
  `delete_examples_for_ticket` bereit; Tickets werden derzeit zusammengeführt, nicht gelöscht.
- `learn_playbook_from_ticket` (nur `done` und `closed`) nimmt die Erledigung in den Prompt
  und als Schritt `Erledigung: <Art>: <Notiz>` in das gelernte Playbook; ein vorhandenes
  ähnliches Playbook wird um den Schritt ergänzt (höchstens 20 Schritte).
- `resolution_hint` vergleicht Betreff und Anliegen einer neuen Mail per Schlagwortüberlappung
  mit den letzten 200 Beispielen des Mandanten und liefert die drei besten unterschiedlichen
  Erledigungen als Text "Bei ähnlichen Vorgängen wurde: ...". Der Text geht in den
  KI-Vorschlag (`suggestion.resolution_hint`) und in den Prompt der Mailklassifikation. Er
  ist Hinweis, keine Entscheidung; ein Mitarbeiter bestätigt weiterhin jeden Vorschlag.

## Entscheidung M19-04 (26.09.2026)

Der Betreiber hat am 26.09.2026 entschieden: Die Artenliste wird standardmäßig um Zahlung
geklärt, Termin vereinbart, Mangel behoben und Vertrag geändert erweitert und ist je Mandant
pflegbar (eingebaute Arten abschaltbar außer Sonstiges und Zusammengeführt, bis zu 30 eigene
Arten). `docs/OPEN_QUESTIONS.md` M19-04 ist damit entschieden.

## Offene Entscheidung

Die Lernbeispiele enthalten Betreff, Anliegen, Notiz und Antwortauszug und damit in der Regel
personenbezogene Daten; `docs/OPEN_QUESTIONS.md` M7-04 (Datenminimierung oder
Pseudonymisierung, Aufbewahrung, Löschlauf) ist damit nicht mehr nur strukturell, sondern
inhaltlich offen, siehe ADR 0010. Bis zur Entscheidung ist die Speicherung je Mandant
ausgeschaltet (Standard), die Beispiele selbst verlassen die Plattform nicht; nur der
Hinweistext aus Art und Notiz geht in den Prompt. Offen bleiben Aufbewahrungsfrist,
Löschlauf und Maskierung der Notiz.
