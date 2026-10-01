# Umsetzungsstand der Prioritätenliste, Stand 1.61.0 (01.10.2026)

Kompakte Übersicht zu den Punkten 1 bis 28 der Prioritätenliste des Betreibers vom 01.10.2026 (Welle 16, Pakete AE01 bis AE40). Quellen: Ergebnisdateien der Pakete, Prüfbericht [REVIEW-W16-2026-10-01](../reviews/REVIEW-W16-2026-10-01.md), Versionsverlauf 1.61.0 in `CHANGELOG.md`. Die Freigabestufen G1 bis G5 bleiben geschlossen, kein Paket öffnet eine Stufe. Technisch vorbereitet heißt nicht fachlich abgenommen, die offenen Entscheidungen liegen beim Betreiber und bei der Rechts- und Steuerberatung.

Statuslogik: "umgesetzt" bedeutet, dass die Ergebnisdatei des Pakets alle Befunde des Punktes als erledigt führt (ohne Befundliste: keine Teilpunkte offen). "teilweise" bedeutet, dass mindestens ein Befund oder Teilpunkt als teilweise geführt wird. "offen" bedeutet, dass nichts umgesetzt ist. Die Spalte "Offene Entscheidung" nennt die Fragen in `docs/OPEN_QUESTIONS.md`, die den Punkt weiter betreffen.

## Übersicht

- Migrationen 0357 bis 0394: 38 Nummern, davon 33 real (0357 bis 0359, 0361 bis 0369, 0371 bis 0374, 0376 bis 0379, 0381 bis 0384, 0386 bis 0394) und 5 Platzhalter ohne Schemaänderung (0360 AE04, 0370 AE14, 0375 AE19, 0380 AE24, 0385 AE29). Die Kette endet bei 0394.
- Neue offene Entscheidungen (38): AE01-01, AE07-01, AE21-01, AE22-01, AE22-02, AE23-01 bis AE23-05, AE25-01, AE26-01 bis AE26-03, AE27-01 bis AE27-03, AE28-01 bis AE28-03, AE29-01, AE30-01, AE30-02, AE31-01, AE32-01, AE33-01 bis AE33-03, AE34-01 bis AE34-03, AE35-01, AE35-02, AE36-01, AE36-02, AE37-01, AE38-01, AE38-02.
- Prüfbericht AE40: drei Befunde behoben (AE40-1 Demo-Mandant und Freigabestufe, AE40-2 Vier Augen der Textbausteine, AE40-3 Löschen eines Zinsbuchungsentwurfs mit Steuerabzügen), sechs weitere Punkte dokumentiert (AE40-01 bis AE40-06, davon AE40-02 nach dem Bericht umgesetzt: der Nummernmodus für Mietrechnungsentwürfe verlangt tenant_settings:update).
- Zählung der 28 Punkte: 9 umgesetzt, 19 teilweise, 0 offen.

## Punkte 1 bis 28

| Punkt | Gegenstand | Paket | Status | Offene Entscheidung | Regeldatei | Offener Rest |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | V16 fachkundige Person und Abnahme | AE01 | teilweise | V16, AE01-01 | [AE01-ACCEPTANCE](../rules/AE01-ACCEPTANCE.md) | Benennung der Person bleibt beim Betreiber; das Register speist g1_acceptance nicht automatisch |
| 2 | M10-01, SA-08, P07-04, P07-05 Kontenrahmen-Freigabe, Mehrschlüssel, Abrechnungsarten | AE02 | teilweise | M10-01, P07-04, P07-05 | [M10-01-kontenrahmen-vorlage](../rules/M10-01-kontenrahmen-vorlage.md) | Für special_levy fehlt in Anhang A.1 ein Konto, Festlegung durch die Steuerberatung |
| 3 | M12-09, BK2-03 G1-Öffnungsliste und Automatikschalter | AE03 | teilweise | M12-09, BK2-03 | [M12-09-g1-oeffnung-automatikschalter](../rules/M12-09-g1-oeffnung-automatikschalter.md) | PUT /banking/automation schaltet per API weiter ohne G1 und Vier Augen |
| 4 | AC03-01 Rechnungsnummern bei Entwürfen | AE04 | teilweise | AC03-01 | [AC03-01](../rules/AC03-01.md) | recurring-invoices/generate (Eingangsrechnungsentwürfe ohne Gate) unverändert |
| 5 | P01-01 KapESt und Soli auf Habenzinsen | AE05 | umgesetzt | P01-01 | [P01-01-zinsabzuege](../rules/P01-01-zinsabzuege.md) | Steuerliche Behandlung und Steuerkonten offen (Steuerberater); nur Entwurf |
| 6 | AC01-02 Nebenbuch ausgebuchte Posten | AE06 | umgesetzt | AC01-02 | [AC01-02](../rules/AC01-02.md) | Standardvariante (ausblenden, getrennt zählen) fachlich zu bestätigen |
| 7 | M24-01, V01-01 reserve_plan als Entität | AE07 | teilweise | V01-01, AE07-01 | [AE07-01-ruecklagenplan](../rules/AE07-01-ruecklagenplan.md) | Ist je Rücklage bleibt Gesamtwert der Abrechnung; steuerliche Einordnung nur Platzhalter; Anfangsbestand Standard gesperrt |
| 8 | P07-02 Zahlungen je Zweckrücklage | AE08 | umgesetzt | P07-02, P07-04 | [AE08-01](../rules/AE08-01.md) | Mehrere Rücklagenvorschüsse einer Einheit brauchen je Rücklage eine eigene Zahlungsart; Aufteilung nach Planverhältnis nur Vorschlag |
| 9 | M24-08, P07-01, M12-L2 unterjährige Planänderung | AE09 | teilweise | M12-L2, P07-01 | [AE09-01](../rules/AE09-01.md) | Buchung freigegebener Differenzen nicht umgesetzt (Folgeschritt hinter G1) |
| 10 | AA07-01, P01 Erwerbsart-Regel | AE10 | teilweise | AA07-01, P01 | [AE10-acquisition-rule](../rules/AE10-acquisition-rule.md) | Regel bisher nur beim Schuldnervorschlag der Sonderumlagen-Differenz angewendet; Rechtsfrage offen |
| 11 | P02 Heizkostenüberleitung und Beschlusskorrektur (D09) | AE11 | teilweise | P02 | [P02-korrekturbericht](../rules/P02-korrekturbericht.md) | Rechtsfolge der Korrektur offen; Mandantenschalter correction_report_enabled nicht gebaut (reine Anzeige) |
| 12 | AA06-02, GA07-01 Übergangsregel virtuelle Versammlung | AE12 | teilweise | AA06-02, AD06-01 | [M25-03-einladung-virtuell](../rules/M25-03-einladung-virtuell.md) | Rechtliche Prüfung offen; der Stichtag hat weder Rechtswirkung noch Sperre |
| 13 | P13-01 Eigentümerportal: Anteil Wirtschaftsplan, Sonderumlage, Mieterträge | AE13 | umgesetzt | P13-01, Q10-01, Q10-02 | [M21-06](../rules/M21-06.md) | Datenschutzfreigabe der Mieterträge offen; Schalter Mieterträge Standard aus |
| 14 | P03-03 Beschluss- und Budgetbezug der Rechnungen | AE14 | teilweise | P03-03 | [PU02-sachliche-pruefung](../rules/PU02-sachliche-pruefung.md) | Preis- und Mengenabgleich fehlt, weil Aufträge keine Positionen führen; nur Hinweise, keine Freigabe |
| 15 | AC10-01, M17-03, P06-01 Vorschussregel D24 | AE15 | teilweise | AC10-01, M17-03, P06-01 | [AC10-d24](../rules/AC10-d24.md) | Standard nur Information; strikter xfail D24 bleibt für den Standard, Variantenwahl durch Rechtsberatung und Betreiber |
| 16 | AA11-01, AA11-02 Texte Informationsblatt, Anschreiben, § 35a | AE16 | teilweise | AA11-01, AA11-02 | [AE16-01](../rules/AE16-01.md) | Wortlaut liefern Rechtsanwalt und Steuerberater; Baustein im Mieteranschreiben und Schalter require_second_person nicht umgesetzt |
| 17 | M17-01 Umlagefähigkeit je Position | AE17 | umgesetzt | M17-01 | [AE17-01](../rules/AE17-01.md) | Sperre bei fehlenden Umlagegrundlagen Standard an (Hinweis für den Betrieb); Anschreiben-Entwurf bewusst nicht gesperrt |
| 18 | M17-04 Frist § 556 Abs. 3 BGB | AE18 | umgesetzt | M17-04 | [M17-04-abrechnungsfrist](../rules/M17-04-abrechnungsfrist.md) | Ausnahmegründe rechtlich offen; Fristende nur Orientierung, zu verifizieren |
| 19 | AB10-01, M17-02 Heizkosten: Prüfpunkte und Berechnung | AE19 | umgesetzt | AB10-01, M17-02 | [AB10-01-pruefpunkte](../rules/AB10-01-pruefpunkte.md), [M17-02-heizkosten](../rules/M17-02-heizkosten.md) | Prüfpunkte ohne Befüllung wirkungslos; Bestätigung im CRM nicht angeboten; Abweichungsbericht nur als CSV |
| 20 | P06-02 Periodensperre je Abrechnung | AE20 | teilweise | P06-02, AA08-01 | [P06-02-periodensperre-objekt](../rules/P06-02-periodensperre-objekt.md) | WEG-Hausgeldabrechnung setzt beim Abschluss keine Objektsperre; Objektbestimmung nach AE21 auf die Spalte journal_line.property_id umzustellen |
| 21 | Q15-01 Objektspalte journal_line | AE21 | umgesetzt | Q15-01, AE21-01 | [Q15-01-objektspalte](../rules/Q15-01-objektspalte.md) | Ableitung aus dem Buchungskreis offen; keine CRM-Oberfläche für Driftbericht und Objektfilter |
| 22 | P04-04, Q01-01 Guthaben als Verbindlichkeitsposten | AE22 | teilweise | AE22-01, AE22-02 | [AE22-credit-payables](../rules/AE22-credit-payables.md) | WEG-Guthaben (G4) nicht angebunden; ein nicht ausgeführter Zahlungsauftrag wird beim allgemeinen Storno nicht gesperrt |
| 23 | M11-01 EBICS, M11-02 GoCardless, FinTS-Hinweise | AE23, AE24 (gestoppt), AE26 | teilweise | AE23-01 bis AE23-05, AE26-02, AE26-03, M11-02 GoCardless | [M11-11-ebics-connector](../rules/M11-11-ebics-connector.md), [M11-07-fints-pin-tan](../rules/M11-07-fints-pin-tan.md) | EBICS nur Gerüst ohne Übertragung (MHVP-BANK-0050); GoCardless offen (siehe Vom Betreiber gestoppt); FinTS-Hinweise umgesetzt |
| 24 | S13-03 ZUGFeRD, AC11-01 KoSIT | AE25, AE26 | teilweise | AE25-01, AE26-01 | [S13-03-zugferd](../rules/S13-03-zugferd.md), [M13-04](../rules/M13-04.md) | PDF/A-3 Konformität nicht nachgewiesen (Schriften im Briefbogen nicht eingebettet); KoSIT-Prüfsummen eigene Berechnung, Betreiberentscheidung offen |
| 25 | M2-04 TOTP, M7-06 und SA-04 Portal-Chat, M21-04 Rechtstexte, AA14-01 und AA14-02, AD06-01 bis AD06-03 | AE27, AE28, AE29, AE30, AE31 | teilweise | AE27-01 bis AE27-03, AE28-01 bis AE28-03, AE29-01, AE30-01, AE30-02, AE31-01 | [M2-04](../rules/M2-04.md), [AE28-01](../rules/AE28-01.md), [AE29-01](../rules/AE29-01.md), [AE30-01](../rules/AE30-01.md), [AE31-online-stimmen-vollmacht](../rules/AE31-online-stimmen-vollmacht.md) | Zweitfaktor Standard freiwillig (Pflicht als Mandantenwahl); QR-Bild in der Einladungs-E-Mail nicht umgesetzt; Logo und Texte für Fremdmandanten (R10-04) mit G5; AD06-01 bis AD06-03 rechtlich offen |
| 26 | S711-10 Verzeichnis, AC07-01 und AC07-03, AC06-01 bis AC06-03 | AE32, AE33, AE34 | umgesetzt | AE32-01, AE33-01 bis AE33-03, AE34-01 bis AE34-03 | [S711-10](../rules/S711-10.md), [AE33-papierkorb-auskunft](../rules/AE33-papierkorb-auskunft.md), [AE34-01](../rules/AE34-01.md) | Papierkorb Standard aus; CRM-Pflegemaske für Rechtsgrundlage und Widerspruch fehlt (Pflege über Fachliche Regeln und API) |
| 27 | GB16-02 Verfügbarkeit, AC09-01, AA15-01, AD10-02 | AE35, AE36 | teilweise | AE35-01, AE35-02, AE36-01, AE36-02 | [PL-AVAIL-01](../rules/PL-AVAIL-01.md), [AE36-SCALE](../rules/AE36-SCALE.md), [AE36-DEMO](../rules/AE36-DEMO.md) | Keine Partitionierung (bewusst, nur Auslöser und Alarm); Hinweisband Demo-Mandant in der CRM-Kopfzeile fehlt; Zählweise der Wartungsfenster offen |
| 28 | Q08-01 Importe, AA16-03 Dossiers, M20-04 Webhook-Quelle | AE37, AE38 | teilweise | AE37-01, AE38-01, AE38-02 | [Q08-01-spaltenerkennung](../rules/Q08-01-spaltenerkennung.md), [M20-04-inbound](../rules/M20-04-inbound.md) | Wertzuordnungen und Abgleich der Einzelposten brauchen echte Exporte; Anhang-B-Läufe nur durch den Betreiber; keine CRM-Oberfläche für Mailquellen |

## Querschnitt

| Paket | Inhalt | Ergebnis |
| --- | --- | --- |
| AE39 | Zentrale CRM-Seite Fachliche Regeln (`/einstellungen/fachliche-regeln`) mit 54 Einträgen in 7 Bereichen, davon 46 änderbar, Hinweis Entscheidung offen mit Nummer der Frage; Suche, Assistent und Handbuch ergänzt | umgesetzt; GoCardless, Plattformschalter AE35 und AE36 nicht aufgenommen |
| AE40 | Sicherheits- und Geldflussprüfung der Welle 16 ([Bericht](../reviews/REVIEW-W16-2026-10-01.md)) | drei Befunde behoben, sechs Punkte dokumentiert; nicht ausgeführt: Gesamtsuite, Frontendtests und Playwright (Vorgabe Welle 16) |

## Vom Betreiber gestoppt

### AE24 GoCardless (Punkt 23, M11-02)

- Der Betreiber hat das Paket AE24 (GoCardless-Konnektor, Bank Account Data API) gestoppt. Der Teilstand ist aus dem Baum entfernt, das Paket wird ohne ausdrückliche Weisung des Betreibers nicht neu gestartet.
- Entfernt: `gocardless.py`, `gocardless_models.py`, `gocardless_routers.py`, `gocardless_tasks.py` in `apps/api/src/mhvp/banking/`, der Test `test_gocardless_client.py` sowie die GoCardless-Anteile in `main.py`, `worker.py`, `models.py`, `core/config.py`, `core/problems.py` (Codes MHVP-BANK-0040 bis 0048), `banking/routers.py` und `banking/tasks.py`. `banking/account_selection.py` enthielt nur GoCardless-Änderungen und steht wieder auf dem Stand vor Welle 16.
- Migration 0380 bleibt als Platzhalter ohne Schemaänderung bestehen, weil 0381 auf sie verweist. Es gibt keine GoCardless-Tabellen.
- Unverändert geblieben: die Erkennung von GoCardless-Verbindungen im Datenschutzregister über `bank_connection` (AE32) und die Vorkommen aus dem Stand vor Welle 16. In `docs/OPEN_QUESTIONS.md` gibt es keine Zeilen zu AE24.
- Punkt 23: M11-02 GoCardless bleibt offen. EBICS (AE23, Gerüst) und die FinTS-Hinweise (AE26) sind unabhängig davon umgesetzt.
- Geprüft nach dem Rückbau: ruff, mypy (banking, privacy), Import von main, worker und models, Unit-Teilmenge (108 bestanden) und Vitest der BFF-Allowlist (209 bestanden). Nicht ausgeführt: volle pytest-Suite, Integrationstests, `make e2e`, `make openapi`.
