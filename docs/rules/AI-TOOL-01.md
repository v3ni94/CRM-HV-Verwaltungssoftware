# AI-TOOL-01 Assistent: vom Modell geplante Nachschlagewerkzeuge (Tool Use), nur lesend, mit den Rechten des Aufrufers

| Field | Content |
| --- | --- |
| ID | `AI-TOOL-01` |
| Title | Das Modell kann im Chat über Werkzeuge in Fachdaten nachschlagen (Kontakte, Verträge, offene Posten, Dokumente, Termine, Kontenplan); die Werkzeuge sind deterministisch, nur lesend, mandantengebunden und prüfen die Rechte des Aufrufers |
| Scope | Aufgabe `answer_question`, Module `mhvp.ai.tool_use`, `mhvp.ai.gateway` (`_tool_loop`), `mhvp.ai.providers` (`Completion.tool_calls`), CRM-Chat (`ChatTools`). Keine Buchung, kein Geldfluss, Gates G1 bis G5 unberührt |
| Source status | Produktschutz und fachliche Umsetzung (9.1 Kontext, Tool Use und Datenschutz; Regeln 0.1.6, 0.1.13); keine Norm aus dem Quellenregister |
| Acceptance case | kein Anhang-D-Fall; Tests `apps/api/tests/integration/test_ac08_ai_tool_use.py`, `apps/api/tests/unit/test_ac08_tool_use.py`, `apps/web-crm/src/components/ai/ChatTools.test.tsx` |
| Implementation | Befund GA10-06, Paket AC08, Migration 0341 (noop: Schalter in `ai_provider_config.models`, Protokoll in `ai_task_run.input_ref`) |
| Change reason | Lückenliste 01.10.2026 GA10-06: bisher wählte nur die Plattform die Suchen (AI-LOOKUP-01); die Entscheidung AI-LOOKUP-Q1 bleibt beim Betreiber, daher Standard aus |

## Regeln

- Schalter: Werkzeuge nur, wenn der Stufeneintrag des Anbieters `models.<stufe>.tool_use = true`
  trägt. Damit gelten die bestehenden Freigaben (Vier-Augen-Freigabe, AVV-Nachweis, Opt-out,
  Budget) unverändert. Standard aus; ohne Schalter läuft der Chat wie nach AI-LOOKUP-01.
- Rechte: Beim Senden der Frage werden Berechtigungen, Rollen und Zuständigkeiten (Rechtsträger
  A37, Objektzuordnung M2-02) des Aufrufers am Lauf hinterlegt. Der Worker führt jedes Werkzeug
  in der Mandantentransaktion des Laufs mit genau diesem Principal aus; jedes Werkzeug prüft
  die Berechtigung seines regulären Endpunkts (Kontakte `contacts:read`, Verträge
  `contracts:read`, offene Posten und Kontenplan `accounting:read`, Dokumente
  `documents:read`, Termine jedes Mitglied, eigene und geteilte). Ohne Berechtigung: keine
  Treffer, Protokoll "ohne Berechtigung". Dem Modell werden nur erlaubte Werkzeuge angeboten.
- Grenzen: höchstens 6 Aufrufe in höchstens 3 Runden und 20 Sekunden; danach antwortet das
  Modell ohne weitere Werkzeuge. Je Aufruf höchstens 10 Treffer.
- Maskierung: Werkzeugausgaben gehen nur maskiert (`mask_personal_data`) und als Datenblock
  `<werkzeugdaten>` an den Anbieter, spitze Klammern neutralisiert; Kontakttreffer ohne
  Telefon und E-Mail. Die Suchtexte im Protokoll sind ebenfalls maskiert.
- Protokoll: `input_ref.tool_calls` am KI-Lauf mit Werkzeug, maskierten Parametern, Erlaubt,
  Trefferzahl, Runde und Treffer-Ids. `GET /ai/runs/{id}` liefert `tools_used`; das Chat-Widget
  zeigt "Verwendete Nachschlagewerkzeuge".
- Die Schnittstelle ist anbieterneutral: das Modell fordert Werkzeuge im strukturierten
  Antwortschema an (`tool_calls`). Native Tool-Use-Parameter der Anbieter werden nicht genutzt.
