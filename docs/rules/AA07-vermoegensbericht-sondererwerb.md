# Vermögensbericht im Eigentümerportal und Sondererwerb (7.8, W11, W07)

| Field | Content |
| --- | --- |
| ID | AA07 |
| Title | Bereitstellung des Vermögensberichts je Eigentümer, Freigabeschritt für Sondererwerbe |
| Scope | WEG, Eigentümerportal, Abrechnungspaket (M24), Gate G4 |
| Source status | W11 Satz 1 und W07 Satz 5 bis 7 (Master-Prompt 7.8); Rechtsfolgen der Erwerbsarten nicht entschieden (OPEN_QUESTIONS AA07-01) |
| Requirement type | Fachliche Umsetzung (Bereitstellung, Freigabeschritt), Produktschutz (vier Augen); keine Rechtsgrundlage für die Zuordnung |
| Acceptance case | `tests/integration/test_aa07_asset_provision_acquisition.py` |
| Implementation | GA07-02: ausgestellter Bericht (Status issued) im Portal unter `/portal/owner/asset-reports`, PDF hinter G4, je Abruf eine Zeile pro Eigentumsvertrag in `hoa_asset_report_provision` (Indiz, keine Zustellung); CRM `GET /hoa/asset-reports/{id}/provisions`. GA07-03: Eigentumsverträge mit Beginn oder Eigentumsübergang im Abrechnungsjahr und Erwerbsart ersterwerb, erbfall, zwangsversteigerung, schenkung, sonstig oder Sondernachfolgekennzeichen erzeugen im Abrechnungspaket den Befund `acquisition_unreleased`, bis eine Person die Freigabe beantragt und eine andere sie erteilt hat (`hoa_acquisition_release`, Problemcode MHVP-HOA-0020). Der Zuordnungsvorschlag je Erwerbsart ist ein Text zur Prüfung und ändert die Berechnung in `calc.py` nicht |
| Change reason | GA07-02, GA07-03, 01.10.2026 |

Die Freigabe gilt je Abrechnungsversion; eine neue Version braucht eine neue Freigabe. Wer nicht im Portal abruft, erhält den Bericht auf anderem Weg (Brief); das Protokoll weist Abrufe aus, keine Zustellung.

## Änderung AB07 (01.10.2026)

- GA07-02: Versandpfad per Brief. `POST /hoa/asset-reports/{id}/dispatch` erzeugt je Empfänger eines Eigentumsvertrags zum Stichtag (Zustellregel der Bevollmächtigten) einen Brief, legt ihn als erzeugtes Dokument ab (Kontext `hoa_asset_report`, Verknüpfung mit Kontakt, Vertrag und Gemeinschaft) und übergibt ihn an den bestehenden Versand. Zustellweg: Vorgabe im Aufruf, sonst bevorzugter Weg des Kontakts, sonst Mandantenstandard. Standard: nur Eigentümer ohne Portalabruf; ein Vertrag mit vorhandenem Brief wird übersprungen. Voraussetzung: Status `issued` und Freigabestufe G4. Das Bereitstellungsprotokoll zeigt je Eigentümer Abrufe und Versandeinträge. Ob der Portalabruf genügt, bleibt offen (AA07-02).
- GA07-03: Sonderfälle Ersterwerb, Zwangsversteigerung und Sonderrechtsnachfolge (Kennzeichen am Vertrag, auch bei Kauf) sind mit deutscher Fallbezeichnung (`case_label`) im Befund und in der Liste geführt und mit Freigabeschritt getestet. Die Zuordnung je Erwerbsart ist nicht entschieden (AA07-01); `calc.py` unverändert.
- Quellenstatus: Fachliche Umsetzung (7.8 W07, W11), keine Rechtsgrundlage neu. Abnahmefall: tests/integration/test_ab07_outputs.py.
