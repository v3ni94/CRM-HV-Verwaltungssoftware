# AI-LOOKUP-01 Assistent: Antworten aus Plattformdaten nur über geprüfte Abfragen, Links nur von der Plattform, Änderungen nur als Vorschlag

| Field | Content |
| --- | --- |
| ID | `AI-LOOKUP-01` |
| Title | Der KI-Assistent beantwortet Fragen zu Kontakten, Objekten, Einheiten, Verträgen, Tickets und Seiten aus deterministischen, berechtigungsgeprüften Abfragen im Kontext des Aufrufers; Links stammen nur von der Plattform; Änderungen entstehen nur als Vorschlag mit menschlicher Bestätigung |
| Scope | Aufgabe `answer_question` (`POST /ai/conversations/{id}/messages`), Module `mhvp.ai.lookup`, `mhvp.ai.chat_actions`, `mhvp.ai.gateway` (Gesprächsverlauf), `mhvp.ai.jobs`; CRM-Chatblase und Assistentenprotokoll. Alle Mandanten, CRM-Nutzer. Keine Buchung, kein Geldfluss, Gates G1 bis G5 unberührt |
| Source status | Produktschutz und fachliche Umsetzung (Regeln 0.1.6, 0.1.13, 9.1 Datenschutz); keine Norm aus dem Quellenregister |
| Acceptance case | kein Anhang-D-Fall; Tests `apps/api/tests/integration/test_ai_lookup.py`, `apps/api/tests/unit/test_ai_lookup.py`, `apps/api/tests/unit/test_ai_chat_actions.py`, `apps/web-crm/src/components/ai/ChatLinks.test.tsx`, `apps/web-crm/src/lib/chat-suggestions.test.ts`, `apps/web-crm/src/components/ai/AiChatWidget.test.tsx`, `apps/web-crm/src/components/ai/ChatActionProposal.test.tsx` |
| Implementation | Migration 0223 (`ai_message.links`), Prompt `answer_question/v2`, Seiten- und Handbuchindex `mhvp/ai/help_index.json` (erzeugt mit `scripts/build_help_index.py`) |
| Change reason | Betreiberauftrag vom 28.09.2026: Chat soll aus den eigenen Daten antworten, mit Links, seitenbezogenen Vorschlägen, im Gespräch und mit Änderungen nur als Vorschlag. Review 28.09.2026 (zehn bestätigte Befunde): Anweisung außerhalb des Datenblocks, Feldinhalte einzeilig, Postfachregel für Mailfakten, deterministische Absichts- und Wertprüfung für Chat-Aktionen, Bankverbindungen auch in Notiz- und Tickettexten, Maskierung für E.164-Nummern und jede IBAN-Schreibweise, Ticketanlage in einer Transaktion, keine Import-Rücknahme für Chat-Aktionen, maskierte Lernbeispiele, v1-Prompt außerhalb des Chats, neue Konversation je Datensatz |

## Regeln

- Die Suchwerkzeuge laufen in der Sitzung des Aufrufers unter Mandanten-RLS und prüfen je
  Werkzeug die Berechtigung des regulären Endpunkts: Kontakte `contacts:read`, Objekte und
  Einheiten `properties:read`, Verträge `contracts:read`, Tickets `tickets:read`, Mails am
  geöffneten Datensatz `communication:read`. Ohne Berechtigung liefert das Werkzeug nichts, die
  Antwort nennt "Ohne Berechtigung nicht durchsucht". Je Werkzeug höchstens 10 Treffer.
- Die Werkzeugauswahl ist deterministisch (Suchbegriffe, Absichtswörter, geöffneter Datensatz).
  Die KI wählt keine Werkzeuge; sie formuliert die Antwort aus den Treffern (offene Frage
  AI-LOOKUP-Q1).
- Die Anweisung des Nutzers steht in einem eigenen Abschnitt `<frage>` vor dem Datenblock;
  Treffer, Fakten und Gesprächsverlauf gehen als Daten in `<daten>`, maskiert wie jede Eingabe
  von `answer_question` (Telefon, E-Mail, IBAN; auch E.164-Nummern anderer Länder und jede
  Schreibweise einer IBAN). Kontaktzeilen enthalten für das Modell nur Platzhalter statt
  Telefon und E-Mail; der Chat zeigt die Werte in der Trefferliste. Spitze Klammern in
  Feldinhalten werden neutralisiert, jeder Feldinhalt steht einzeilig auf der Zeile seines
  Treffers (kein Zeilenumbruch aus Ticketbeschreibungen, Betreffzeilen oder Namen), damit kein
  Datensatz den Datenblock schließen oder eine Anweisung oder einen Gesprächsschritt
  vortäuschen kann. Datensatzinhalte sind Daten, keine Anweisungen.
- Mailfakten zum geöffneten Kontakt oder Ticket folgen der Postfachregel der Mail-Endpunkte:
  Mitglieder sehen Mails ohne Postfach, aus Standardpostfächern und aus freigegebenen
  Postfächern, Administratoren alle; Kopien in weiteren eigenen Postfächern bleiben verborgen.
- Links (Typ, ID, Bezeichnung, CRM-Pfad) erzeugt nur die Plattform; sie stehen an der Nachricht
  (`ai_message.links`, Protokoll) und am Lauf. Die Oberfläche rendert nur interne Pfade.
  Keine Treffer: die Antwort sagt es ausdrücklich.
- Ohne freigegebenen Anbieter, bei erschöpftem Budget oder Anbieterfehler antwortet die
  Plattform mit der Trefferliste und sagt in einem Satz, dass die KI nicht verfügbar ist.
- Änderungswünsche (Kontaktdaten, Notiz am Kontakt, neues Ticket) werden zu einem Vorschlag
  `chat_action`, nur für Chatläufe mit Plattformsuche, nur für Datensätze aus den Treffern
  desselben Laufs und nur, wenn die Nachricht des Nutzers selbst (ohne den Seitenhinweis der
  Chatblase) die Änderung, die Notiz oder das Ticket verlangt; eine Aktion, die das Modell aus
  einer Mail, einer Ticketbeschreibung oder von sich aus vorschlägt, wird verworfen und
  protokolliert. Telefon und E-Mail nimmt die Plattform aus der Nachricht des Nutzers, nie
  aus der Modellausgabe; neue Namen und Anschriften müssen wörtlich in der Nachricht stehen,
  sonst fragt die Antwort danach. Bankverbindungen werden nie vorgeschlagen, auch wenn die
  Nachricht, der Notiztext oder der Tickettext sie nur erwähnt oder eine IBAN enthält; sie
  bleiben beim Vier-Augen-Weg der Kontaktakte. Der Vorschlag zeigt die Begründung des Modells.
  Geschrieben wird erst mit `POST /ai/proposals/{id}/apply` und der Berechtigung des
  Zielendpunkts (`contacts:update`, `tickets:create`), Entscheidung, Importlauf, Ereignis und
  Datensatz (auch das Ticket) in einer Transaktion. Der Importlauf einer Chat-Aktion hat keine
  Positionen; `POST /imports/{id}/undo` lehnt ihn ab (409), der Datensatz wird über seine
  eigenen Endpunkte geändert.
- Ein verworfener Chat-Vorschlag mit Begründung wird als Lernbeispiel maskiert gespeichert
  (Telefon, E-Mail, IBAN); die Beispiele im Prompt werden bei maskierten Aufgaben zusätzlich
  maskiert.
- `answer_question` außerhalb des Chats (Automation `ai_task`, Intake) erhält Prompt v1 und
  nie eine Chat-Aktion; v2 gilt nur für `POST /ai/conversations/{id}/messages`.
- Die Chatblase legt je geöffnetem Datensatz eine eigene Konversation an; beim Seitenwechsel
  wird die vorherige Konversation nicht weiterverwendet.
- Ohne `documents:read` wird die Frage ohne Dokumentsuche beantwortet; angehängte Dokumente
  verlangen weiterhin `documents:read` (403).
