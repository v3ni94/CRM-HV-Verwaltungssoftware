# Q06 KI-Gateway Welle 3: Chat-Aktionen, Kaskade, Sammellauf, Mieterhöhungsprüfung

* ID: Q06 (Unterregeln Q06-01 bis Q06-06)
* Geltungsbereich: Domäne `mhvp.ai` mit kleinen Aufrufen in `letting` (KI-Prüfung des Mieterhöhungsfalls) und `portal` (KI-Vorqualifizierung des Portal-Chats). Gates G1 bis G5 bleiben geschlossen; nichts hier bucht, zahlt, versendet oder gibt frei.
* Quellenstatus Anhang C: Fachliche Umsetzung (Masterprompt 9.1, 9.3, 10 Einleitung, 10.1 Schritt 6, 10.3, 6.3, 14 Phase 3, 13.1). Keine Rechtsgrundlage; die Mieterhöhungsprüfung enthält keine Norm (Anhang C führt keine Mietrechtsnorm).
* Abnahmefälle: `tests/integration/test_q06_ai_w3.py`, `tests/unit/test_q06_ai_w3.py`.
* Änderungsgrund: Befunde M7-03, M7-04, M7-05, M7-07, M7-08, M7-09, M26-01, M21-01, M8-05 der Lückenliste 30.09.2026.

## Q06-01 Chat-Aktionen (M7-03, 10.3)

Neue Aktionsarten des Assistenten: `property_create` (Objekt als Vorschlag, Status `onboarding`), `document_file` (an die Nachricht angehängte Dokumente an einem Treffer ablegen), `portal_invite_prepare` (Portalzugang vorbereiten), `letter_create` (Brief aus aktiver Vorlage als Entwurf). Es gelten die Prüfungen von AI-LOOKUP-01: Absicht in der Nachricht des Nutzers, Ziel nur aus den Treffern des Laufs, Bankwörter führen zur Ablehnung. Objektwerte müssen wörtlich in der Nachricht stehen, die Verwaltungsart ist einer der Plattformwerte. Die E-Mail-Adresse der Einladung stammt aus der Kontaktakte, nie vom Modell; es wird nichts versendet und kein Einladungscode im Protokoll gespeichert. Die Vorlage wird deterministisch unter den aktiven Vorlagen gesucht (Code oder Name aus der Anfrage, genau ein Treffer). Geschrieben wird erst mit `POST /ai/proposals/{id}/apply` über die Wege der regulären Endpunkte. Ausnahme: der Portalzugang wird in eigenen Transaktionen angelegt (Plattformnutzer, Mitgliedschaft), die Entscheidung folgt danach.

## Q06-02 Folgeschritte (M7-04, 10.1 Schritt 6)

Nach bestätigtem Kontaktimport, Objektimport oder Chat-Aktion leitet die Plattform Folgeschritte ab (Portaleinladungen für neue Kontakte mit E-Mail ohne Portalzugang, Verträge bei Rolle Eigentümer oder Mieter, Formularanfrage bei unvollständigen Kontakten, Einheiten, Unterlagen). Sie stehen in `summary.next_steps` und als Chatnachricht. Jeder Schritt ist nur ein Angebot und eine eigene, zu bestätigende Aktion.

## Q06-03 Kaskade small zu large (M7-08, 9.3)

Liefert die Stufe `small` einen Schemafehler (nach der einen Wiederholung) oder eine Konfidenz unter der vom Betreiber je Anbieter eingetragenen Schwelle `models.small.cascade_confidence_below` (Wert zwischen 0 und 1), wird dieselbe Eingabe einmal mit der Stufe `large` desselben Anbieters gestellt. Ohne eingetragene Schwelle eskaliert nur der Schemafehler; eine Schwelle wird nie erfunden. Jede Stufe führt Token und Kosten getrennt (`input_ref.cascade`, `RunOut.cascade`), `cost_eur` ist die Summe. Gilt für Einzelaufrufe, nicht für zerlegte Extraktion und den Schnellimport.

## Q06-04 Sperre mit Benachrichtigung (M7-09, 9.1)

Wird ein Lauf wegen erreichten Monatsbudgets gesperrt, erhalten alle Mitglieder mit `tenant_settings:update` eine Benachrichtigung `ai.budget_blocked`, höchstens eine ungelesene je Person. Die KI-Kosten je Monat stehen bereits in `usage_counter.ai_cost_eur` (M27, `mhvp.platform.licensing.count_usage`).

## Q06-05 Sammellauf statt Anbieter-Batch (M7-07, 9.3)

Die Batch-Schnittstellen der Anbieter sind im Adapter nicht belegt. Bis dahin markiert `mhvp.ai.batch.defer` einen wartenden Lauf der Aufgaben `classify_document`, `classify_email`, `summarize`, `propose_posting` für den nächtlichen Sammellauf `mhvp.ai.batch_nightly` (01:30, Warteschlange io). Er läuft über den regulären Gateway-Weg (Freigabe, AVV, Budget, Deduplizierung, Kaskade). Der spätere Wechsel auf den Anbieter-Batch ändert nur `submit_deferred`.

## Q06-06 KI-Plausibilität des Mieterhöhungsfalls (M26-01, 6.3)

Aufgabe `rent_increase_check` (Stufe large, maskiert): Eingabe sind die erfassten Werte und die deterministische Prüfung des Falls ohne Namen, Anschriften und Kennungen der Beteiligten. Ergebnis sind Hinweise mit Schweregrad als `AiProposal` vom Typ `rent_increase_check`, verknüpft als `ai_check_id`. Die Gesamteinschätzung leitet die Plattform aus den Schweregraden ab. Der Vorschlag kann nicht übernommen werden (409), er ist keine Freigabe und keine Rechtsprüfung; Fall, Status und Regelprüfung bleiben unverändert.

## Q06-07 Portal-Chat KI-Vorqualifizierung (M21-01)

Sind Mandantenschalter `chat_ai_prequalification_enabled` und Gateway-Freigabe offen, läuft der maskierte Text (IBAN, E-Mail, Telefon, Anschrift) als `classify_email` durch das Gateway; Kategorie, Dringlichkeit und Zusammenfassung erscheinen unter `ai` als Vorschlag für die Verwaltung. Das Ticket wird nicht verändert, der Portalnutzer erhält keine KI-Antwort.

## Q06-08 Historische Bankzuordnungen als Lernbeispiele (M8-05, 13.1)

Ergänzung zu AI-HIST-01: historische Bankumsätze mit Zuordnung zum Immoware24-Journal (`migrated_bank_link`) werden als nur lesende Beispiele für `propose_posting` geladen: maskierter Verwendungszweck, Richtung, Betragsklasse (nie der genaue Betrag, kein Name, keine IBAN, keine Kennung) und die Buchungszeilen der alten Buchung.
