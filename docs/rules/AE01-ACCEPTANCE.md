# AE01-ACCEPTANCE: Abnahmeregister unabhängiger Sollwerte (V16)

- **ID:** AE01-ACCEPTANCE
- **Geltungsbereich:** alle Fälle D01 bis D58 aus Anhang D, je Mandant; Freigabestufen G1 bis G4 (nur Nachweis, keine Öffnung).
- **Art:** Fachliche Umsetzung (Anhang D.3: Sollwert vor dem Vergleich festlegen, nie an das Ist anpassen) und Produktschutz (Freigabe nur durch eine zweite Person mit eigenem Recht).
- **Quellenstatus (Anhang C):** keine Rechtsnorm; interne Abnahmeregel. Die Benennung der fachkundigen Person ist Betreiberentscheidung V16 (offen, technisch vorbereitet Welle 16, AE01).
- **Abnahmefall:** Anhang D.3 für jeden Fall; Test `apps/api/tests/integration/test_ae01_acceptance.py`.

## Regel

1. Eine Person mit `acceptance:manage` erfasst je Fall eine Fassung mit Eingaben, Sollwert, Quelle (Pflicht) und Rechenweg als Entwurf und reicht sie ein. Zahlen werden als Zeichenkette erfasst, JSON-Gleitkommazahlen werden abgelehnt.
2. Eine zweite Person mit `acceptance:approve` gibt die eingereichte Fassung frei oder lehnt sie ab. Die Verfasserin oder der Verfasser kann nie freigeben (Dienst und Datenbankbedingung `ck_acceptance_expected_second_person`).
3. Eine freigegebene Fassung bleibt unverändert (Trigger `mhvp_acceptance_expected_guard`); eine neue Freigabe setzt die vorige auf `superseded`. Je Fall gibt es höchstens eine freigegebene Fassung.
4. Abnahmeergebnisse (bestanden, nicht bestanden, Softwarestand, Name) werden nur zu freigegebenen Fassungen und nur durch `acceptance:approve` erfasst und nie geändert oder gelöscht.
5. `acceptance:approve` gehört nicht zur Administratorrolle; es trägt nur die Systemrolle `acceptance_expert` (Fachkundige Abnahmeperson). Lesen dürfen auch `read_only` und Administratoren.
6. Das Register öffnet keine Freigabestufe und ersetzt nicht die Checkliste `g1_acceptance` (M12-09) oder den Vier-Augen-Antrag.

## Änderungsgrund

Betreiberliste vom 01.10.2026, Punkt 1 (V16): technische Vorbereitung der fachlichen Abnahme.
