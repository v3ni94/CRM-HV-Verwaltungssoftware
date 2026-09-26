# M19-08 Anruf-Mails der Telefonassistenz (Hallo Heidi): Erkennung, Zuordnung, Vorschlag

| Field | Content |
| --- | --- |
| ID | `M19-08` |
| Title | Gesprächsprotokolle der KI-Telefonassistenz werden deterministisch erkannt und zugeordnet; eine neue Rufnummer wird nur als Vorschlag mit Antwortentwurf angeboten |
| Scope | `mhvp.tickets.call_assistant` (`is_call_mail`, `extract`, `merge_ai`, `resolve`, `propose_call`, `reply_for_call`), Aufruf aus `mhvp.tickets.proposals.propose_contact_change`, `POST /tickets/{id}/proposals/{pid}/accept-and-reply`, Einstellungen `GET/PUT /mail/call-assistant` (`tenant_settings.call_assistant`), KI-Aufgabe `call_summary`; alle Mandanten, kein Geldfluss, keine Freigabestufe betroffen |
| Source status | Fachliche Umsetzung (Betreiberauftrag 26.09.2026, Version 1.24.0, Migration 0131 nach Zusammenführung 1.25.0). Produktschutz nach Regel 0.1.6 und M19-05: Stammdaten nur als Vorschlag, nie Bankdaten, kein automatischer Versand. Datenschutz: Auftragsverarbeitung für die Telefonassistenz und für den KI-Anbieter offen (M19-03, M7-01, M12-01) |
| Acceptance case | keine in annex D; Tests `apps/api/tests/unit/test_ticket_call_assistant.py` (Erkennung über Absender, Betreff und Text, Extraktion aus Protokollen, Varianten, Rufnummernnormierung und Label, KI füllt nur Lücken, Namens- und Straßenabgleich), `apps/api/tests/integration/test_ticket_call_assistant.py` (Protokoll bis Entwurf an den Anrufer, 422 ohne E-Mail-Adresse und ohne Kontakt bei offenem Vorschlag, Mandantentrennung und Berechtigung), `apps/api/tests/integration/test_m19_ticket_proposals.py` (Anruf mit Namensvetterin, zweiter Anruf ohne neuen Vorschlag, Einstellungen) |
| Implementation | Migration `0131_call_assistant` (Enumwert `ai_task.call_summary`, Spalte `tenant_settings.call_assistant` JSONB `{"enabled", "sender_patterns", "keywords"}`), `mhvp.tickets.call_assistant`, Web `CallAssistantSettings` (Einstellungen, Postfächer), Vorschlagsanzeige im Ticket mit Aktion Freigeben und antworten |
| Change reason | Betreiberauftrag 26.09.2026: Anrufe der Telefonassistenz sollen ohne Handarbeit dem richtigen Kontakt, Objekt und der Einheit zugeordnet und neue Rufnummern nachgetragen werden |

## Regeln

- Erkennung nur bei aktivierter Erkennung je Mandant (`enabled`, Standard an): Treffer eines
  Absendermusters in der Absenderadresse (Standard `hallo-heidi`, `halloheidi`,
  `hallo.heidi`) oder eines Kennworts im Betreff (Standard `hallo heidi`). Ein Kennwort nur im
  Text zählt ausschließlich zusammen mit einer beschrifteten Rufnummer (Rufnummer, Telefon,
  Handy, Mobil, Rückrufnummer und Varianten), damit eine Anrede an eine Mitarbeiterin keinen
  Anruf auslöst. Leere Listen in der Einstellung bedeuten die Standardwerte.
- Extraktion zuerst deterministisch (Regex): Anrufernummer (E.164 nach
  `mhvp.contacts.validation.normalise_phone`, Label `mobile` bei +4915, +4916, +4917, sonst
  `other`), Anrufername mit Anrede, Objekt (dreistellige Objektnummer oder Anschrift), Einheit
  (Whg., WE, Etage) und Anliegen, Rückrufwunsch. Die KI-Aufgabe `call_summary` läuft mit
  maskierten Kennungen (`mask_identifiers`) und ergänzt bei Sicherheit ab 0,5 nur fehlende
  Felder; die Rufnummer kommt immer aus der deterministischen Stufe. Ein Fehler des Anbieters
  blockiert nichts.
- Zuordnung in fester Reihenfolge: Objekt über Nummer, sonst über Straße und Hausnummer (nur
  bei genau einem Treffer); Personen mit laufendem Miet- oder Eigentumsvertrag an diesem Objekt
  per Nachname und, wenn vorhanden, Vorname; bei mehreren Treffern schränkt die Einheit ein,
  bleiben mehrere, werden sie als Kandidaten geführt. Ohne Objekttreffer der Name im
  Mandanten, nur bei genau einem Treffer (höchstens sechs Kandidaten). Zuletzt die Rufnummer,
  nur bei genau einem Kontakt. Kontakt, Objekt und Einheit werden am Ticket nur gesetzt, wenn
  das Feld leer ist. Das Ergebnis steht als `TicketEvent` `call_summary` am Ticket.
- Ein Vorschlag (`AiProposal`, `entity_type="contact_change"`, `proposed.kind="call"`)
  entsteht nur, wenn eine Anrufernummer erkannt wurde und sie beim zugeordneten Kontakt nicht
  hinterlegt ist, oder wenn kein Kontakt zugeordnet werden konnte. Er enthält genau die
  Änderung `phone` mit Label, nie Bankdaten (`bank_change_mentioned=False`), und einen
  Antwortentwurf (Playbook zum Anliegen, sonst allgemeiner Text).
- `accept-and-reply` übernimmt die Nummer wie `accept` (M19-05) und legt die Antwort als
  ausgehende Nachricht im Status Entwurf am Ticket an, Empfänger ist die E-Mail-Adresse des
  Kontakts (nicht die Absenderadresse der Telefonassistenz), ohne `In-Reply-To`. Versendet
  wird nur über den Freigabepfad des Mailmoduls (M20-03, M20-06).
- Ein Entwurf ohne Empfänger entsteht nie (Dokumentationsprüfung 1.25.0): Hat der
  zugeordnete Kontakt keine E-Mail-Adresse oder ist dem Vorschlag kein Kontakt zugeordnet,
  antwortet `accept-and-reply` mit 422 (`MHVP-CORE-0004`, deutscher Hinweistext: Adresse im
  Kontakt nachtragen, über Korrigieren einen Kontakt wählen oder den Vorschlag ohne Antwort
  freigeben). Die Prüfung läuft vor jeder Änderung: der Vorschlag bleibt offen, die Nummer
  wird nicht übernommen, es wird kein Entwurf angelegt. `accept` ohne Antwort bleibt möglich;
  auch `reply-draft` nach der Übernahme weist mit 422 ab, solange keine Adresse vorliegt.
  Dieselbe Prüfung gilt für Mailvorschläge ohne Absenderadresse.
- Für dieselbe Mail entsteht kein zweiter Vorschlag (`_existing`).

## Offene Entscheidung

Auftragsverarbeitung mit dem Anbieter der Telefonassistenz und Datenschutzhinweis für
Anrufer (Speicherung von Rufnummer, Name und Anliegen aus dem Protokoll) sowie die Freigabe
des KI-Anbieters für `call_summary`: `docs/OPEN_QUESTIONS.md` M19-03. Ohne freigegebenen
Anbieter läuft nur die deterministische Stufe.
