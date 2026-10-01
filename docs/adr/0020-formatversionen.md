# ADR 0020: Formatversionen und Kompatibilitätstests

- Status: Accepted (Version je Bank und Zielsystem bleibt Betreiberfrage, siehe AA10-02)
- Date: 01.10.2026

## Context

Master-Prompt 6.9.14 und Anhang E E16 verlangen, konkrete Formatversionen je Meilenstein zu
begründen und zu pinnen. Der Code nutzt mehrere Versionen nebeneinander (pain.001.001.03 und
.09, pain.008.001.02 und .08), ohne dass die Begründung dokumentiert ist. Eine Aktualisierung
darf nur mit Kompatibilitätstest erfolgen. Die Anforderungen der Banken ändern sich; die
Versionswahl ist je Bankverbindung konfigurierbar (`PaymentBankConfig`).

## Decision

| Format | Unterstützte Versionen | Standard | Begründung | Quelle der Spezifikation | Test |
| --- | --- | --- | --- | --- | --- |
| pain.001 (Überweisung) | pain.001.001.03, pain.001.001.09 | .09 | .03 ist die bis 2025 verbreitete DK Fassung, .09 die neuere; Banken stellen zu unterschiedlichen Zeitpunkten um | ISO 20022 Message Definitions, XSD unter `apps/api/tests/data/iso20022` | `tests/unit/test_pain001_versions.py`, `tests/unit/test_format_versions_pin.py` |
| pain.008 (Lastschrift) | pain.008.001.02, pain.008.001.08 | .02 | .02 ist die breit akzeptierte SEPA Fassung, .08 die neuere | wie oben | `tests/unit/test_pain008_versions.py`, `tests/unit/test_format_versions_pin.py` |
| pain.002 und camt.054 (Statusbericht) | nur lesend, Namensraum wird geprüft | n/a | Import von Bankstatus, keine Erzeugung | wie oben | `tests/unit/test_m15_payment_run.py` |
| camt.053 (Kontoauszug) | nur lesend, Version wird nicht erzwungen (Namensraum camt.053), Beispiele .02 und .08 in den Tests | n/a | Banken liefern unterschiedliche Versionen, der Parser liest die gemeinsamen Elemente | wie oben | `tests/integration/test_m11_banking.py`, `tests/unit/test_m15_payment_run.py` |
| XRechnung | 3.0, Syntax UBL 2.1 (CustomizationID in `accounting/xrechnung.py`) | 3.0 | Ausgehende Honorarrechnungen, EN 16931 | KoSIT Spezifikation XRechnung | `tests/integration/test_q15_fee_documents.py` |
| ZUGFeRD / Factur-X | nur lesend (CII, Anhangnamen siehe `receipts/einvoice.py`) | n/a | Eingangsrechnungen, kein Erzeugen | FeRD / Factur-X Spezifikation | Tests zu `receipts` |
| HeiWaKo | Standard-Datenaustausch 3.10, akzeptierter Versionsbereich in `metering/heiwako.py` | 3.10 | Einlesen von Verbrauchsdaten | bved / ARGE HeiWaKo | Tests zu `metering` |

Regeln:

1. Eine neue oder geänderte Version wird nur zusammen mit diesem ADR, einer XSD oder
   Spezifikationsdatei im Repository und einem Kompatibilitätstest aufgenommen. Das Pin Test
   `tests/unit/test_format_versions_pin.py` schlägt bei jeder stillen Änderung der
   Versionsmengen oder Standardwerte fehl.
2. Nebeneinander genutzte pain Versionen müssen für Anzahl, Kontrollsumme und
   Ende zu Ende Kennungen denselben Inhalt liefern (Test `test_pain001_versions_carry_same_content`
   und `test_pain008_versions_carry_same_content`).
3. Die Standardversion je Bank steht in `PaymentBankConfig`; bankspezifische Abweichungen
   bleiben ungeprüft, bis eine Bankvorgabe vorliegt (P05).
4. Es werden keine Versionen vermutet. Fehlende Spezifikationsdateien (z. B. XRechnung XSD,
   Schematron) sind in `docs/OPEN_QUESTIONS.md` geführt.

## Consequences

- Versionswechsel erfordern einen kleinen Änderungsaufwand an ADR, Pin Test und XSD.
- Die Erzeugung bleibt hinter G2 (Zahlungsanstoß) beziehungsweise G3 (Mieterabrechnung); der ADR
  öffnet kein Gate.
- Offen: Ob und wann die Standardversionen auf .09 beziehungsweise .08 gehoben werden, hängt
  von den Bankvorgaben ab (AA10-02).

## Alternatives considered

- Nur die jeweils neueste Version: verworfen, da Banken zeitversetzt umstellen.
- Versionen ohne Test pflegen: verworfen (6.9.14).

## References

- `docs/MASTER-PROMPT.md` 6.9.14 und Anhang E E16
- ADR 0001, ADR 0003
