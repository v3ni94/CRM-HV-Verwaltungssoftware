# Evaluation Kontierung Stufe 1, Stand 27.09.2026

Prüfumfang: deterministische Kontierung `mhvp.banking.posting_proposal.propose` (M12-01,
Stufe 1) gegen den synthetischen Testbestand `apps/api/tests/ai_eval/posting_stage1/cases.json`
(M12-02, 200 Fälle). Lauf: `make ai-eval` (Abschnitt `posting_stage1`) und
`pytest apps/api/tests/unit/test_m12_posting_stage1.py`. Keine KI beteiligt, keine echten Daten.

Treffer bedeutet: Quelle (Regel oder Abgleich), Fallklasse, zugeordnete offene Posten, Kennzeichen
„eindeutig“ und bei Regeln die Regel-ID stimmen mit der erwarteten Kontierung überein und
nichts ist buchbar (`postable = false`).

## Trefferquote je Fallklasse

| Fallklasse | Fälle | Treffer | Quote | Erwartetes Verhalten |
| --- | ---: | ---: | ---: | --- |
| Miete mit Verwendungszweck (`rent_with_purpose`) | 32 | 32 | 100 % | Vollausgleich, eindeutig |
| Miete ohne Verwendungszweck (`rent_without_purpose`) | 30 | 30 | 100 % | 15 mit Mandatsreferenz eindeutig, 15 nur IBAN und Betrag als `weak`, nie eindeutig |
| Teilzahlung (`partial`) | 25 | 25 | 100 % | Teilzahlung, offener Rest bleibt, auch von Drittkonten |
| Sammelüberweisung (`collective`) | 25 | 25 | 100 % | Aufteilung auf zwei oder drei Posten eines Schuldners, manuell |
| Rückläufer (`return`) | 15 | 15 | 100 % | erkannt, keine Zuordnung, Storno und Neubuchung |
| Dienstleisterrechnung (`invoice`) | 25 | 25 | 100 % | 15 mit Rechnungsnummer eindeutig, 10 nur IBAN und Betrag als `weak` |
| Kaution (`deposit`) | 15 | 15 | 100 % | Fremdgeld, immer Prüfung; 10 mit Kautionsforderung zugeordnet |
| Unklare Fälle (`unclear`) | 25 | 25 | 100 % | kein Vorschlag mit Zuordnung, Konfidenz höchstens 0,2 |
| Bankregel (`rule`) | 8 | 8 | 100 % | Quelle Regel, Konto aus der Regel, Posten aus dem Abgleich |
| Gesamt | 200 | 200 | 100 % | |

## Einordnung

1. Die Quote ist keine Aussage über echte HVM-Umsätze: der Bestand ist synthetisch und wurde
   von derselben Entwicklung erzeugt wie die Kontierung. Er prüft, dass die vereinbarten
   Fallklassen nachvollziehbar und stabil behandelt werden. Der fachlich zusammengestellte
   Bestand aus anonymisierten Umsätzen mit Sollzuordnung (M12-02, Betreiber Buchhaltung) bleibt
   offen; erst damit ist eine belastbare Trefferquote messbar.
2. Bewusst nicht als Treffer gewertet, sondern als Prüfung: nur IBAN und Betrag (7.4 Nr. 2),
   Teilzahlungen, Sammelzahlungen, Überzahlungen, Kautionen, Rückläufer (7.4 Nr. 4).
3. Die Schwelle in `make ai-eval` liegt bei 90 % Gesamtquote (`STAGE1_THRESHOLD`); der Unit-Test
   verlangt zusätzlich mindestens 80 % je Klasse und meldet die Quote je Klasse in der Ausgabe.
4. Stufe 2 (KI, `propose_posting`) bleibt bis zur Anbieterfreigabe mit AVV (M12-01, M7-01)
   gesperrt; die Offline-Evaluation der Nachverarbeitung (`propose_posting`, 10 aufgezeichnete
   Fälle, Feld-F1 1,0) ist unverändert. Ein Live-Lauf mit echten Modellantworten (M7-05) ist
   ohne Freigabe nicht möglich und nicht erfolgt.

## Nicht ausgeführt

Vergleich mit Immoware24-Zuordnungen (Regel 0.1.8, Zusatzprüfung) und Lauf gegen echte Daten:
beides wartet auf den Bestand nach M12-02.
