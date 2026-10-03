# ADR 0034: Kettenprüfung der Kontoauszüge

- Status: Accepted
- Date: 2026-10-02

## Context

Master-Prompt Invariante B09 verlangt, dass Kontoauszüge lückenlos aneinander anschließen. Ein fehlender oder doppelter Auszug verfälscht Salden und Abstimmung (Befund GAH-102).

## Decision

1. Beim Import eines Kontoauszugs prüft `_chain_check` (`banking/services.py:379`) gegen den Vorgänger desselben Bankkontos: Anfangssaldo des neuen Auszugs gleich Endsaldo des Vorgängers (`chain_status` `ok`, `break`, `not_checkable`, `first`; Differenz in `chain_difference`) und lückenlose, überlappungsfreie Zeiträume (`period_status` `ok`, `gap`, `overlap`, mit `gap_from` und `gap_to`).
2. Die Prüfung ist lesend. Ein Bruch ist ein Befund zur Klärung, kein automatisch korrigierter Fehler; nichts wird überschrieben oder gebucht.
3. Fehlen Salden oder Daten, lautet das Ergebnis `not_checkable`, nicht `ok`.
4. Der Abgleichbericht übernimmt Brüche als Befund (`accounting/services.py:1007`, Text "Anfangssaldo weicht um ... vom Endsaldo des Vorauszugs ab").
5. Tests: `tests/unit/test_ai01_bank_chain.py`, `tests/unit/test_aj04_bank_chain_and_interest.py`.

## Consequences

- Fehlende Auszüge fallen beim Import oder im Abgleichbericht auf, bevor Abrechnungen darauf aufbauen.
- Die Klärung eines Bruchs (Auszug nachladen, Bankauskunft) bleibt eine fachliche Aufgabe.
- Auszüge ohne Saldenangabe können die Kette nicht bestätigen.

## Alternatives considered

- Automatisches Auffüllen von Lücken: würde Buchungsgrundlagen erfinden.
- Nur Summenprüfung je Auszug: erkennt fehlende Auszüge nicht.

## References

- `docs/MASTER-PROMPT.md` Abschnitt 7.1 (B09)
