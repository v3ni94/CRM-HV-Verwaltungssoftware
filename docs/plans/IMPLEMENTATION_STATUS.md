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


## Welle 17 (Stand 1.62.0, 02.10.2026)

Befunde der Lückenanalyse GAA bis GAF, Pakete AF01 bis AF24 und Prüfung AF25. Quellen: Ergebnisdateien der Pakete (Feld findings), Regeln unter `docs/rules/`, Versionsverlauf 1.62.0 in `CHANGELOG.md`. Die Freigabestufen G1 bis G5 bleiben geschlossen. Status wie in den Ergebnisdateien: done, partial, not_done.

- Migrationen 0395 bis 0418: 24 Nummern, davon 5 real (0398 Periodensperre Quelle hoa_statement, 0402 Stimm-Eindeutigkeit, 0409 Eigentümerabrechnung Portal, 0410 Mieterabrechnung Portal, 0411 Portal-Assistent asynchron) und 19 Platzhalter ohne Schemaänderung (0395, 0396, 0397, 0399, 0400, 0401, 0403, 0404, 0405, 0406, 0407, 0408, 0412, 0413, 0414, 0415, 0416, 0417, 0418). Die Kette endet bei 0418.
- Neue offene Entscheidungen (9): AF01-01, AF02-01, AF06-01, AF06-02, AF07-01, AF08-01, AF10-01, AF15-01, AF16-01.
- Zählung: 95 Befunde in 25 Paketen, davon 74 done, 18 partial, 3 not_done. 20 Befunde der Analyse (insgesamt 110) sind keinem Paket der Welle 17 zugeordnet. Die Zeilen AF25 sind Prüfbefunde (done = behoben, not_done = dokumentiert, Entscheidung beim Betreiber) und zählen mit.

| Befund-ID | Paket | Status | Regel oder Report | Hinweis |
| --- | --- | --- | --- | --- |
| AF25-01 | AF25 | not_done | [REVIEW-W17-2026-10-02](../reviews/REVIEW-W17-2026-10-02.md) | niedrig: Ausgangsautomatik ohne Vier-Augen-Antrag (AF01-01, G1) (apps/api/src/mhvp/banking/routers.py) |
| AF25-02 | AF25 | not_done | [REVIEW-W17-2026-10-02](../reviews/REVIEW-W17-2026-10-02.md) | niedrig: Eigentuemerabrechnung mit Rechtstraeger = Gemeinschaft fuer alle Eigentuemer sichtbar, Entscheidung offen (apps/api/src/mhvp/portal/owner_reports.py) |
| AF25-03 | AF25 | not_done | [REVIEW-W17-2026-10-02](../reviews/REVIEW-W17-2026-10-02.md) | hinweis: Keine Pfadinjektion, nur Betreiberumgebung (apps/api/src/mhvp/documents/pdf_fonts.py) |
| AF25-1 | AF25 | done | [REVIEW-W17-2026-10-02](../reviews/REVIEW-W17-2026-10-02.md) | mittel: Downgrade DELETE unter FORCE RLS wirkungslos, CheckViolation; jetzt NO FORCE/FORCE und UPDATE auf failed statt Loeschen (apps/api/alembic/versions/0411_af17_portal_assistant_async.py) |
| AF25-2 | AF25 | done | [REVIEW-W17-2026-10-02](../reviews/REVIEW-W17-2026-10-02.md) | niedrig: Objektnummer 1601 verletzt Schema, Test rot (apps/api/tests/integration/test_af16_portal_tenant_statement.py) |
| GAA-01 | AF01 | done | Ergebnisdatei AF01 |  |
| GAA-02 | AF08 | done | [P08-pruefung-einsicht](../rules/P08-pruefung-einsicht.md), [AE31-online-stimmen-vollmacht](../rules/AE31-online-stimmen-vollmacht.md), [P02-korrekturbericht](../rules/P02-korrekturbericht.md) |  |
| GAA-03 | AF06 | done | Ergebnisdatei AF06 |  |
| GAA-05 | AF07 | partial | [PU02-sachliche-pruefung](../rules/PU02-sachliche-pruefung.md), [M3-02-sepa-mandate](../rules/M3-02-sepa-mandate.md) | Lauf schließt B2B nur als Kandidat mit Sperrgrund aus (kein eigener 409-Code); contracts /sepa-mandates check_b2b (fremde Domain) unverändert |
| GAA-06 | AF06 | done | Ergebnisdatei AF06 |  |
| GAA-07 | AF22 | done | [GAC-04](../rules/GAC-04.md) |  |
| GAB-02 | AF02 | done | [M11-11-ebics-connector](../rules/M11-11-ebics-connector.md), [M11-07-fints-pin-tan](../rules/M11-07-fints-pin-tan.md) |  |
| GAB-03 | AF02 | done | [M11-11-ebics-connector](../rules/M11-11-ebics-connector.md), [M11-07-fints-pin-tan](../rules/M11-07-fints-pin-tan.md) |  |
| GAB-04 | AF10 | done | [AF10-01](../rules/AF10-01.md) |  |
| GAB-05 | AF21 | done | [AF21-01](../rules/AF21-01.md) |  |
| GAB-06 | AF11 | done | Ergebnisdatei AF11 |  |
| GAB-07 | AF10 | done | [AF10-01](../rules/AF10-01.md) |  |
| GAB-08 | AF01 | done | Ergebnisdatei AF01 |  |
| GAB-11 | AF10 | done | [AF10-01](../rules/AF10-01.md) |  |
| GAB-13 | AF23 | done | Ergebnisdatei AF23 |  |
| GAB-14 | AF21 | done | [AF21-01](../rules/AF21-01.md) |  |
| GAB-16 | AF21 | done | [AF21-01](../rules/AF21-01.md) |  |
| GAC-01 | AF15 | done | [AF15-01](../rules/AF15-01.md) |  |
| GAC-02 | AF16 | partial | [AF16-01](../rules/AF16-01.md) | Integrationstest geschrieben, aber nicht ausgeführt (Migrationskette lückenhaft, 0399 fehlte) Nach FIX-AF16 lief der Integrationstest (1 bestanden), Status bleibt wie in der Ergebnisdatei. |
| GAC-03 | AF15 | done | [AF15-01](../rules/AF15-01.md) |  |
| GAC-04 | AF22 | done | [GAC-04](../rules/GAC-04.md) |  |
| GAC-06 | AF01 | done | Ergebnisdatei AF01 |  |
| GAC-08 | AF21 | done | [AF21-01](../rules/AF21-01.md) |  |
| GAD-02 | AF22 | done | [GAC-04](../rules/GAC-04.md) |  |
| GAE-01 | AF04 | done | [P06-02-periodensperre-objekt](../rules/P06-02-periodensperre-objekt.md), [AE22-credit-payables](../rules/AE22-credit-payables.md) |  |
| GAE-02 | AF04 | partial | [P06-02-periodensperre-objekt](../rules/P06-02-periodensperre-objekt.md), [AE22-credit-payables](../rules/AE22-credit-payables.md) | Banking-Verifier (Zahlungsabgleich) nicht um Objektsperre erweitert (Domäne banking, nicht im Paket); admin_fee-Vorabprüfung ohne eigenen Integrationstest |
| GAE-03 | AF04 | done | [P06-02-periodensperre-objekt](../rules/P06-02-periodensperre-objekt.md), [AE22-credit-payables](../rules/AE22-credit-payables.md) |  |
| GAE-04 | AF05 | done | Ergebnisdatei AF05 |  |
| GAE-05 | AF04 | done | [P06-02-periodensperre-objekt](../rules/P06-02-periodensperre-objekt.md), [AE22-credit-payables](../rules/AE22-credit-payables.md) |  |
| GAE-06 | AF04 | partial | [P06-02-periodensperre-objekt](../rules/P06-02-periodensperre-objekt.md), [AE22-credit-payables](../rules/AE22-credit-payables.md) | Kautionsabrechnung reclass nicht als Gesamtablauf getestet (freigegebene DepositSettlement-Fixture aufwendig), nur Eigentümerabrechnung |
| GAE-07 | AF04 | done | [P06-02-periodensperre-objekt](../rules/P06-02-periodensperre-objekt.md), [AE22-credit-payables](../rules/AE22-credit-payables.md) |  |
| GAE-08 | AF04 | done | [P06-02-periodensperre-objekt](../rules/P06-02-periodensperre-objekt.md), [AE22-credit-payables](../rules/AE22-credit-payables.md) |  |
| GAE-09 | AF06 | done | Ergebnisdatei AF06 |  |
| GAE-10 | AF04 | done | [P06-02-periodensperre-objekt](../rules/P06-02-periodensperre-objekt.md), [AE22-credit-payables](../rules/AE22-credit-payables.md) |  |
| GAE-11 | AF08 | partial | [P08-pruefung-einsicht](../rules/P08-pruefung-einsicht.md), [AE31-online-stimmen-vollmacht](../rules/AE31-online-stimmen-vollmacht.md), [P02-korrekturbericht](../rules/P02-korrekturbericht.md) | Jahresabrechnung mit gebundener Zahlung (contributions_paid_by_reserve im Snapshot) nicht Ende zu Ende getestet, braucht Bank- und Buchungsaufbau |
| GAE-12 | AF08 | partial | [P08-pruefung-einsicht](../rules/P08-pruefung-einsicht.md), [AE31-online-stimmen-vollmacht](../rules/AE31-online-stimmen-vollmacht.md), [P02-korrekturbericht](../rules/P02-korrekturbericht.md) | Planuebernahme nicht an den Hook calc.allocation_owner angebunden (Zuordnung des Abrechnungsergebnisses W07/P01 offen) |
| GAE-13 | AF08 | done | [P08-pruefung-einsicht](../rules/P08-pruefung-einsicht.md), [AE31-online-stimmen-vollmacht](../rules/AE31-online-stimmen-vollmacht.md), [P02-korrekturbericht](../rules/P02-korrekturbericht.md) |  |
| GAE-14 | AF08 | done | [P08-pruefung-einsicht](../rules/P08-pruefung-einsicht.md), [AE31-online-stimmen-vollmacht](../rules/AE31-online-stimmen-vollmacht.md), [P02-korrekturbericht](../rules/P02-korrekturbericht.md) |  |
| GAE-15 | AF15 | done | [AF15-01](../rules/AF15-01.md) |  |
| GAE-16 | AF12 | done | [AE16-01](../rules/AE16-01.md) |  |
| GAE-17 | AF12 | done | [AE16-01](../rules/AE16-01.md) |  |
| GAE-18 | AF12 | done | [AE16-01](../rules/AE16-01.md) |  |
| GAE-19 | AF14 | done | Ergebnisdatei AF14 |  |
| GAE-20 | AF14 | partial | Ergebnisdatei AF14 | Integrationstest test_af14_deadline_snapshot.py geschrieben und mit ruff geprüft, wegen unvollständiger Migrationskette und Fremdfehler im Arbeitsbaum (doppelter Fehlercode MHVP-BANK-0057, alembic upgrade lief unter Last nicht durch) nicht ausgeführt |
| GAE-21 | AF07 | done | [PU02-sachliche-pruefung](../rules/PU02-sachliche-pruefung.md), [M3-02-sepa-mandate](../rules/M3-02-sepa-mandate.md) |  |
| GAE-22 | AF07 | partial | [PU02-sachliche-pruefung](../rules/PU02-sachliche-pruefung.md), [M3-02-sepa-mandate](../rules/M3-02-sepa-mandate.md) | Integrationstest nicht ausgeführt (Migrationskette unvollständig) |
| GAE-23 | AF02 | done | [M11-11-ebics-connector](../rules/M11-11-ebics-connector.md), [M11-07-fints-pin-tan](../rules/M11-07-fints-pin-tan.md) |  |
| GAE-25 | AF02 | done | [M11-11-ebics-connector](../rules/M11-11-ebics-connector.md), [M11-07-fints-pin-tan](../rules/M11-07-fints-pin-tan.md) |  |
| GAE-26 | AF19 | done | Ergebnisdatei AF19 |  |
| GAE-27 | AF19 | done | Ergebnisdatei AF19 |  |
| GAE-28 | AF15 | done | [AF15-01](../rules/AF15-01.md) |  |
| GAE-29 | AF17 | done | [AE28-01](../rules/AE28-01.md) |  |
| GAE-30 | AF19 | done | Ergebnisdatei AF19 |  |
| GAE-31 | AF19 | partial | Ergebnisdatei AF19 | DemoBanner in Kopfzeile eingebaut, liest is_demo aus /auth/me; die API liefert das Feld an Mandantenbenutzer noch nicht |
| GAE-33 | AF24 | done | Ergebnisdatei AF24 |  |
| GAE-34 | AF22 | done | [GAC-04](../rules/GAC-04.md) |  |
| GAE-35 | AF10 | done | [AF10-01](../rules/AF10-01.md) |  |
| GAE-36 | AF24 | done | Ergebnisdatei AF24 |  |
| GAE-37 | AF13 | done | [S13-03-zugferd](../rules/S13-03-zugferd.md) |  |
| GAE-38 | AF24 | done | Ergebnisdatei AF24 |  |
| GAF-01 | AF18 | done | Ergebnisdatei AF18 |  |
| GAF-02 | AF03 | partial | Ergebnisdatei AF03 | Erzeugen, Download, Einreichung, bank-status und payment-bank-config PUT ohne UI/BFF (G2, Entscheidung M15-01 offen) |
| GAF-03 | AF03 | done | Ergebnisdatei AF03 |  |
| GAF-04 | AF03 | done | Ergebnisdatei AF03 |  |
| GAF-05 | AF05 | done | Ergebnisdatei AF05 |  |
| GAF-06 | AF05 | done | Ergebnisdatei AF05 |  |
| GAF-07 | AF05 | done | Ergebnisdatei AF05 |  |
| GAF-08 | AF06 | done | Ergebnisdatei AF06 |  |
| GAF-09 | AF06 | done | Ergebnisdatei AF06 |  |
| GAF-10 | AF01 | partial | Ergebnisdatei AF01 | kein eigener Vier-Augen-Antrag fuer die Ausgangsautomatik (Entscheidung M12-05 offen, AF01-01); Ausgangsschalter wirkt nur bei eingeschalteter Hauptautomatik |
| GAF-12 | AF14 | done | Ergebnisdatei AF14 |  |
| GAF-13 | AF14 | partial | Ergebnisdatei AF14 | Belegeinsicht (StatementInspectionsPanel) und Ergebnisbuchungen (ResultEntriesPanel, nur Status fällig, G3 per API) in StatementWorkbench; period-lock, heating/consumption-info und co2-split nicht ergänzt (consumption-info und co2-split haben bereits Panels bzw. Heizungstext, period-lock ohne UI) |
| GAF-14 | AF18 | partial | Ergebnisdatei AF18 | Pflichtdokumente CRUD und lokales Modell (Status, Vorschlag je Prüffall) in Einstellungen Objektakte; Importlauf, ocr-cache, previews/import ohne Maske |
| GAF-15 | AF09 | done | Ergebnisdatei AF09 |  |
| GAF-16 | AF09 | partial | Ergebnisdatei AF09 | Mehrheitsprüfung und new-version-Aufrufer nicht neu angefasst (Mehrheitsprüfung besteht als MajorityCheckLine) |
| GAF-17 | AF20 | done | Ergebnisdatei AF20 |  |
| GAF-18 | AF20 | partial | Ergebnisdatei AF20 | U-Protokoll Import (Vorschau/Übernahme, JSON-Ausgabe) und Mängel zu Tickets umgesetzt; Datei-Zuordnung imports/uprotokoll/files ohne UI (nur BFF) |
| GAF-19 | AF17 | done | [AE28-01](../rules/AE28-01.md) |  |
| GAF-20 | AF19 | done | Ergebnisdatei AF19 |  |
| GAF-21 | AF19 | done | Ergebnisdatei AF19 |  |
| GAF-22 | AF17 | done | [AE28-01](../rules/AE28-01.md) |  |
| GAF-23 | AF18 | partial | Ergebnisdatei AF18 | Abnahme je Objekt (Anlegen, Unterzeichnen), Journalspalten, Jahresausgaben in /importe/migration; Abnahme bearbeiten (PUT), vollimport/exporttypen, history/open-items ohne Maske |
| GAF-24 | AF20 | done | Ergebnisdatei AF20 |  |
| GAF-25 | AF20 | done | Ergebnisdatei AF20 |  |
| GAF-26 | AF20 | done | Ergebnisdatei AF20 |  |
| GAF-27 | AF05 | done | Ergebnisdatei AF05 |  |
| GAF-28 | AF20 | done | Ergebnisdatei AF20 |  |
| GAF-30 | AF23 | partial | Ergebnisdatei AF23 | 17 CRM-Komponenten (banking 4, accounting 4, hoa 4, ai 3, documents 2) getestet; übrige banking/accounting/properties/hoa ohne Test |
| GAF-31 | AF23 | partial | Ergebnisdatei AF23 | 8 Portal-Komponenten getestet; OnlineMeetingPanel, WorkOrderDetail, DataChangeForm, InvitationForm und Seiten ohne Einzeltest |
| GAF-33 | AF15 | done | [AF15-01](../rules/AF15-01.md) |  |
