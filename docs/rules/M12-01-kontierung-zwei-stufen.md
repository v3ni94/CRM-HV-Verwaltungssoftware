# M12-01 Kontierung in zwei Stufen: deterministisch immer, KI nur als freigegebener Vorschlag

| Field | Content |
| --- | --- |
| ID | `M12-01` |
| Title | Zweistufige Kontierung von Bankumsätzen: Stufe 1 deterministisch (Bankregel, Mandatsreferenz, Vertrags- oder Rechnungsnummer, Bestimmung im Verwendungszweck, IBAN des Zahlers, Betrag), immer aktiv; Stufe 2 KI-Vorschlag nur bei Mandantenschalter und freigegebenem Anbieter; nie automatische Buchung |
| Scope | Alle Mandanten, alle Rechtsträger (WEG, Miete, SEV), Ein- und Ausgänge. `mhvp.banking.posting_proposal` (Stufe 1), `mhvp.banking.ai_posting` (Stufe 2), Endpunkt `GET /api/v1/banking/transactions/{id}/posting-proposals`, CRM `TransactionMatcher`. Nicht erfasst: Verrechnung mit Guthaben und Tilgungsfolge (M10-03), Rücklastschriften werden nur erkannt, nicht zugeordnet |
| Source status | Fachliche Umsetzung nach 7.4 Nr. 2 bis 4 und 9.2; Produktschutz (keine Rechtsnorm). Datenschutz: Bankumsätze sind personenbezogene Daten, die KI-Stufe setzt den geprüften AVV und die Anbieterfreigabe voraus (Regel 0.1.13, M7-01). Betreiberentscheidung zum AVV offen |
| Acceptance case | D-Fälle zu 7.4 (Zuordnung nur als Vorschlag, IBAN allein kein Nachweis, Teil- und Sammelzahlungen manuell). Tests `apps/api/tests/unit/test_m12_posting_stage1.py` (200 Fälle, Trefferquote je Fallklasse), `apps/api/tests/integration/test_m12_posting_proposals.py` (API, KI-Stufe gesperrt, nichts gebucht), `apps/web-crm/src/components/banking/TransactionMatcher.test.tsx` |
| Implementation | Migration `0194_posting_proposal_noop` (down_revision `0193`, keine Schemaänderung). Stufe 1 rechnet beim Lesen, speichert nichts; Stufe 2 speichert `AiProposal` (Entitätstyp `posting`). Testbestand `apps/api/tests/ai_eval/posting_stage1/cases.json` (Generator `generate_cases.py`), Auswertung in `mhvp.ai.evaluate.evaluate_stage1` und `make ai-eval` |
| Change reason | Nachtrag 27.09.2026 zu M12-01: die KI-Kontierung war abgeschaltet, ohne dass eine deterministische Kontierung mit Quelle und Konfidenz sichtbar war. Betreiberauftrag: zweistufig, Stufe 1 ohne KI immer aktiv |

## Ablauf

1. Stufe 1a, Bankregeln: freigegebene und aktive Regeln (`bank_rule`, Zustände `approved`
   und `active`) des Rechtsträgers werden nach Priorität geprüft (IBAN-Fingerabdruck, Name,
   Zweck-Muster, Betragsgrenzen). Treffer: Quelle `rule`, Konfidenz 0,9 bei aktiver Regel, 0,6
   bei nur freigegebener Regel, 0,5 bei Überschreiten der Betragsgrenze. Eine Regel der Art
   `debtor_payment` übernimmt den offenen Posten aus Stufe 1b, wenn dieser eindeutig ist.
2. Stufe 1b, Abgleich mit Sollstellungen (Eingang): Punkte je offenem Posten, Mandatsreferenz
   40, Vertragsnummer im Zweck 35, IBAN des Zahlers beim Vertragspartner 15, Betrag gleich
   offenem Betrag 15, Bestimmung im Zweck (Monat, Rechnungs- oder Sollstellungsnummer, D39)
   10. Konfidenz = Punkte / 100, gedeckelt. Mehr als IBAN plus Betrag (30 Punkte) ist nötig,
   damit ein Kandidat als Nachweis gilt (7.4 Nr. 2).
3. Fallklassen der Stufe 1b: `full` (ein Kandidat mit Nachweis, Betrag gleich, einziger Fall
   mit `unambiguous = true`), `partial` (Betrag kleiner), `collective` (genau eine Kombination
   von höchstens sechs Posten, deren Summe dem Betrag entspricht; zwei mögliche Kombinationen
   bleiben `unclear`), `overpayment` (Guthaben bleibt Guthaben), `weak` (nur IBAN und Betrag,
   Konfidenz 0,3), `deposit` (Zweck nennt eine Kaution, Fremdgeld, immer Prüfung), `return`
   (Rücklastschrift oder Rückgabe an Geschäftsvorfallcode oder Zweck erkannt, keine
   Zuordnung, Ausgleich nur durch Storno und Neubuchung), `unclear`.
4. Stufe 1c, Ausgang: offene Verbindlichkeiten mit Rechnungsnummer im Zweck 35, IBAN des
   Empfängers 15, Betrag 15. Nur Empfänger-IBAN und Betrag ergibt `weak`.
5. Stufe 2, KI: nur bei `tenant_settings.ai_posting_enabled` (Standard aus) und freigegebenem
   Anbieter mit AVV-Nachweis (`gateway.posting_block_reason`). Die Antwort wird normalisiert
   (unbekannte Konten und Posten verworfen, Aufteilung gegen Betrag geprüft, Konfidenz
   gedeckelt), als `AiProposal` gespeichert und im CRM mit Quelle `KI`, Konfidenz und
   Begründung angezeigt. Die angegebene Konfidenz ist kein Nachweis (7.4 Nr. 3).
6. Freigabe: jeder Vorschlag ist ein Entwurf. Buchung nur über `POST
   /banking/transactions/{id}/book` durch eine Person mit Buchungsrecht (B01 bis B09, G1);
   die Automatik (`auto-post`) bleibt an aktive Regeln, Mandanten-Opt-in und eindeutige
   Vollzahlung gebunden und ist von dieser Regel nicht verändert.

## Testbestand M12-02 (synthetisch)

200 Fälle in neun Klassen: Miete mit Zweck 32, Miete ohne Zweck 30 (15 mit Mandatsreferenz,
15 nur IBAN und Betrag), Teilzahlung 25 (jede dritte von einem Drittkonto), Sammelzahlung 25,
Rückläufer 15, Dienstleisterrechnung 25 (15 mit Rechnungsnummer, 10 nur IBAN und Betrag),
Kaution 15 (10 mit Kautionsforderung, 5 ohne), unklar 25, Regel 8. Erwartete Kontierung je
Fall im JSON. Der Bestand ist vom Entwickler erzeugt und ersetzt nicht den fachlich
zusammengestellten Bestand aus anonymisierten HVM-Umsätzen (M12-02 bleibt offen).
