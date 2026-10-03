# Ausführungsprotokoll Anhang D (Vorlage)

**Zweck:** Nachweis der fachlichen Abnahme der Fälle D01 bis D58 aus Anhang D des Master-Prompts durch den Betreiber und die fachkundige Person (V16). Entscheidungsvorlage: AH14-07 in docs/plans/ENTSCHEIDUNGEN-2026-10-01.md.

**Hinweis Regel 0.1.8:** Ein Testbezug in apps/api/tests ist kein bestandener Fall. Anhang-D-Fälle sind Anforderungen. Ein Fall gilt erst als abgenommen, wenn Ergebnis, Datum, Name und Nachweis eingetragen sind. Sollwerte dürfen nicht an das Ist-Ergebnis angepasst werden (D.3).

**Angaben zur Abnahme:** Version: ______ Commit (Softwarestand): ______ Umgebung: ______ Regelversion (Regeldatei in docs/rules mit Stand): ______ Prüfer: ______ Abnehmende Personen: ______

**Pflichtangaben je Test (Anhang D.3):** Kennung, geprüfte Regelversion, fachliche Annahmen, anonymisierte Eingaben, erwartetes Ergebnis, tatsächlich beobachtetes Ergebnis, Differenz, ausgeführter Testbefehl oder manueller Prüfablauf, Softwarestand, Prüfer und Status. Die Kopfangaben gelten für alle Zeilen, die Spalten der Detailtabelle stehen je Test. Neue Protokolle (docs/acceptance/PROTOKOLL-*.md) werden von `scripts/check_acceptance_protocols.py` auf diese Pflichtangaben geprüft.

**Ergebnis:** bestanden, nicht bestanden, zurückgestellt (mit Begründung im Nachweis).
**Nachweis:** Testlauf (Befehl und Ausgabe), Bildschirmfoto, Beleg oder Rechenweg, jeweils mit Ablageort.

| Kennung | Bezeichnung | Freigabestufe | Ergebnis | Datum | Name | Nachweis |
| --- | --- | --- | --- | --- | --- | --- |
| D01 | WEG-Spitze und Rückstand | G4 | | | | |
| D02 | WEG-Anpassung und Guthaben | G4 | | | | |
| D03 | Tatsächliche Rücklage | G4 | | | | |
| D04 | Interner Banktransfer | G1 | | | | |
| D05 | Echte Gleichzahlungen | G1 | | | | |
| D06 | Zahlung wird nicht bei Export ausgeglichen | G2 | | | | |
| D07 | Teil- und Überzahlung | G1 | | | | |
| D08 | Centverteilung | G1 | | | | |
| D09 | Heizkostenüberleitung | G3/G4 | | | | |
| D10 | CO₂-Stufengrenze | G3 | | | | |
| D11 | Unterjährige Jahresvollständigkeit | G1 | | | | |
| D12 | Abschlag und Schlussrechnung | G1 | | | | |
| D13 | WEG-Ergebnis intern bestätigt, kein wirksamer Beschluss | G4 | | | | |
| D14 | Ergebnisversion nach Beschlussfassung geändert | G4 | | | | |
| D15 | Eigentümerwechsel mit offenen Vorschüssen | G4 | | | | |
| D16 | Nutzen- und Lastenwechsel weicht vom Eigentumswechsel ab | G4 | | | | |
| D17 | Eine Person mit zwei Einheiten, eine Einheit mit mehreren Personen | G4 | | | | |
| D18 | Untergemeinschaft ohne belegte Grundlage | G4 | | | | |
| D19 | Rücklagenzuführung beschlossen, aber unbezahlt | G4 | | | | |
| D20 | Sonderumlage in Raten mit teilweiser Erstattung | G4 | | | | |
| D21 | Vermietetes Wohnungseigentum ohne Miet-Verteilungsschlüssel | G3 | | | | |
| D22 | Mischrechnung Verwaltung, Instandsetzung, Betrieb | G3 | | | | |
| D23 | Abrechnung kurz vor Fristende erzeugt, Zugang nicht rechtzeitig | G3 | | | | |
| D24 | Mietvorauszahlungen offen, Abrechnung erteilt | G3 | | | | |
| D25 | Nutzerwechsel im Winter mit Zwischenablesung | G3 | | | | |
| D26 | Pflichtige Verbrauchsinformation, Portal noch nicht entwickelt | G3 | | | | |
| D27 | Gemischte CO₂-Sachverhalte, Selbstversorgung, fehlende Lieferangaben | G3 | | | | |
| D28 | Neue Rechtsregel gilt erst in späterem Zeitraum | G3 | | | | |
| D29 | Eigentümer beantragt GdWE-Unterlagen außerhalb eigener Einzelabrechnung | G3/G4 | | | | |
| D30 | Fremde GdWE- oder private SEV-Akte ohne Rechtsgrund | G3/G4 | | | | |
| D31 | Mieter beantragt Abrechnungsbelege mit Angaben Dritter | G3 | | | | |
| D32 | Beirat prüft nur ausgewählte Belege | G4 | | | | |
| D33 | Rechnung nach Beiratsprüfung geändert | G4 | | | | |
| D34 | Lesebestätigung oder Ablauf einer Portal-Einladung | G3/G4 | | | | |
| D35 | Betrag oder Empfänger-IBAN nach Zahlungsfreigabe geändert | G2 | | | | |
| D36 | Umgehung der Zahlungsfreigabe mit zweiter Identität | G2 | | | | |
| D37 | Bank lehnt Auftrag ab oder führt nur Teile aus | G2 | | | | |
| D38 | Bereits zugeordnete Zahlung wird zurückgegeben | G2 | | | | |
| D39 | Tilgungsbestimmung gegen Kontenpriorität | G1 | | | | |
| D40 | Mahnung ohne nachgewiesenen Verzug | G1 | | | | |
| D41 | Formal valide E-Rechnung ohne erbrachte Leistung | G1 | | | | |
| D42 | Hybridrechnung mit Widerspruch zwischen XML und PDF | G1 | | | | |
| D43 | Original soll nach OCR gelöscht werden | G1 | | | | |
| D44 | §-35a-Anteil fehlt oder ist KI-Schätzung | G3 | | | | |
| D45 | Steuerliche Option ohne passenden Steuerstatus | G1/G3 | | | | |
| D46 | Aufbewahrung gegen Löschwunsch oder Import-Rücknahme | G1 | | | | |
| D47 | Wiederherstellung eines Backups nach rechtmäßiger Löschung | G1 | | | | |
| D48 | Sollstellungslauf gleichzeitig, Retry und doppelter Aufruf | G1 | | | | |
| D49 | Historischer OP-Stichtag | G1 | | | | |
| D50 | Nur-Lese-Nutzer versucht Finanzänderung | ohne eigene Stufe | | | | |
| D51 | Unbekannte Regel als Konfiguration eingetragen | ohne eigene Stufe | | | | |
| D52 | Parallelbetrieb mit altem Schreibadapter | G1 | | | | |
| D53 | Virtuelle Versammlung ohne Grundlage oder mit Störung | G4 | | | | |
| D54 | Anfechtung gegen Beschluss erfasst | G4 | | | | |
| D55 | Steuerberater- und Prüfexport | G1 | | | | |
| D56 | Private Kaution neben GdWE- und Miet-Bankmitteln | G1 | | | | |
| D57 | KI-Ausgabe enthält Anweisung | ohne eigene Stufe | | | | |
| D58 | Gebührenrechnung der Verwaltung für SEV | G1 | | | | |

## Detailprotokoll je Test (D.3)

| Kennung | Regelversion | Annahmen | Eingaben (anonymisiert) | Erwartet | Beobachtet | Differenz | Testbefehl oder Prüfablauf | Softwarestand | Prüfer | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D__ | | | | | | | | | | |

**Unterschriften:** Betreiber ______ Datum ______ Fachkundige Person ______ Datum ______
