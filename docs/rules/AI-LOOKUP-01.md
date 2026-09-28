# AI-LOOKUP-01 Assistent: Antworten aus Plattformdaten nur über geprüfte Abfragen, Links nur von der Plattform, Änderungen nur als Vorschlag

| Field | Content |
| --- | --- |
| ID | `AI-LOOKUP-01` |
| Title | Der KI-Assistent beantwortet Fragen zu Kontakten, Objekten, Einheiten, Verträgen, Tickets und Seiten aus deterministischen, berechtigungsgeprüften Abfragen im Kontext des Aufrufers; Links stammen nur von der Plattform; Änderungen entstehen nur als Vorschlag mit menschlicher Bestätigung |
| Scope | Aufgabe `answer_question` (`POST /ai/conversations/{id}/messages`), Module `mhvp.ai.lookup`, `mhvp.ai.chat_actions`, `mhvp.ai.gateway` (Gesprächsverlauf), `mhvp.ai.jobs`; CRM-Chatblase und Assistentenprotokoll. Alle Mandanten, CRM-Nutzer. Keine Buchung, kein Geldfluss, Gates G1 bis G5 unberührt |
| Source status | Produktschutz und fachliche Umsetzung (Regeln 0.1.6, 0.1.13, 9.1 Datenschutz); keine Norm aus dem Quellenregister |
| Acceptance case | kein Anhang-D-Fall; Tests `apps/api/tests/integration/test_ai_lookup.py`, `apps/api/tests/unit/test_ai_lookup.py`, `apps/web-crm/src/components/ai/ChatLinks.test.tsx`, `apps/web-crm/src/lib/chat-suggestions.test.ts`, `apps/web-crm/src/components/ai/AiChatWidget.test.tsx` |
| Implementation | Migration 0223 (`ai_message.links`), Prompt `answer_question/v2`, Seiten- und Handbuchindex `mhvp/ai/help_index.json` (erzeugt mit `scripts/build_help_index.py`) |
| Change reason | Betreiberauftrag vom 28.09.2026: Chat soll aus den eigenen Daten antworten, mit Links, seitenbezogenen Vorschlägen, im Gespräch und mit Änderungen nur als Vorschlag |

## Regeln

- Die Suchwerkzeuge laufen in der Sitzung des Aufrufers unter Mandanten-RLS und prüfen je
  Werkzeug die Berechtigung des regulären Endpunkts: Kontakte `contacts:read`, Objekte und
  Einheiten `properties:read`, Verträge `contracts:read`, Tickets `tickets:read`, Mails am
  geöffneten Datensatz `communication:read`. Ohne Berechtigung liefert das Werkzeug nichts, die
  Antwort nennt "Ohne Berechtigung nicht durchsucht". Je Werkzeug höchstens 10 Treffer.
- Die Werkzeugauswahl ist deterministisch (Suchbegriffe, Absichtswörter, geöffneter Datensatz).
  Die KI wählt keine Werkzeuge; sie formuliert die Antwort aus den Treffern (offene Frage
  AI-LOOKUP-Q1).
- Treffer, Fakten und Gesprächsverlauf gehen als Daten in den Prompt, maskiert wie jede Eingabe
  von `answer_question` (Telefon, E-Mail, IBAN). Spitze Klammern in Feldinhalten werden
  neutralisiert, damit kein Datensatz den Datenblock schließen kann. Datensatzinhalte sind
  Daten, keine Anweisungen.
- Links (Typ, ID, Bezeichnung, CRM-Pfad) erzeugt nur die Plattform; sie stehen an der Nachricht
  (`ai_message.links`, Protokoll) und am Lauf. Die Oberfläche rendert nur interne Pfade.
  Keine Treffer: die Antwort sagt es ausdrücklich.
- Ohne freigegebenen Anbieter, bei erschöpftem Budget oder Anbieterfehler antwortet die
  Plattform mit der Trefferliste und sagt in einem Satz, dass die KI nicht verfügbar ist.
- Änderungswünsche (Kontaktdaten, Notiz am Kontakt, neues Ticket) werden zu einem Vorschlag
  `chat_action`, nur für Datensätze aus den Treffern desselben Laufs. Telefon und E-Mail nimmt
  die Plattform aus der Nachricht des Nutzers, nie aus der Modellausgabe. Bankverbindungen
  werden nie vorgeschlagen, auch wenn die Nachricht sie nur erwähnt; sie bleiben beim
  Vier-Augen-Weg der Kontaktakte. Geschrieben wird erst mit `POST /ai/proposals/{id}/apply`
  und der Berechtigung des Zielendpunkts (`contacts:update`, `tickets:create`).
- Ohne `documents:read` wird die Frage ohne Dokumentsuche beantwortet; angehängte Dokumente
  verlangen weiterhin `documents:read` (403).
