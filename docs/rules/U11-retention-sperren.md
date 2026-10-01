# U11 Automatische Löschungssperre bei offenem Verfahren und Vier-Augen-Aufhebung

| Feld | Inhalt |
| --- | --- |
| ID | `U11` (Rest S711-06, Spezifikation 7.11 S04/S05) |
| Geltungsbereich | Mandant, Dokumente (`documents/retention.py`, `documents/services.deletion_blocker`), Vorgänge (Ticket-Sperre) |
| Regeltyp | Produktschutz (0.2), keine Rechtsgrundlage behauptet |
| Quellenstatus Anhang C | keine neue Frist; Fristwerte der Profile bleiben Entwurf (Regel M6-04, Prüfung Steuerberater) |
| Abnahmefall | D43, D46 (Sperre schlägt Frist), Test `tests/integration/test_u11_retention_procedure_holds.py` |
| Änderungsgrund | Lückenliste 30.09.2026, S711-06 teilweise: Verknüpfung mit Verfahren und Aufhebung im Vier-Augen-Prinzip fehlten |

## Regel

1. Automatische Sperre: Ist ein Dokument mit einem Vertrag verknüpft und besteht auf einem offenen Posten dieses Vertrags eine aktive Mahnsperre mit Grund `litigation` (Prozess) oder `insolvency` (Insolvenz) aus der Buchhaltung (M16-03), wird das Dokument nicht gelöscht, weder einzeln noch über Löschvorschläge. Grund im Sperrtext: "Automatische Löschungssperre: offenes Verfahren (...)". Mit Aufhebung der Mahnsperre in der Buchhaltung entfällt die automatische Sperre; die übrigen Prüfungen (Frist, Profil, Dauerunterlage) gelten weiter.
2. Bestrittene Posten, Ratenplan und Aufrechnung lösen keine Sperre aus.
3. Vier Augen: Eine manuelle Sperre am Dokument oder am Vorgang hebt nur eine andere Person auf als die, die sie zuletzt gesetzt hat (Ereignis `document.hold_set` bzw. `ticket.hold_set`). Sonst Fehler `MHVP-GATE-0002` (403).
4. Status: `GET /documents/{id}/retention-status` zeigt manuelle Sperre, Sperrart, automatische Verfahrenssperre, Vorgangssperre, WEG-Dauerunterlage und den aktuellen Löschhinderungsgrund.

## Nicht geregelt (offen)

* Fristbeginn "Beschluss" als eigene Startregel braucht einen neuen Wert der Aufzählung `retention_start` (Schema); bis dahin wird das Beschlussdatum als `retention_base_on` mit Startregel `statement_issued` oder `contract_end` erfasst (Jahresende, verkürzt nie). Siehe OPEN_QUESTIONS U11-01.
* Steuerliche Verfahren (Außenprüfung, Einspruch) haben kein Datenmodell; Sperre bis dahin manuell mit Sperrart `tax_procedure`.
