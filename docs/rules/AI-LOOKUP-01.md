# AI-LOOKUP-01 Assistent: Antworten aus Plattformdaten nur über geprüfte Abfragen, Links nur von der Plattform, Änderungen nur als Vorschlag

| Field | Content |
| --- | --- |
| ID | `AI-LOOKUP-01` |
| Title | Der KI-Assistent beantwortet Fragen zu Kontakten, Objekten, Einheiten, Verträgen, Tickets, Terminen, Fristen, Dokumenten, WEG (Beschlüsse, Versammlungen, Rücklage), Mieterhöhungen, Aufträgen, Bankumsätzen, offenen Posten und Seiten aus deterministischen, berechtigungsgeprüften Abfragen im Kontext des Aufrufers und des geöffneten Bereichs; Links stammen nur von der Plattform; Änderungen entstehen nur als Vorschlag mit menschlicher Bestätigung |
| Scope | Aufgabe `answer_question` (`POST /ai/conversations/{id}/messages`), Module `mhvp.ai.lookup`, `mhvp.ai.lookup_tools`, `mhvp.ai.chat_actions`, `mhvp.ai.gateway` (Gesprächsverlauf, Eingabebudget), `mhvp.ai.jobs`; CRM-Chatblase (`chat-suggestions.ts`, `chat-context.ts`) und Assistentenprotokoll. Alle Mandanten, CRM-Nutzer. Keine Buchung, kein Geldfluss, Gates G1 bis G5 unberührt |
| Source status | Produktschutz und fachliche Umsetzung (Regeln 0.1.6, 0.1.13, 9.1 Datenschutz); keine Norm aus dem Quellenregister |
| Acceptance case | kein Anhang-D-Fall; Tests `apps/api/tests/integration/test_ai_lookup.py`, `apps/api/tests/integration/test_ai_lookup_areas.py`, `apps/api/tests/unit/test_ai_lookup.py`, `apps/api/tests/unit/test_ai_chat_actions.py`, `apps/api/tests/unit/test_ai_input_budget.py`, `apps/web-crm/src/components/ai/ChatLinks.test.tsx`, `apps/web-crm/src/lib/chat-suggestions.test.ts`, `apps/web-crm/src/components/ai/AiChatWidget.test.tsx`, `apps/web-crm/src/components/ai/ChatActionProposal.test.tsx` |
| Implementation | Migration 0223 (`ai_message.links`), Prompt `answer_question/v3` (v2 bleibt als Vorgängerversion, v1 außerhalb des Chats), Seiten- und Handbuchindex `mhvp/ai/help_index.json` (erzeugt mit `scripts/build_help_index.py`), Bereichswerkzeuge `mhvp/ai/lookup_tools.py`, Routentabelle `apps/web-crm/src/lib/chat-suggestions.ts` |
| Change reason | Betreiberauftrag vom 28.09.2026: Chat soll aus den eigenen Daten antworten, mit Links, seitenbezogenen Vorschlägen, im Gespräch und mit Änderungen nur als Vorschlag. Review 28.09.2026 (zehn bestätigte Befunde): Anweisung außerhalb des Datenblocks, Feldinhalte einzeilig, Postfachregel für Mailfakten, deterministische Absichts- und Wertprüfung für Chat-Aktionen, Bankverbindungen auch in Notiz- und Tickettexten, Maskierung für E.164-Nummern und jede IBAN-Schreibweise, Ticketanlage in einer Transaktion, keine Import-Rücknahme für Chat-Aktionen, maskierte Lernbeispiele, v1-Prompt außerhalb des Chats, neue Konversation je Datensatz. Betreiberauftrag 29.09.2026: Chat immer auf den geöffneten Bereich bezogen (jeder Menüpunkt, jede Unterebene, Einstellungsseiten), Bereichswerkzeuge für Kalender, Fristen, Dokumente, WEG, Mieterhöhungen, Aufträge, Bank und offene Posten, Termin- und Fristeinträge als Vorschlag; Produktionsfehler 29.09.2026 (Anbieter 400, Eingabe über dem Kontextfenster): hartes Eingabebudget je Aufruf |

## Regeln

- Die Suchwerkzeuge laufen in der Sitzung des Aufrufers unter Mandanten-RLS und prüfen je
  Werkzeug die Berechtigung des regulären Endpunkts: Kontakte `contacts:read`, Objekte und
  Einheiten `properties:read`, Verträge `contracts:read`, Tickets `tickets:read`, Mails am
  geöffneten Datensatz `communication:read`. Ohne Berechtigung liefert das Werkzeug nichts, die
  Antwort nennt "Ohne Berechtigung nicht durchsucht". Je Werkzeug höchstens 10 Treffer.
- Die Werkzeugauswahl ist deterministisch (Suchbegriffe, Absichtswörter, geöffneter Datensatz,
  geöffneter Bereich). Die KI wählt keine Werkzeuge; sie formuliert die Antwort aus den Treffern
  (offene Frage AI-LOOKUP-Q1).
- Seitenkontext: Die Chatblase leitet aus Route und Abfrageparametern für jede Seite des CRM
  Bereich, Unterbereich und geöffneten Datensatz ab (`chat-suggestions.ts`, Routentabelle mit
  Vitest über alle `page.tsx`); Einstellungsseiten werden ihrem Eintrag des Einstellungsindex
  zugeordnet. Eine Seite kann einzelne Felder mit `useChatContext({...})` oder dem Attribut
  `data-chat-context` überschreiben. Bereich und Unterbereich gehen als `area` / `sub_area` an
  die API, erreichen das Modell als Kontext ("Geöffneter Bereich im CRM") und wählen die
  Bereichswerkzeuge (`lookup_tools.AREA_MAP`), die ohne Suchbegriff die Standardfragen der
  Seite beantworten. Die Vorschlagsknöpfe sind je Bereich, Unterbereich und Datensatz
  hinterlegt (Deutsch und Englisch).
- Bereichswerkzeuge (`mhvp.ai.lookup_tools`), je höchstens 10 Treffer, in der Sitzung des
  Aufrufers unter RLS: Termine (eigene, geteilte und erzeugte Kalendereinträge im genannten
  Zeitraum, Übergabetermine, nächster freier Werktag als Fakt; Google-Kalender werden nicht
  gelesen und die Antwort sagt das), Fristen (Fristenliste nach Leseberechtigung der Art,
  überfällig oder fällig in N Tagen, eigene Termine mit Erinnerung; Orientierung, keine
  rechtliche Fristberechnung, M1-09), Dokumente (`documents:read`, Titel, Kategorie, Objekt,
  Rechtsträgerscope der Dokumentenliste), Beschlüsse und Versammlungen (`accounting:read`,
  nur Gemeinschaften im Rechtsträgerscope), Rücklage (`accounting:read`, Endstand der letzten
  berechneten Jahresabrechnung; außerhalb des Rechtsträgerscopes sagt das Werkzeug "nicht im
  Zugriff", nie ein Wert), Mieterhöhungen (`contracts:read`), Aufträge (`tickets:read`),
  Bankumsätze (`accounting:read`, nicht zugeordnete Umsätze, Gegenpartei, Beträge als Text,
  nie eine IBAN), offene Posten je Debitor (`accounting:read`, Restbetrag nach Ausgleichen).
  Zeitwörter ("heute", "diese Woche", "in 7 Tagen", "TT.MM.JJJJ") werden deterministisch in
  einen Zeitraum übersetzt und sind keine Suchbegriffe.
- Eingabebudget (`gateway.fit_answer_input`): Der Datenblock eines Chataufrufs wird vor dem
  Aufruf in das Kontextfenster des Anbieters eingepasst (`context_tokens` der Stufe, sonst
  150.000 Token bei 3,5 Zeichen je Token mit Reserve). Gekürzt wird in dieser Reihenfolge:
  gefundene Dokumente (unwichtigste zuerst), dann Auszüge je Dokument, dann Treffer über 10 je
  Werkzeug, dann Verlauf über die letzten 6 Schritte; Frage und Seitenkontext nie. Meldet der
  Anbieter 400 mit Bezug auf Token oder Kontext, wird einmal mit halbiertem Budget wiederholt;
  scheitert auch das, antwortet die Plattform mit der Trefferliste und einem Satz. Die Größen
  stehen in `RunOut.input_stats`.
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
- Änderungswünsche (Kontaktdaten, Notiz am Kontakt, neues Ticket, Termin im CRM-Kalender,
  Fristeintrag) werden zu einem Vorschlag `chat_action`, nur für Chatläufe mit Plattformsuche, nur für Datensätze aus den Treffern
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
- Termin- und Fristeinträge (`calendar_create`, `deadline_create`): nur bei ausdrücklicher
  Bitte in der Nachricht des Nutzers, mit gültigem Datum in einem plausiblen Fenster (sonst
  fragt die Antwort nach dem Datum), Beteiligte nur aus Kontakttreffern desselben Laufs und nur
  als Notiz. Die Übernahme legt einen internen Eintrag im eigenen CRM-Kalender der
  bestätigenden Person an (`workspace.CalendarEntry`, Ziel intern), nie ein Google-Ereignis,
  nie eine Einladung (Regel M23-05); der Fristeintrag trägt die Erinnerungen `1d` und `7d` und
  erscheint in der Fristenliste als Termin. Datum, Uhrzeit und Titel dürfen beim Bestätigen
  korrigiert werden (`entry_date`, `entry_time`, `title`), eine zweite Übernahme liefert 409.
  Buchungen, Zahlungen und Mahnungen löst der Chat nie aus.
- Ein verworfener Chat-Vorschlag mit Begründung wird als Lernbeispiel maskiert gespeichert
  (Telefon, E-Mail, IBAN); die Beispiele im Prompt werden bei maskierten Aufgaben zusätzlich
  maskiert.
- `answer_question` außerhalb des Chats (Automation `ai_task`, Intake) erhält Prompt v1 und
  nie eine Chat-Aktion; v3 (Bereichskontext, Termin- und Fristvorschläge) gilt nur für
  `POST /ai/conversations/{id}/messages`.
- Die Chatblase legt je geöffnetem Datensatz eine eigene Konversation an; beim Seitenwechsel
  wird die vorherige Konversation nicht weiterverwendet.
- Ohne `documents:read` wird die Frage ohne Dokumentsuche beantwortet; angehängte Dokumente
  verlangen weiterhin `documents:read` (403).
