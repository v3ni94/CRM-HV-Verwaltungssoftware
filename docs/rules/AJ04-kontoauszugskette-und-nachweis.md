# AJ04: Kontoauszugskette in der Konsistenzprüfung, Nachweisereignisse Steuer, Zahlung, Finanzierung

| Feld | Inhalt |
| --- | --- |
| ID | AJ04 (GAI-604, GAI-307, GAI-105, GAI-601, GAI-606) |
| Geltungsbereich | Buchhaltung (Konsistenzprüfung, Steuerprofile, § 35a, Gläubiger Identifikationsnummer, Zahlungskonfiguration), WEG Finanzierung |
| Quellenstatus (Anhang C) | B09 Abgleich Bankbestand (7.1), Regel 0.1.6 und B07 (Nachvollziehbarkeit); keine neue Rechtsregel |
| Abnahmefall (Anhang D) | kein eigener Fall; Tests `tests/unit/test_aj04_bank_chain_and_interest.py`, `tests/integration/test_aj04_audit_events.py` |
| Änderungsgrund | Lückenanalyse Welle 21 |

## Inhalt

1. Die Konsistenzprüfung eines Buchungskreises (`GET /accounting/ledgers/{id}/checks`) meldet zusätzlich Befunde der Kontoauszugskette der verknüpften Bankkonten: Anfangssaldo weicht vom Endsaldo des Vorauszugs ab, Anfangssaldo plus Umsätze ergibt nicht den Endsaldo, Lücke oder Überschneidung der Auszugszeiträume. Nur Anzeige, nichts wird korrigiert. Auszüge ohne Salden (CSV) gelten als nicht prüfbar und erzeugen keinen Befund.
2. Änderungen an Steuerprofil je Objekt und je Lieferant, Steuerdaten einer Rechnung, § 35a Kennzeichen (Setzen und Entfernen), Steuerkonten für Habenzinsen, Gläubiger Identifikationsnummer (Rechtsträger und Mandant), Zahlungsformat je Bankkonto und der Schalter der wöchentlichen Zahllaufvorschau erzeugen ein Domainereignis mit alt und neu im Audit. Die steuerliche Einordnung selbst bleibt eine Entscheidung der Steuerberatung.
3. Anlage und Änderung von Maßnahmen, Finanzierungsquellen, Darlehen, Darlehenspositionen, Versicherungsfällen und deren Positionen erzeugen Ereignisse (`hoa.measure.*`, `hoa.loan.*`, `hoa.insurance_claim.*`).
4. Die alte Route `GET /accounting/ledgers/{id}/liquidity` prüft den Rechtsträgerbereich wie `/reports/liquidity`.
5. `interest_amount_for` berücksichtigt die Tageszählung des Mandanten, wenn ein Beginndatum übergeben wird. Ohne Beginn bleibt Tage durch 365. Die Frage AI03-01 bleibt offen; der Standard ändert sich nicht.
