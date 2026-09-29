# M12-06 Gelernte Bankregeln aus wiederholten Entscheidungen

| Field | Content |
| --- | --- |
| ID | `M12-06` |
| Title | Regelvorschläge aus wiederholten gleichen Entscheidungen von Personen je Rechtsträger, Gegenpartei, Richtung und Konto; Schwelle je Mandant mit niedrigerer Schwelle für wiederkehrende Muster; Widerspruch zieht den Vorschlag zurück; Annahme erzeugt eine Bankregel im Zustand vorgeschlagen (verengen erlaubt, erweitern nicht); Aktivierung im bestehenden Vier-Augen-Pfad ersetzt ältere gelernte Regeln desselben Schlüssels |
| Scope | Alle Mandanten und Rechtsträger, Ein- und Ausgänge, nur mit `learning_bookkeeper_enabled`. Quelle sind ausschließlich Entscheidungen von Personen an nicht stornierten Buchungen, Ablehnungen mit Grund und Stornos (Gegenbeispiel); Automatikbuchungen, Immoware24-Journal, Importrohzeilen, Entwürfe und Modellantworten nie (7.4 Nr. 6). Schritt S5 des Fahrplans. Nicht erfasst: Löschlauf 24 Monate (M12-06 Auflage, siehe offene Punkte), KI-Nachweise (S8) |
| Source status | Fachliche Umsetzung nach 7.4 Nr. 2, 4 und 6, 6.9.4, D51; Produktschutz: Schwellen (A-086), Zwecktoken als All-of-Bedingung neben Gegenparteischlüssel und Betragsspanne (Fahrplan 3.6: Schlüsselwörter allein lösen nie aus), Bulk-Entscheidungen mit halbem Gewicht. Zahler-IBAN wird nie in Kontakte übernommen (nur Fingerabdruck als Merkmal, PÜ04) |
| Acceptance case | D51 (Regel nie produktiv ohne Entscheidung und Test). Tests `tests/unit/test_bank_rule_learning.py` (Schlüssel, Zwecktoken, Gewichtung, Schwellen, Verengung), `tests/unit/test_m12_levels_replay.py` (Replay der Lernfolgen mit festen Sollwerten), `tests/integration/test_m12_automation_levels.py::test_rule_proposals_threshold_contradiction_and_four_eyes` (Vorschlag nach dem dritten identischen Fall, Nachweis, Fremdmandant 404, Erweiterung 422 `MHVP-BANK-0024`, Annahme erzeugt Regel proposed, Vier Augen bei der Freigabe, Vorschlag bucht nichts, Widerspruch zieht zurück, Ablehnung mit Verdopplung) |
| Implementation | Migration `0241`: Tabelle `bank_rule_proposal` (RLS, höchstens ein offener Vorschlag je Musterschlüssel), `bank_rule.learned_from_proposal_id`, `contradiction_count`, `superseded_by_id`, `tenant_settings.bank_rule_proposal_threshold` (5) und `bank_rule_recurring_threshold` (3, beide über `PATCH /tenant/settings`, Bereich 2 bis 50). Modul `mhvp.banking.learning` (`observe` im Savepoint nach jeder Buchung, Ablehnung und jedem Storno; reine Streak-Funktionen `trailing_streak`, `qualifies`, `next_status` aus `mhvp.automation.learning`), `posting_proposal.rule_matches` um `creditor_id` und `purpose_keywords` (All-of) erweitert. Endpunkte `GET /banking/rule-proposals`, `POST /banking/rule-proposals/{id}/accept`, `POST .../reject`; Supersede in `POST /banking/rules/{id}/activate`. Ereignisse `bank_rule_proposal.created`, `.withdrawn`, `.accepted`, `.rejected`, `bank_rule.superseded`, `bank_rule.downgraded`. CRM: `components/banking/BankRuleProposals.tsx` auf der Seite Bankregeln |
| Change reason | Fahrplan S5 vom 28.09.2026 und Betreiberauftrag vom 29.09.2026 ("das System lernt mit jeder Buchung", 90 Prozent der Buchungen wiederholen sich monatlich oder jährlich): Regeln entstehen aus echter Arbeit und durchlaufen den bestehenden Vier-Augen-Pfad; kein Vorschlag bucht oder aktiviert etwas |

## Ablauf

1. Nach jeder Entscheidung einer Person lädt `learning.observe` die geschlossenen Entscheidungen
   derselben Gegenpartei (IBAN-Fingerabdruck, sonst Gläubiger-ID), desselben Rechtsträgers und
   derselben Richtung und bildet je Entscheidung den Wert Kontomuster (Konten der Buchung ohne
   das Bankkonto); eine Ablehnung nennt das abgelehnte Konto, ein Storno ist ein Nein für das
   stornierte Muster. `trailing_streak` liefert die neueste widerspruchsfreie Folge.
2. Nachweisgewicht: 1 je Entscheidung, 0,5 je Massenbestätigung. Schwelle: `bank_rule_proposal_threshold`
   (Standard 5); sind alle Beträge der Folge identisch (wiederkehrendes Muster), gilt
   `bank_rule_recurring_threshold` (Standard 3). Muster mit mehr als einem Konto (Splits) werden
   nicht gelernt.
3. Erreicht die Folge die Schwelle, entsteht oder aktualisiert sich der Vorschlag `proposed` mit
   Nachweis (Entscheidungs- und Umsatz-IDs, Zeitraum, Beträge), Betragsspanne, Zwecktoken (in
   jedem Fall enthalten, keine Namens- und Stoppwörter, höchstens fünf), Richtung, Konto und
   abgeleiteter Aktionsart (`debtor_payment`, `creditor_payment`, `posting`). Existiert bereits
   eine Regel (vorgeschlagen, freigegeben, aktiv) mit gleichem Schlüssel und Konto, entsteht kein
   Vorschlag (Deduplikation).
4. Widerspruch (anderes Konto, Ablehnung des Kontos, Storno) beendet die Folge und zieht den
   offenen Vorschlag zurück (`withdrawn`). Nach einer Ablehnung durch eine Person erscheint das
   Muster erst bei doppeltem Nachweis erneut (`next_status`).
5. Annahme (`accounting:approve`, angemeldete Person) erzeugt die `BankRule` im Zustand
   `proposed` mit `match` aus Schlüssel, Betragsspanne und Zwecktoken und `action` aus Konto;
   verengen (kleinere Spanne, zusätzliche Token) ist erlaubt, erweitern wird mit 422
   `MHVP-BANK-0024` abgewiesen. Die annehmende Person ist Erstellerin der Regel und darf sie
   nicht freigeben; Freigabe und Aktivierung (`max_amount`, Testnachweis) wie bei jeder Regel.
6. Aktivierung einer gelernten Regel schaltet ältere gelernte Regeln desselben Schlüssels und
   Kontos ab (`bank_rule.superseded`, `superseded_by_id`); handgeschriebene Regeln bleiben
   unberührt. Jede Regeländerung ist eine neue Zeile.
7. Verfall: jeder Storno einer Automatikbuchung zählt `contradiction_count`; Grundcode
   `automation_error` stuft die aktive Regel auf `approved` zurück, ein zweiter Fall schaltet ab
   (`bank_rule.downgraded`, siehe M12-05).

## Offene Punkte

- Der tägliche Löschlauf (24 Monate) für `posting_decision` und `bank_rule_proposal` ist nicht
  umgesetzt: der Guard-Trigger `mhvp_posting_decision_guard` verbietet jedes Löschen; die
  Aufbewahrung nach der Auflage M12-06 braucht eine eigene Entscheidung zur Ausnahme des
  Löschlaufs vom Guard (OPEN_QUESTIONS M12-06).
- Regeln ohne Treffer seit 180 Tagen werden noch nicht als veraltet gekennzeichnet.
