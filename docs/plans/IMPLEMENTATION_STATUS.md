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

## Welle 18 (Stand 1.63.0, 02.10.2026)

Befunde der Lückenanalyse GAA bis GAF und Rückstände aus Welle 17, Pakete AG01 bis AG20. Quellen: Ergebnisdateien der Pakete (Feld findings), Versionsverlauf 1.63.0 in `CHANGELOG.md`. Die Freigabestufen G1 bis G5 bleiben geschlossen. Status wie in den Ergebnisdateien: done, partial, not_done.

- Migrationen 0419 bis 0438: 20 Nummern, davon 8 real (0420 ledger_leading_switch, 0422 ai_provider_config Stapel, 0424 work_order_rating, 0425 Umlaufbeschluss im Portal, 0427 Belegeinsicht Eigentümer, 0430 Abrechnungen der Gemeinschaft im Portal, 0437 Ziel des Automatikantrags, 0438 Zuordnungsvorschlag) und 12 Platzhalter ohne Schemaänderung (0419, 0421, 0423, 0426, 0428, 0429, 0431, 0432, 0433, 0434, 0435, 0436).
- Korrektur in Migration 0424: Der Name der Check-Constraint wird aus dem Katalog gelesen, weil die Namenskonvention den Namen verdoppelte und das Upgrade auf frischer Datenbank scheiterte.
- Neue offene Entscheidungen: AG02-01, AG04-01, AG07-01, AG09-01, AG14-01, AG18-01 bis AG18-04, AG20-01, GAC-07; fortgeschrieben AF25-02 (AG12) und AF01-01 (AG19, fachliche Freigabe M12-05).
- Zählung: 41 Befunde in 20 Paketen, davon 30 done, 11 partial, 0 not_done. Die partial-Befunde GAA-04, GAB-12, GAB-15 und GAB-17 sind Entscheidungsfragen und stehen unter Bewusst nicht umgesetzt (Abschnitt unten, kein zweites Verzeichnis).
- Vom Koordinator bei der Integration erledigt: OpenAPI-Export und api-client neu erzeugt, `test_migrations.py` über die Kette 0419 bis 0438 grün (Auf- und Rückweg bis 0418 geprüft), `test_af14_deadline_snapshot.py` (GAE-20) grün, Gesamtsuiten API (4.711 bestanden), CRM und Portal, Playwright Kernpfade beider Apps (GAE-39) und Messlauf MHVP_PERF=1 (GAE-32, docs/runbooks/leistungsmessung.md) ausgeführt. Einmal rot im Shard und isoliert grün: `test_m20_gmail_state_sync.py::test_reconcile_after_expired_history_and_preview` (Mail-Domäne in Welle 18 unverändert, reihenfolgeabhängig).

| Befund-ID | Paket | Status | Hinweis |
| --- | --- | --- | --- |
| GAD-01 | AG01 | done |  |
| GAC-05 | AG02 | done | AG02-01 offen (Bank-Autobuchung, A17); Zahllauf prüft Stichtag des Laufs, nicht Fälligkeit je Rechnung |
| GAC-07 | AG03 | partial | Schalter und Rechte vorhanden, Fachendpunkte prüfen insurance:read und claims:read nicht (kein Router), Umfang offen |
| GAF-11 | AG03 | done |  |
| GAB-09 | AG04 | done | AG04-01 offen (AVV, Preisfaktor) |
| GAB-10 | AG04 | done | OpenAI Batch API bewusst nachgelagert |
| GAE-24 | AG05 | done | Abnahme am Testsystem der Bank bleibt Betreiberaufgabe |
| GAF-35 | AG06 | done | AE30-02 bleibt offen, Datenschutzprüfung vor Modus all |
| GAF-32 | AG07 | done | AG07-01 offen; Vollmachten im Portal-Umlauf nicht angenommen |
| GAF-34 | AG08 | done | P13-01 offen; nicht umlagefähige Kosten nicht im Snapshot, Leerstandsanteil nur je Objekt |
| GAF-36 | AG09 | done | AG09-01 offen; Quelle hoa_cost_item.document_id |
| GAE-02 | AG10 | done |  |
| GAE-20 | AG10 | done | Test test_af14_deadline_snapshot.py nach Behebung der Migration 0424 vom Koordinator ausgeführt (grün); Hinweis am reinen Buchungsvorschlag nicht umgesetzt |
| GAF-13 | AG10 | done |  |
| AF03-R | AG11 | partial | payment-batches und payment-bank-config ohne Maske (G2, M15-01 offen) |
| AF05-R | AG11 | done | Anzeige der ersten Freigabe fehlt im Rechnungsmodell (fremde Domain) |
| AF07-R | AG11 | partial | B2B-Lauf nur als Kandidat mit Sperrgrund, kein eigener 409-Code (G2, AF07-01) |
| AF15-R | AG12 | done | Abrufvermerk für Eigentümerabrechnungs-PDF nicht ergänzt |
| AF25-02 | AG12 | done | Entscheidung offen (Betreiber, G3) |
| AF18-D | AG13 | done |  |
| AF19-R | AG13 | done |  |
| AF22-D | AG13 | done | Portal-Kapitel nur abgegrenzt |
| GAF-17 | AG14 | done |  |
| GAF-18 | AG14 | partial | Liste und Lösen nicht umsetzbar, API bietet nur das Zuordnen (AG14-01) |
| GAF-24 | AG14 | done | Belegdaten als gemeinsame JSON-Vorlage, kein Mapping je Datensatz (AG14-01) |
| AF21-R | AG15 | done | Angleichung banking/ai_posting.py optional |
| GAF-14 | AG16 | partial | OCR-Cache leeren ohne API-Endpunkt, Verlauf der Importläufe nur per Lauf-ID |
| GAF-23 | AG16 | done |  |
| AF23-R | AG17 | done | Unter Last einzelne userEvent-Tests über 5 s, mit --testTimeout=30000 grün |
| AF08-R | AG18 | partial | Job-Schlüssel registriert; GAE-11 und GAE-12 laut AG20 umgesetzt |
| AF24-R | AG18 | done |  |
| GAA-04 | AG18 | partial | Sonderumlagekonto, Entscheidung AG18-01 (Steuerberatung) |
| GAB-12 | AG18 | partial | DMS als Primärspeicher, Entscheidung AG18-02 |
| GAB-15 | AG18 | partial | Lokale Einbettung, Entscheidung AG18-03 |
| GAB-17 | AG18 | partial | GoCardless gestoppt, Aggregator laut V3 finAPI, AG18-04 |
| GAF-29 | AG18 | done | Negativbefund |
| GAF-37 | AG18 | done | Negativbefund, Terminbestätigung bereits eingebunden |
| AF25-01 | AG19 | done | fachliche Freigabe M12-05, AF01-01 offen |
| GAF-10 | AG19 | done |  |
| GAE-11 | AG20 | done | Positiver Fall des Zuordnungsvorschlags nur über 409-Zweige getestet (G4) |
| GAE-12 | AG20 | done | AG20-01 offen; Übernahme und Ergebnisbuchung unverändert |

## Welle 24 (Stand 1.69.0, 03.10.2026)

Technische Reste der Welle 23 (AN01 bis AN14, darunter die Gegenprüfung AN14 in docs/reviews/REVIEW-W23-2026-10-03.md mit 13 Befunden, zwei G2-Lücken sofort behoben: Zahlungsdateien als Mailanhang und im Belegeinsichtspaket des Eigentümerportals) und die Lückenanalyse GAK (25 Befunde GAK-101 bis GAK-406 aus vier lesenden Prüfpaketen zu Abschnitt 7, Mietverwaltung und WEG, Portale und Automatisierung, Betrieb und Anhang D und E; Pakete AN15 bis AN20). Quellen: Ergebnisdateien der Pakete, Versionsverlauf 1.69.0 in `CHANGELOG.md`. Die Freigabestufen G1 bis G5 bleiben geschlossen.

- Migrationen 0451 (portal_feature_setting.meter_photo_mode), 0452 (contact_address valid_to, superseded_at, CHECK und Index), 0453 (Vier-Augen-Freigabe majority_rule), 0454 (Rücklastschrift-Belege, Tabelle open_item_write_off mit RLS, zwei Schalter), 0455 (Platzhalter), Rundlauf 0448 bis 0455 getestet.
- Entscheidungsfragen bleiben offen und sind technisch als Mandantenschalter mit heutigem Verhalten als Standard vorbereitet: Fotopflicht Zählerstand (AM06-01), Adresshistorie und Aufbewahrung (AM14-01), Mehrheitsregelmodell (AM02-01), KI-Regelaktionen (AM04-03), Gebührenweiterbelastung Rücklastschrift (AN15-01), Ausbuchungsverfahren (AN15-02), Mieterhöhungssperre (AN18-01), Interessentenlöschung (AN18-02), Anfechtungsfrist (AN19-01), Verkaufsinserate (AN19-02), Stichtag Sonderumlage (AN19-03), Zahlungsdateien im Vollexport (AN08-01), Nachweispflicht Gates (AM10-01, AN04-01).
- Betrieb: backup.sh exportiert das Löschjournal verschlüsselt mit jedem Dump und bricht ohne Konfiguration mit Exit 3 ab (GAK-405); neues Lint compose-exposure; Seitengröße aller Listen auf 200 begrenzt (GAK-301); Massenbestätigung nur mit Vorschau-Token (GAK-105, API-Verhalten geändert, 409 ohne Token).
- Teilweise (Grundlage Welle 25): GAK-104 (Buchungsweg der Ausbuchung, CRM-Maske, Stichtag im Prüfexport), GAK-203 (Vertragsfelder Index und Staffel, VPI-Tabelle, Job, Migration nötig), GAK-205 (eigene Spalten Ertragskonto und Stichtag der Sonderumlage), GAK-303 (Hinweis im Regel-Editor), GAK-402 (zweite Tests D04, D17, D31, D34, D47, D55), GAK-107 (Mandantenstandard Klärungskonto), GAK-108 (gespeicherter Schalter, CRM-Anzeige Zeitversatz), AN19 CRM-Masken (Beschlussfolgen, Prüfdatum, Kautionsverknüpfung), AN11 Rest (rund 86 untypisierte Geldrouten).

| Paket | Befunde | Stand | Migration |
| --- | --- | --- | --- |
| AN01 | GAJ-102 | done | none |
| AN02 | GAJ-401 | done | 0451 an02_meter_photo_mode |
| AN03 | GAJ-501 | done | none |
| AN04 | GAJ-504 | done | none |
| AN05 | GAJ-610 | done | 0452 contact_address valid_to, superseded_at, ck_contact_address_valid_range, ix_contact_address_tenant_contact_from |
| AN06 | GAJ-602, AN14-09 | done, done | 0453 an06_majority_rule_approval (tenant_settings.hoa_majority_rule_four_eyes, majority_rule.requires_approval/approved_by/approved_at) |
| AN07 | AM04 | done | none |
| AN08 | AM01 | done | none |
| AN09 | AM03 | done | none |
| AN10 | AL06-02 | done | none |
| AN11 | GAI-304 | done | none |
| AN12 | AL03 | done | none |
| AN13 | GAJ-403 | done | none |
| AN14 | Review | done | none |
| AN15 | GAK-101, GAK-104 | done, partial | 0454 an15_returned_debit_writeoff (Spalten direct_debit_order und open_item, Tabelle open_item_write_off mit RLS, zwei Schalter, open_item_guard erweitert) |
| AN16 | GAK-102, GAK-105, GAK-107, GAK-108 | done, done, done, done | 0455_an16_accounting_checks.py (noop, down_revision 0454) |
| AN17 | GAK-103, GAK-106 | done, done | none |
| AN18 | GAK-201, GAK-202, GAK-203, GAK-207 | done, done, partial, done | none |
| AN19 | GAK-204, GAK-205, GAK-206, GAK-208 | done, partial, done, done | none |
| AN20 | GAK-301, GAK-302, GAK-303, GAK-401, GAK-402, GAK-403, GAK-404, GAK-405, GAK-406 | done, done, partial, done, partial, done, done, done, done | none |

## Welle 23 (Stand 1.68.0, 03.10.2026)

Reste der Welle 22 (AL01 bis AL06, darunter die Gegenprüfung AL06 in docs/reviews/REVIEW-W22-2026-10-03.md, keine Codefehler, zwei Härtungen AL06-01 und AL06-02 in AM15 umgesetzt) und die Lückenanalyse GAJ (39 Befunde GAJ-101 bis GAJ-610 entlang der durchgängigen Geschäftsprozesse, Pakete AM01 bis AM15). Quellen: Ergebnisdateien der Pakete, Versionsverlauf 1.68.0 in `CHANGELOG.md`, Lückenliste `docs/plans/LUECKENLISTE-2026-10-03.md`. Die Freigabestufen G1 bis G5 bleiben geschlossen.

- Migrationen 0449 (CHECK valid_to >= valid_from auf property_owner, property_contact, contact_relation, deposit, majority_rule, NOT VALID plus VALIDATE) und 0450 (Importberichtsarten historical_statement und resolution mit Tabellen migrated_statement und migrated_resolution), beide mit Rundlauf getestet.
- Sicherheits- und Produktschutzbefunde aus GAJ: Lastschrift- und Zahlungsdateien waren über die allgemeinen Dokumentrouten ohne Gate G2 abrufbar (GAJ-301, behoben in AM01 auf content, download-url, Portal, Bundle, Spiegelung und Ereignis-Payload); Mehrheitsregel wurde nicht gegen den Versammlungstag geprüft (GAJ-601); WhatsApp ohne Einwilligungsprüfung im Sendepfad (GAJ-405); Upload-Limit hing vom Content-Type des Clients ab (AL06-01).
- Produktfehler aus den Tests behoben: Portalseite Dokumente stürzte ab (Funktion an Client-Komponente, AM07); Kontaktzusammenführung erzeugte zwei Hauptanschriften (AM14); Terminbutton verlor Fehlermeldungen (AK08, Welle 22); der API-Nutzungstest zählte die Allowlist selbst als Aufruf und war wirkungslos (AM05).
- Tests: alle 49 Anhang-D-Fälle haben zwei unabhängige Tests (SINGLE_TEST_CASES leer); Invarianten B06 und B07 als Tests; 84 plus 7 Fremdmandantentests; Playwright phone-Projekt mit Schadensmeldung, Zählerstand, Auftrag, Dokumente; PITR-Selbsttest gegen echten Wegwerf-Cluster in CI.
- Neue offene Punkte: AL06-01, AL06-02, AM02-01, AM04-01, AM04-03, AM06-01, AM09-01, AM10-01, AM14-01, AM13-01 bis AM13-06 (Vorlagen in `docs/plans/ENTSCHEIDUNGEN-2026-10-01.md`).
- Teilweise erledigt (Rest für Welle 24): GAI-304 (AL04), GAJ-602 (AM02), GAJ-102 (AM05), GAJ-401 (AM06), GAJ-403 (AM07), GAJ-501 (AM09), GAJ-504 (AM10), GAJ-505 (AM11), GAJ-610 (AM14), AL06-02 (AM15).
- Vom Koordinator bei der Integration erledigt: ruff fix und format, Allowlist um vier neue Pfade, OpenAPI-Export und api-client, Hilfeindex und Handbuch, i18n-Nutzungsprüfung, Migrationsrundlauf 0450 nach 0448 und zurück, 76 Wächtertests, Gesamtsuiten API, CRM und Portal, Builds, Playwright (Ergebnis siehe Versionsverlauf und Ergebnisbericht).
- Deploy-Hinweise 1.68.0: zwei Migrationen (0449, 0450); 0449 validiert Zeitraum-Prüfregeln und bricht ab, wenn Bestandsdaten valid_to vor valid_from haben (vorher mit dem Abgleichbericht prüfen); nach dem Deploy einmal POST /document-categories/ensure-defaults je Mandant, damit bestehende Zahlungsdateien die Kategorie payment_file erhalten; deploy.sh verlangt für Staging die Smoke-URLs (STAGING_API_URL, STAGING_CRM_URL) oder DEPLOY_SKIP_SMOKE=1; neue CI-Jobs pitr-drill und erweiterte agent-docs-Prüfungen; drei KI-Schalter stehen auf an (bisheriges Verhalten), Entscheidung AM04-01 bis AM04-03.

| Befund-ID | Paket | Status | Hinweis |
| --- | --- | --- | --- |
| GAI-612 | AL01 | done |  |
| GAI-612 | AL02 | done |  |
| GAI-307 | AL03 | done |  |
| GAI-215 | AL04 | done |  |
| GAI-304 | AL04 | partial |  |
| GAI-110 | AL05 | done |  |
| GAJ-301 | AM01 | done |  |
| GAJ-601 | AM02 | done |  |
| GAJ-602 | AM02 | partial |  |
| GAJ-604 | AM02 | done |  |
| GAJ-603 | AM03 | done |  |
| GAJ-608 | AM03 | done |  |
| GAJ-609 | AM03 | done |  |
| GAJ-605 | AM04 | done |  |
| GAJ-606 | AM04 | done |  |
| GAJ-607 | AM04 | done |  |
| GAJ-101 | AM05 | done |  |
| GAJ-102 | AM05 | partial | nur PATCH Zahlungsposition (AmountCorrectionForm); Zahlungsplan PATCH fehlt, weil das CRM keine Planliste lädt |
| GAJ-103 | AM05 | done |  |
| GAJ-104 | AM05 | done |  |
| GAJ-201 | AM05 | done |  |
| GAJ-203 | AM05 | done |  |
| GAJ-204 | AM05 | done |  |
| GAJ-202 | AM06 | done |  |
| GAJ-401 | AM06 | partial | Fotopflicht nur als Code-Vorgabe (Hinweis, keine Ablehnung); gespeicherter Mandantenschalter braucht Migration (AM06-01) |
| GAJ-402 | AM06 | done |  |
| GAJ-404 | AM06 | done |  |
| GAJ-403 | AM07 | partial | Dokumente-Test schlug gegen den vorhandenen Build fehl (Absturz der Seite, siehe Fehlerbehebung); nach dem Fix nicht erneut per Playwright geprüft, da ein next  |
| GAJ-406 | AM07 | done |  |
| GAJ-405 | AM08 | done |  |
| GAJ-407 | AM08 | done |  |
| GAJ-501 | AM09 | partial | keine CRM-Ansicht für Altabrechnungen, Beschlüsse und Prüfbericht (nur API; Import über bestehenden Assistenten mit neuen Berichtsarten) |
| GAJ-502 | AM09 | done |  |
| GAJ-503 | AM10 | done |  |
| GAJ-504 | AM10 | partial | typisierte prüfbare Nachweisverweise (ci-run:<Lauf>@<Commit>, commit:, version:, doc:) mit evidence_kind, cases_passed_without_test_run, Nachweistext im G1-Antr |
| GAJ-506 | AM10 | done |  |
| GAJ-507 | AM10 | done |  |
| GAJ-508 | AM10 | done |  |
| GAJ-505 | AM11 | partial | Protokoll eines realen Drills mit Produktionsbasisbackup fehlt weiterhin (Betreiberschritt auf dem Server); kein systemd-Timer für den PITR-Drill angelegt |
| GAJ-509 | AM11 | done |  |
| GAJ-302 | AM12 | done |  |
| GAJ-303 | AM12 | done |  |
| GAJ-304 | AM12 | done |  |
| GAJ-305 | AM12 | done |  |
| Entscheidungen | AM13 | done |  |
| GAJ-610 | AM14 | partial | valid_to und echte Stichtagsabfrage fehlen (Schema und Entscheidung AM14-01) |
| AL06-01 | AM15 | done |  |
| AL06-02 | AM15 | partial | forwarded-for.ts kann die direkte Gegenstelle als rechtesten Eintrag anhängen (getestet), Next.js-Routen liefern die Socketadresse aber nicht, daher übergibt no |

## Welle 22 (Stand 1.67.0, 03.10.2026)

Reste der Welle 21 (41 Teilbefunde der Lückenanalyse GAI) in 19 Paketen AK01 bis AK19, darunter die Gegenprüfung AK19 (docs/reviews/REVIEW-W21-2026-10-03.md, Befunde AK19-01 bis AK19-09, keine Regression, ein Zeitzonenfehler bei naiven Zeitstempeln behoben). Quellen: Ergebnisdateien der Pakete (Feld findings), Versionsverlauf 1.67.0 in `CHANGELOG.md`. Die Freigabestufen G1 bis G5 bleiben geschlossen.

- Migrationen 0447 (tenant_settings: heating_negative_costs_mode, hoa_remainder_mode, check_amounts_tolerance_cents mit konservativen Standardwerten) und 0448 (privacy_access_request), beide mit Rundlauf getestet.
- Produktschutz aus Welle 22: Kautionsfreigabe verlangt in der API eine andere Person als den Ersteller (409 MHVP-CONTR-0002); Auszahlungen ohne Rechnung stehen in der API hinter Gate G2; sechs Schaltflächen erscheinen nur mit Schreibrecht; ASGI-Körperlimit je Pfadgruppe vor dem Multipart-Parsing.
- Tests: 84 Mandantentrennungstests mit echten Objekten (AK03, keine Lücke), 17 Anhang-D-Fälle mit zweitem unabhängigem Test (AK09, AK10; 12 Fälle offen), 19 weitere Komponententests (AK08), Wächter gegen neue untypisierte Routen (AK11, Liste mit 966 Routen), Coverage-Schwellen knapp unter dem Basiswert (CRM 71/62/67/73, Portal 74/66/78/76 Prozent).
- Neue offene Punkte: AJ01-01, AJ01-02, AJ02-01, AJ07-01, AJ07-02, AJ13-01, AK19-02, AK19-03, AK19-04, AK19-05, AK19-09; AK19-02 bis AK19-05 und AK19-09 im Review.
- Teilweise erledigt (Rest für Welle 23): GAI-215 (AK01), GAI-307 (AK02), GAI-612 (AK09), GAI-612 (AK10), GAI-304 (AK11), GAI-110 (AK12).
- Vom Koordinator bei der Integration erledigt: Importreihenfolge in main.py, Typcast in forwarded-for-Test, ungenutzter Import, Allowlist-Eintrag für GET /privacy/access-requests/{request_id}, ADR-Index 0022 und 0024 bis 0030 ergänzt, OpenAPI-Export und api-client, Hilfeindex und Handbuch, Migrationsrundlauf 0448 nach 0446 und zurück, Wächtertests (45), Gesamtsuiten API, CRM und Portal, Builds, Playwright (Ergebnis siehe Versionsverlauf und Ergebnisbericht).
- Deploy-Hinweise 1.67.0: zwei Migrationen (0447, 0448); neue Settings MHVP_BODY_LIMIT_* (Standardwerte oberhalb der Endpunktlimits), MHVP_RATE_LIMIT_TRUSTED_PROXIES auch im CRM-Container, falls freigegeben (AJ07-01); Compose-Profil für den zweiten Worker (AK05) optional; Coverage-Jobs noch nicht in CI.

| Befund-ID | Paket | Status | Hinweis |
| --- | --- | --- | --- |
| GAI-202 | AK01 | done |  |
| GAI-204 | AK01 | done |  |
| GAI-214 | AK01 | done |  |
| GAI-215 | AK01 | partial | Summentests fuer heating _component (beide Modi, negativ), Monatsraten aller Restcentmodi, Zeitanteile bei Mieterwechsel, Kautionszins (Historie gleich Referenz |
| GAI-307 | AK02 | partial | noch ohne emit: heating-cost-imports (anlegen, csv, mapping, rows, apply), statements heating PUT/consumptions/apply/import, owner-statements anlegen/options/ap |
| GAI-303 | AK03 | done |  |
| GAI-309 | AK04 | done |  |
| GAI-311 | AK04 | done |  |
| GAI-312 | AK04 | done |  |
| GAI-317 | AK05 | done |  |
| GAI-319 | AK05 | done |  |
| GAI-506 | AK06 | done |  |
| GAI-507 | AK06 | done |  |
| GAI-513 | AK07 | done |  |
| GAI-515 | AK07 | done |  |
| GAI-516 | AK07 | done |  |
| GAI-615 | AK08 | done |  |
| GAI-612 | AK09 | partial | Teil 1: D05, D06, D15, D18, D20 weiterhin nur mit einem Test (Bankimport-, Zahlungsdatei-, Eigentümerwechsel-, Untergemeinschafts- und Sonderumlagenwelten nicht |
| GAI-612 | AK10 | partial |  |
| GAI-304 | AK11 | partial | rund 955 Routen weiter untypisiert, darunter alle mit Decimal-Antworten (nur gezaehlt ueber die Allowlist, nicht getrennt ausgewiesen) |
| GAI-110 | AK12 | partial | Zahlläufe: Vorschau-Liste nur mit limit, SavedFilters für Postfach fehlen |
| GAI-512 | AK13 | done |  |
| GAI-621 | AK13 | done |  |
| GAI-402 | AK14 | done |  |
| GAI-410 | AK14 | done |  |
| GAI-109 | AK15 | done |  |
| GAI-422 | AK15 | done |  |
| GAI-605 | AK15 | done |  |
| GAI-404 | AK16 | done |  |
| GAI-315 | AK17 | done |  |
| GAI-301 | AK18 | done |  |

## Welle 21 (Stand 1.66.0, 02.10.2026)

Befunde der Lückenanalyse GAI (Gesamtdurchlauf des Master-Prompts in sechs Teilen: Regeln und Konventionen, Geld und Rundung, Sicherheit und Berechtigungen, Oberfläche und Handbuch, Datenschutz und Betrieb, Modulreste; 126 Befunde GAI-101 bis GAI-623), Pakete AJ01 bis AJ32 in zwei Reihen. Die Welle wurde nach einem Umgebungsreset am 02.10.2026 vollständig neu erarbeitet, der erste Durchlauf ging vor dem Commit verloren. Quellen: Ergebnisdateien der Pakete (Feld findings), Versionsverlauf 1.66.0 in `CHANGELOG.md`, Befunddateien GAI-1 bis GAI-6 der Analyse. Die Freigabestufen G1 bis G5 bleiben geschlossen. Status wie in den Ergebnisdateien: done, partial, not_done.

- Migrationen 0444 bis 0446, alle real: 0444 Datenbankschutz für open_item (alle fachlich festen Felder), journal_entry (Periodensperre), payment_order, deposit_movement, receivable_item und journal_number_counter; 0445 Löschvorschläge je Datenart (auto_propose, Status proposed, Datenarten domain_event, platform_user, bank_raw); 0446 Fehlversuchszähler des Magic-Link-Codes.
- Fachliche Korrekturen aus den Tests: distribute verteilte negative Summen nicht summentreu (GAI-101); drei Bankrouten und drei Vermietungsrouten gaben für fremde Mandanten 200 oder 503 statt 404 (AJ05, AJ23); sechs Schreibrouten verlangten nur Leserecht (AJ21); das Vertragsformular sandte die Kontakt-ID als Partei-ID (AJ32, Produktionsfehler aus Welle 20).
- Verhaltensänderungen: Importwerte wie 1.234 ohne Komma werden abgewiesen statt als 1234 gelesen (AJ02); neue Abrechnungsversion verlangt einen Korrekturgrund (AJ27); Celery-Tasks haben Zeitlimits je Klasse und die zwölf schnellen Beat-Tasks eine Überlappungssperre (AJ11); Uploads brechen bei Überschreitung mit 413 MHVP-DOC-0010 ab (AJ10).
- Neue offene Entscheidungen: AJ01-01, AJ01-02, AJ02-01, AJ02-02, AJ02-03, AJ03-01, AJ03-03, AJ07-01, AJ07-02, AJ09-01, AJ12-01, AJ13-01, AJ13-02, AJ13-03, AJ15-01, AJ15-05, AJ21-01, AJ26-01, AJ26-02, AJ27-01, AJ28-02, AJ28-04, AJ30-14, AJ30-17, AJ30-18, AJ30-19, AJ30-28, AJ31-01 sowie AJ30-01 bis AJ30-28 (Vorlagen in `docs/plans/ENTSCHEIDUNGEN-2026-10-01.md`). Neue Annahmen AJ09-01 (Europe/Berlin als fachliche Zeitzone aller Mandanten) und AJ12-01 (90 Tage bis zur Anonymisierung abgelaufener Sitzungsdaten) in `docs/ASSUMPTIONS.md`.
- Teilweise erledigt (Rest für Welle 22): GAI-202 (AJ01), GAI-214 (AJ01), GAI-204 (AJ02), GAI-215 (AJ02), GAI-210 (AJ03), GAI-307 (AJ04), GAI-303 (AJ06), GAI-309 (AJ07), GAI-311 (AJ07), GAI-312 (AJ07), GAI-422 (AJ08), GAI-315 (AJ10), GAI-317 (AJ11), GAI-319 (AJ11), GAI-501 (AJ12), GAI-503 (AJ12), GAI-504 (AJ12), GAI-522 (AJ12), GAI-506 (AJ13), GAI-507 (AJ13), GAI-513 (AJ14), GAI-516 (AJ14), GAI-118 (AJ15), GAI-119 (AJ15), GAI-515 (AJ15), GAI-519 (AJ15), GAI-520 (AJ15), GAI-521 (AJ15), GAI-404 (AJ16), GAI-615 (AJ18), GAI-612 (AJ19), GAI-110 (AJ20), GAI-304 (AJ22), GAI-303 (AJ24), GAI-512 (AJ26), GAI-623 (AJ26), GAI-607 (AJ27), GAI-410 (AJ28), GAI-422 (AJ29), GAI-109 (AJ31), GAI-605 (AJ31).
- Vom Koordinator bei der Integration erledigt: drei rekursive businessToday-Wrapper entfernt (AJ09), fünf eslint-Warnungen (ungenutztes busy aus AJ29), zwei ruff-Befunde und vier Formatierungen, OpenAPI-Export und api-client neu erzeugt, Hilfeindex und Handbuch neu gebaut, Versionsnummern in pyproject und package.json per scripts/bump_version.py gesetzt, Migrationsrundlauf 0446 nach 0443 und zurück, Wächtertests (Migrationen, Tenant-Index, Ereigniskatalog, Problemcodes, Schemakonvention) grün, Gesamtsuiten API, CRM und Portal, next build und Playwright (Ergebnis siehe Versionsverlauf und Ergebnisbericht).
- Deploy-Hinweise 1.66.0: drei Migrationen (0444 bis 0446); Traefik-Router crm-auth und portal-auth mit auth-ratelimit in compose.prod.yaml prüfen; neue Settings MHVP_CELERY_LIMIT_*, MHVP_CELERY_OVERLAP_LOCK_ENABLED, rate_limit_trusted_proxies, rate_limit_token_routes_fail_closed stehen auf konservativen Standardwerten; Worker-Smoke nach dem Start (Beat lädt mhvp.core.auth.session_purge und mhvp.privacy.proposals); Branch Protection für die CI-Jobs version-check, commitlint, restore-drill-dry-run und e2e-backend setzen (AJ26-01).

| Befund-ID | Paket | Status | Hinweis |
| --- | --- | --- | --- |
| GAI-101 | AJ01 | done |  |
| GAI-201 | AJ01 | done |  |
| GAI-202 | AJ01 | partial | negative_costs_mode in HeatingSettings (legacy_warn Standard mit Warnhinweis, distribute); persistenter Mandantenschalter fehlt (Schema) |
| GAI-213 | AJ01 | done |  |
| GAI-214 | AJ01 | partial | monthly_rates/remainder_mode (report_only Standard, first_month, last_month) in hoa.calc.plan_results; persistenter Mandantenschalter und UI fehlen (Schema) |
| GAI-613 | AJ01 | done |  |
| GAI-614 | AJ01 | done |  |
| GAI-203 | AJ02 | done |  |
| GAI-204 | AJ02 | partial | check_amounts rundet HALF_UP wie split_gross, Toleranz als Konstante CHECK_AMOUNTS_TOLERANCE und Parameter (Standard 1 Cent); Mandantenschalter offen bis AJ02-0 |
| GAI-205 | AJ02 | done |  |
| GAI-206 | AJ02 | done |  |
| GAI-207 | AJ02 | done |  |
| GAI-208 | AJ02 | done |  |
| GAI-215 | AJ02 | partial | Summentests fuer distribute_cents (Eigenschaft, negativ, Null) und reserve_split; heating _component, Kautionszins, Eigentuemerabrechnung, proration nicht ergae |
| GAI-209 | AJ03 | done |  |
| GAI-210 | AJ03 | partial | Objektsperre period_lock (object_period) nur in der Anwendung, Frage AJ03-02 |
| GAI-211 | AJ03 | done |  |
| GAI-212 | AJ03 | done |  |
| GAI-105 | AJ04 | done |  |
| GAI-307 | AJ04 | partial | emit mit changes ergänzt für Steuerprofil Objekt und Lieferant, Rechnungssteuerdaten, § 35a setzen/entfernen, interest-tax-config, Gläubiger-Id Rechtsträger und |
| GAI-601 | AJ04 | done |  |
| GAI-604 | AJ04 | done |  |
| GAI-606 | AJ04 | done |  |
| GAI-303 | AJ05 | done |  |
| GAI-303 | AJ06 | partial | billing und Portal (Bewohnerseite, Übergabe im Portal) nur 403/401 mit unbekannten Ids, kein Fremdmandant-404 mit echten Objekten (Abrechnungen, Heizkostenimpor |
| GAI-308 | AJ06 | done |  |
| GAI-116 | AJ07 | done |  |
| GAI-309 | AJ07 | partial | payload begrenzt (64 KiB, 200 Felder, Tiefe 3, Schluessel 100, Text 5000) plus Ereignis self_disclosure.submitted ohne Inhalt; eigenes Limit je Token fehlt, DSG |
| GAI-310 | AJ07 | done |  |
| GAI-311 | AJ07 | partial | API-Seite fertig (rate_limit_trusted_proxies, Standard leer = aus, rechtester nicht vertrauter Hop); CRM-BFF und Sitzungsrouten reichen X-Forwarded-For noch nic |
| GAI-312 | AJ07 | partial | Schalter rate_limit_token_routes_fail_closed (Standard aus) mit Notzaehler im Prozess fuer Token- und Code-Routen; Limit je Route und Token fehlt |
| GAI-422 | AJ08 | partial | nur Freigabe- und Sperrkomponenten, Rest bei AJ29 |
| GAI-426 | AJ08 | done |  |
| GAI-427 | AJ08 | done |  |
| GAI-603 | AJ08 | done |  |
| GAI-102 | AJ09 | done |  |
| GAI-103 | AJ09 | done |  |
| GAI-104 | AJ09 | done |  |
| GAI-115 | AJ09 | done |  |
| GAI-106 | AJ10 | done |  |
| GAI-313 | AJ10 | done |  |
| GAI-314 | AJ10 | done |  |
| GAI-315 | AJ10 | partial | alle 6 Webhooks nutzen read_body_limited (Strom mit Abbruch, auch ohne Content-Length), WhatsApp 256 KiB vor HMAC, compare_digest, Engine aus app.state.resource |
| GAI-316 | AJ11 | done |  |
| GAI-317 | AJ11 | partial | Retry nur für 6 sicher idempotente Tasks; weitere ereignisgetriebene Tasks (archive_message, suggest_message, prepare_mail, paperless_receipt_intake, assistant_ |
| GAI-318 | AJ11 | done |  |
| GAI-319 | AJ11 | partial | compose.yaml nicht geändert (kein zweiter Worker, Beat Zeitplandatei weiter in /tmp), nur Runbook |
| GAI-501 | AJ12 | partial | Vorschlagsjob mhvp.privacy.proposals (Beat 04:25) nur bei freigegebenem Profil mit auto_propose (Standard aus); Kontakte erhalten Antrag Status proposed, Überna |
| GAI-502 | AJ12 | done |  |
| GAI-503 | AJ12 | partial | domain_event als Datenart im Löschprofil, nur Zählung, Standard keine Löschung; Fristen je Ereignisklasse offen (AJ12-01) |
| GAI-504 | AJ12 | partial | platform_user als Datenart dokumentierbar, keine Anonymisierung (mandantenübergreifend, M20-08-Q7 offen) |
| GAI-522 | AJ12 | partial | bank_raw als Datenart dokumentierbar, Regel AJ12 dokumentiert; Löschpfad Bankverbindungen und finAPI-Anbieterlöschung offen |
| GAI-414 | AJ13 | done |  |
| GAI-506 | AJ13 | partial | Tickets, Kommunikation, Dokumentbezüge per Mandantenschalter (Standard aus, sonst nur Anzahl); Portalkonto mit Anmeldeereignissen/Sitzungen sowie Zahlungs- und  |
| GAI-507 | AJ13 | partial | Fristeinstellung ohne Standardwert und Überwachung für Löschanträge; Auskunftsanträge ohne Eingangsdatensatz (Schemabedarf AJ13-03), keine Eintragung ins allgem |
| GAI-508 | AJ13 | done |  |
| GAI-509 | AJ13 | done |  |
| GAI-510 | AJ13 | done |  |
| GAI-108 | AJ14 | done |  |
| GAI-513 | AJ14 | partial | Runbooks 2FA-Reset, FINTS-Betrieb und Webhook-Betrieb nicht geschrieben (nicht im Paketumfang) |
| GAI-514 | AJ14 | done |  |
| GAI-516 | AJ14 | partial | ADR für Webhook-Helfer, CSP, Split-Worker, Branding vorhanden; Mandantenschalter-Muster, Zwei-Personen-Reset, Tenant-Index-Wächter, Kettenprüfung, Snapshot-Trig |
| GAI-608 | AJ14 | done |  |
| GAI-117 | AJ15 | done |  |
| GAI-118 | AJ15 | partial | Platzhalter einheitlich gekennzeichnet, Inhalte brauchen Betreiber |
| GAI-119 | AJ15 | partial | Abgleichtabelle, Master-Prompt unveraendert (AJ15-03) |
| GAI-428 | AJ15 | done |  |
| GAI-505 | AJ15 | done |  |
| GAI-515 | AJ15 | partial | Stammdatenvorschlag benannt; Brotkruemennavigation nicht als eigener Abschnitt |
| GAI-517 | AJ15 | done |  |
| GAI-518 | AJ15 | done |  |
| GAI-519 | AJ15 | partial | B10 bis B14 nicht vergeben vermerkt, Entscheidung Betreiber (AJ15-01) |
| GAI-520 | AJ15 | partial | V17-Matrixvorlage und V13-Pruefmappe angelegt, Entscheidungen offen |
| GAI-521 | AJ15 | partial | Doppelvergabe M11-42 und Pruefplan nur als OPEN_QUESTIONS AJ15-05 |
| GAI-403 | AJ16 | done |  |
| GAI-404 | AJ16 | partial | Maske erfasst nur submitted, accepted_by_bank, rejected; executed und returned buchen (Ausgleich, Storno) und bleiben beim Import der Bankrueckmeldung bzw. API |
| GAI-405 | AJ16 | done |  |
| GAI-406 | AJ16 | done |  |
| GAI-407 | AJ16 | done |  |
| GAI-411 | AJ16 | done |  |
| GAI-412 | AJ17 | done |  |
| GAI-413 | AJ17 | done |  |
| GAI-415 | AJ17 | done |  |
| GAI-416 | AJ17 | done |  |
| GAI-417 | AJ17 | done |  |
| GAI-418 | AJ17 | done |  |
| GAI-419 | AJ17 | done |  |
| GAI-420 | AJ17 | done |  |
| GAI-421 | AJ18 | done |  |
| GAI-424 | AJ18 | done |  |
| GAI-425 | AJ18 | done |  |
| GAI-611 | AJ18 | done |  |
| GAI-615 | AJ18 | partial | 22 Komponenten getestet; verbleibend ohne Test u. a. metering/ConnectionsAdmin, AssignmentWizard, PropertyMeteringTab, imports/Immoware24Wizard, tickets/*, mail |
| GAI-107 | AJ19 | done |  |
| GAI-612 | AJ19 | partial | Marker annex_d registriert, D16 (2 Tests), D17, D35 bis D38 markiert; Waechter verlangt je Fall D01 bis D49 mindestens einen Test, 29 Faelle mit nur einem Test  |
| GAI-616 | AJ19 | done |  |
| GAI-617 | AJ19 | done |  |
| GAI-618 | AJ19 | done |  |
| GAI-620 | AJ19 | done |  |
| GAI-110 | AJ20 | partial | Offene Posten, Mahnfälle, WEG Listen, Postfach, Zahlläufe haben keine Abfrageparameter in der Oberfläche, Ressourcen stehen bereit |
| GAI-114 | AJ20 | done |  |
| GAI-301 | AJ21 | done |  |
| GAI-304 | AJ22 | partial | Antwortmodelle fuer 4 schreibende Routen (PUT /hoa/acquisition-rules/{kind} HoaAcqRuleOut, PUT /hoa/allocation-proposal-settings HoaAllocationProposalSettingOut |
| GAI-305 | AJ22 | done |  |
| GAI-306 | AJ22 | done |  |
| GAI-303 | AJ23 | done |  |
| GAI-303 | AJ24 | partial | Fremdmandant-404 mit echten Objekten fehlt für Messdienst (Zuordnungen, Übertragungen, Clearing), Telefonie-Anrufe, Mail-Postfächer/Playbooks, Lizenzen/Preislis |
| GAI-621 | AJ25 | partial |  |
| GAI-622 | AJ25 | done |  |
| GAI-609 | AJ25 | done |  |
| GAI-610 | AJ25 | done |  |
| GAI-111 | AJ26 | done |  |
| GAI-112 | AJ26 | done |  |
| GAI-113 | AJ26 | done |  |
| GAI-511 | AJ26 | done |  |
| GAI-512 | AJ26 | partial | Kontakt-Löschjournal (mhvp.privacy.erasure_journal export/replay, erasure.anonymize_contact extrahiert) und Runbook vorhanden; Replay gegen echte DB nur durch r |
| GAI-623 | AJ26 | partial | docs/runbooks/ci-required-checks.md listet e2e-backend als Pflichtprüfung; Branch Protection selbst ist nur im GitHub-Setup möglich (AJ26-01) |
| GAI-602 | AJ27 | done |  |
| GAI-607 | AJ27 | partial | /parties lehnt as_of weiter per strict_query mit 422 ab, Test prueft jetzt, dass die Meldung den Parameter nennt; Gueltigkeitsspalten an Party brauchen Schema,  |
| GAI-401 | AJ28 | done |  |
| GAI-402 | AJ28 | done |  |
| GAI-408 | AJ28 | done |  |
| GAI-409 | AJ28 | done |  |
| GAI-410 | AJ28 | partial | Vier-Augen nur im CRM per Bestaetigung; API prueft created_by != Freigebender nicht (AJ28-04, Domaene contracts) |
| GAI-422 | AJ29 | partial | nicht umgesetzt AppointmentButton, LocalModelStatus, OccupancyList, AvailabilitySelfMeasurement, CostTypeAccountsAdmin (eigene Handler bzw. Auswahlfelder, Einze |
| GAI-423 | AJ29 | done | ohne Leerzustand belassen, da statisch, durch Elternkomponente abgedeckt oder nie leer: AssistantTab, ChatLinks, ChatTools (null-Guard), ProviderSettings, Tenan |
| GAI-102 | AJ30 | done |  |
| GAI-108 | AJ30 | done |  |
| GAI-117 | AJ30 | done |  |
| GAI-118 | AJ30 | done |  |
| GAI-119 | AJ30 | done |  |
| GAI-202 | AJ30 | done |  |
| GAI-203 | AJ30 | done |  |
| GAI-204 | AJ30 | done |  |
| GAI-205 | AJ30 | done |  |
| GAI-208 | AJ30 | done |  |
| GAI-209 | AJ30 | done |  |
| GAI-210 | AJ30 | done |  |
| GAI-211 | AJ30 | done |  |
| GAI-213 | AJ30 | done |  |
| GAI-214 | AJ30 | done |  |
| GAI-301 | AJ30 | done |  |
| GAI-311 | AJ30 | done |  |
| GAI-312 | AJ30 | done |  |
| GAI-316 | AJ30 | done |  |
| GAI-319 | AJ30 | done |  |
| GAI-401 | AJ30 | done |  |
| GAI-402 | AJ30 | done |  |
| GAI-408 | AJ30 | done |  |
| GAI-409 | AJ30 | done |  |
| GAI-410 | AJ30 | done |  |
| GAI-414 | AJ30 | done |  |
| GAI-425 | AJ30 | done |  |
| GAI-501 | AJ30 | done |  |
| GAI-503 | AJ30 | done |  |
| GAI-504 | AJ30 | done |  |
| GAI-505 | AJ30 | done |  |
| GAI-506 | AJ30 | done |  |
| GAI-510 | AJ30 | done |  |
| GAI-519 | AJ30 | done |  |
| GAI-520 | AJ30 | done |  |
| GAI-521 | AJ30 | done |  |
| GAI-522 | AJ30 | done |  |
| GAI-603 | AJ30 | done |  |
| GAI-606 | AJ30 | done |  |
| GAI-607 | AJ30 | done |  |
| GAI-614 | AJ30 | done |  |
| GAI-109 | AJ31 | partial | Farben (Primaer, Akzent) als CSS-Variablen im CRM-Layout hinter Schalter branding.crm_apply (Standard aus); Logo nicht angewendet |
| GAI-605 | AJ31 | partial | coverage-Block (v8) in beiden Configs vorbereitet; @vitest/coverage-v8 nicht im pnpm-Store (Store enthaelt nur index/projects/files, find ohne Treffer), Schwell |
| GAI-619 | AJ31 | done |  |

## Welle 20 (Stand 1.65.0, 02.10.2026)

Befunde der Lückenanalyse GAH (Modul-Durchlauf MASTER-PROMPT 3 bis 17 und Anhang D sowie Rückstände der Welle 19, 62 Befunde GAH-101 bis GAH-418), Pakete AI01 bis AI18. Quellen: Ergebnisdateien der Pakete (Feld findings), Versionsverlauf 1.65.0 in `CHANGELOG.md`. Die Freigabestufen G1 bis G5 bleiben geschlossen. Status wie in den Ergebnisdateien: done, partial, not_done.

- Migrationen 0439 bis 0443, alle real: 0439 Trigger statement_snapshot (nur Einfügen), 0440 Indizes mit führender tenant_id für 128 Tabellen, 0441 Fehlerzähler und Schalter der Webhooks, 0442 Antrag und Einstellung zum Zurücksetzen des zweiten Faktors, 0443 Schalter § 35a sowie Tabellen section35a_certificate_log und deposit_hint_setting.
- Fachliche Korrektur aus den Tests: Der KI-Stapelpfad prüfte AVV-Nachweis, Dokument und Opt-out nicht (GAH-203); jetzt wie das Gateway, offene Stapel werden bei entzogener Freigabe nicht mehr abgerufen.
- Neue offene Entscheidungen: AI03-01, AI07-01, AI07-02, AI08-01, AI09-01, AI12-01, AI12-02, AI17-01 bis AI17-13 (Vorlagen in `docs/plans/ENTSCHEIDUNGEN-2026-10-01.md`). Vermerke technisch vorbereitet: AI18-01, AI18-02. Neue Annahme A-AI01-01 in `docs/ASSUMPTIONS.md`.
- Festlegungen des Koordinators: as_of bei Umlageschlüsseln liefert Schlüssel mit einem am Stichtag gültigen Einheitenwert (AI08, zu bestätigen in AI08-01); Nummernkreis 001200 bis 001999 erlaubt auch technical und transit (A-AI01-01).
- Zählung: 62 Befunde (13 davon nur Entscheidung, als Vorlagen erledigt), Status je Paket in der Tabelle; partial: GAH-102, GAH-201, GAH-402, GAH-213, GAH-208, GAH-301, GAH-304, GAH-310, GAH-407 (AI16), GAH-101 (AI18).
- Vom Koordinator bei der Integration erledigt: ruff format für drei Dateien, LooseGet-Cast in der Auswertungsseite nach dem OpenAPI-Export entfernt, OpenAPI-Export und api-client neu erzeugt, Hilfeindex und Handbuch neu gebaut, Migrationskette 0248 bis 0443 mit Drift-Check, Tenant-Index-Wächter, Ereigniskatalog, Listeninventar und Gate-Abdeckung grün (42 Tests), Gesamtsuiten API, CRM und Portal sowie next build und Playwright wegen der CSP-Umstellung (Ergebnis siehe Versionsverlauf und Ergebnisbericht).
- Korrektur des Koordinators (Produktionsbefund 02.10.2026, MHVP-BANK-0014 mit Rückmeldecode 9010 beim Aktualisieren): `mhvp.banking.fints` zeichnet die Rückmeldungen der Bank auf (RecordingClient), zeigt sie in der Fehlermeldung an und eröffnet den Dialog bei 9010 einmal ohne gespeicherten Zustand neu; drei neue Tests in `tests/unit/test_fints.py`.
- Rückstände für Welle 21: GAH-407 Rest (22 Komponenten), alte Liquiditätsroute ohne Scope-Prüfung, billing new-version mit Body-Schema, CRM-Maske für MFA-Reset-Anträge, Bankbefund in accounting checks(), Vitest-Coverage-Schwelle, quantize ohne Rundungsverfahren, Summentreue reserve_split, party.valid_from und valid_to, CSP-Dokumentation im Runbook.

| Befund-ID | Paket | Status | Hinweis |
| --- | --- | --- | --- |
| GAH-101 | AI17 | done | AI17 Vorlage AI17-01; AI18 Schalter section_35a_basis Standard Rechnungsdatum, Protokoll je Vertrag und Jahr ohne Sperre |
| GAH-101 | AI18 | partial | AI17 Vorlage AI17-01; AI18 Schalter section_35a_basis Standard Rechnungsdatum, Protokoll je Vertrag und Jahr ohne Sperre |
| GAH-102 | AI01 | partial | Bankbefund noch nicht in accounting checks() |
| GAH-103 | AI02 | done |  |
| GAH-104 | AI02 | done | Rohvariante GET /ledgers/{id}/liquidity ohne Scope-Prüfung bleibt vorerst (Folgepunkt) |
| GAH-105 | AI01 | done | Annahme A-AI01-01: technical und transit im Bereich 001200 bis 001999 zulässig |
| GAH-106 | AI02 | done |  |
| GAH-107 | AI05 | done |  |
| GAH-108 | AI17 | done |  |
| GAH-109 | AI17 | done |  |
| GAH-110 | AI03 | done | Entscheidung AI03-01 offen, Standard 365 fest |
| GAH-111 | AI17 | done | AI17 Vorlage AI17-04; AI18 Schalter deposit_limit_hint_enabled Standard aus |
| GAH-111 | AI18 | done | AI17 Vorlage AI17-04; AI18 Schalter deposit_limit_hint_enabled Standard aus |
| GAH-112 | AI03 | done |  |
| GAH-113 | AI03 | done |  |
| GAH-114 | AI17 | done | D16 ohne Fallkennung, 13 Fälle mit Einzelfundstelle |
| GAH-115 | AI17 | done | rund 100 quantize-Aufrufe ohne Rundungsverfahren (AI17-13), Summentreue reserve_split zu testen |
| GAH-201 | AI01 | partial | paralleler finAPI- und FinTS-Abruf nicht getestet (Celery, Anbieter) |
| GAH-202 | AI07 | done | Schalter objektakte_webhook_require_timestamp Standard aus, AI07-01 offen |
| GAH-202 | AI17 | done | Schalter objektakte_webhook_require_timestamp Standard aus, AI07-01 offen |
| GAH-203 | AI06 | done |  |
| GAH-204 | AI06 | done |  |
| GAH-205 | AI06 | done |  |
| GAH-206 | AI07 | done | automatisches Deaktivieren nur per Schalter, AI07-02 offen |
| GAH-206 | AI17 | done | automatisches Deaktivieren nur per Schalter, AI07-02 offen |
| GAH-207 | AI07 | done |  |
| GAH-208 | AI08 | partial | nur /postal/jobs begrenzt, Inventar LISTENLIMITS-2026-10-02.md, AI08-01 offen |
| GAH-208 | AI17 | done | nur /postal/jobs begrenzt, Inventar LISTENLIMITS-2026-10-02.md, AI08-01 offen |
| GAH-209 | AI08 | done |  |
| GAH-210 | AI17 | done |  |
| GAH-211 | AI05 | done |  |
| GAH-212 | AI07 | done |  |
| GAH-213 | AI08 | partial | /parties braucht valid_from und valid_to (Schema), as_of bei allocation-keys über gültigen Einheitenwert |
| GAH-214 | AI10 | done |  |
| GAH-215 | AI07 | done |  |
| GAH-301 | AI09 | partial | Admin-Reset hinter Schalter Standard aus, CRM-Maske und Wiederherstellungscodes offen (AI09-01) |
| GAH-301 | AI17 | done | Admin-Reset hinter Schalter Standard aus, CRM-Maske und Wiederherstellungscodes offen (AI09-01) |
| GAH-302 | AI09 | done |  |
| GAH-303 | AI10 | done | style-src behält unsafe-inline (React style-Props, next/font); Playwright-Prüfung durch Koordinator |
| GAH-304 | AI11 | partial | @axe-core/playwright offline nicht installierbar |
| GAH-305 | AI09 | done |  |
| GAH-306 | AI12 | done |  |
| GAH-307 | AI13 | done | Katalogtest verlangt Gleichheit mit emit-Aufrufen |
| GAH-308 | AI14 | done | 0440 sperrt Schreibzugriffe je Tabelle während des Indexaufbaus; bei großen Tabellen vorab CONCURRENTLY mit gleichem Namen möglich |
| GAH-309 | AI11 | done |  |
| GAH-310 | AI12 | partial | Vitest-Coverage-Schwelle nicht gesetzt (Coverage-Paket fehlt offline); PYSEC-2026-4141 pyjwt in Allowlist, AI12-02 |
| GAH-311 | AI11 | done |  |
| GAH-312 | AI12 | done |  |
| GAH-313 | AI10 | done |  |
| GAH-314 | AI12 | done |  |
| GAH-314 | AI17 | done |  |
| GAH-401 | AI05 | done |  |
| GAH-402 | AI04 | partial | Workbench Mietabrechnung: billing new-version ohne Body-Schema (Folgepunkt billing) |
| GAH-403 | AI04 | done | neuer Code MHVP-HOA-0038 |
| GAH-404 | AI05 | done |  |
| GAH-405 | AI13 | done |  |
| GAH-406 | AI05 | done |  |
| GAH-407 | AI15 | done | AI15 Ordner ai, platform, settings vollständig; AI16 Rest, rund 22 Komponenten weiter ohne Test |
| GAH-407 | AI16 | partial | AI15 Ordner ai, platform, settings vollständig; AI16 Rest, rund 22 Komponenten weiter ohne Test |
| GAH-408 | AI11 | done |  |
| GAH-409 | AI16 | done |  |
| GAH-410 | AI16 | done |  |
| GAH-411 | AI17 | done |  |
| GAH-414 | AI17 | done |  |
| GAH-415 | AI12 | done |  |
| GAH-417 | AI16 | done |  |

## Welle 19 (Stand 1.64.0, 02.10.2026)

Befunde der Lückenanalyse GAG (Prüfung der Masken, Endpunkte und Tests nach Welle 18), Pakete AH01 bis AH20 plus AH21 des Koordinators. Quellen: Ergebnisdateien der Pakete (Feld findings), Versionsverlauf 1.64.0 in `CHANGELOG.md`. Die Freigabestufen G1 bis G5 bleiben geschlossen. Status wie in den Ergebnisdateien: done, partial, not_done.

- Keine Migration und keine Schemaänderung in dieser Welle (letzte Migration bleibt 0438).
- Fachliche Korrektur aus den Tests: POST /banking/csv-mappings akzeptierte das Bankkonto eines fremden Mandanten, weil die Fremdschlüsselprüfung der Datenbank die Zeilensicherheit umgeht; das Konto wird jetzt vorab unter Mandantentrennung geladen (404).
- Neue offene Entscheidungen: AH14-01 bis AH14-07 (Vorlagen in `docs/plans/ENTSCHEIDUNGEN-2026-10-01.md`, Fragen in `docs/OPEN_QUESTIONS.md`).
- Zählung: 39 Befunde, davon 38 done und 1 partial (GAG-16 in AH11 partial, in AH12 done; zusammen abgedeckt). GAG-35 war in keinem Paket enthalten und wurde vom Koordinator als AH21 ergänzt.
- Vom Koordinator bei der Integration erledigt: tsc-Fehler in `apps/web-portal/src/test/serverPage.tsx` behoben, OpenAPI-Export und api-client neu erzeugt (neue Antwortfelder object_period_lock und correction_majority_check, neue Endpunkte objektakte/import-runs, ocr-cache, uprotokoll/files), Hilfeindex und Handbuch neu gebaut, ruff, mypy, eslint, tsc, Gesamtsuiten API, CRM und Portal ausgeführt (Ergebnis siehe Versionsverlauf und Ergebnisbericht). Hinweis aus AH19: Redis bietet nur die Datenbanken 0 bis 15, die Zuweisungen 16 bis 20 im Brief waren ungültig; für die nächste Welle werden Redis-Datenbanken nur im gültigen Bereich vergeben.

| Befund-ID | Paket | Status | Hinweis |
| --- | --- | --- | --- |
| GAG-01 | AH01 | done | Hinweis erscheint an jeder nicht zugeordneten Zeile (IBAN-Abgleich nur serverseitig) |
| GAG-02 | AH01 | done | Kontoart other im Inline-Formular nicht angeboten (wie im Assistenten) |
| GAG-03 | AH02 | done |  |
| GAG-04 | AH02 | done | UPD-Fallback mit echter Bank ungeprüft, BIC bleibt im Fallback leer |
| GAG-05 | AH02 | done |  |
| GAG-06 | AH03 | done | CRM zeigt object_period_lock noch nicht an |
| GAG-07 | AH04 | done | Beobachtung: erneutes Buchen einer gebuchten Buchung liefert 200 (idempotent); CRM muss contract_id mitsenden |
| GAG-08 | AH05 | done |  |
| GAG-09 | AH06 | done |  |
| GAG-10 | AH20 | done |  |
| GAG-11 | AH07 | done | Aufhebung der Sperre bewusst nur in der Buchhaltung (Vier Augen) |
| GAG-12 | AH08 | done | Recht objektakte:update statt des nicht vorhandenen objektakte:write; OCR-Cache wird mandantenweit geleert (Zuordnung Dokument zu Lauf bräuchte Schemaänderung) |
| GAG-13 | AH09 | done | Zuordnungen in ImportRun.summary.assigned_files, Läufe vor Welle 19 ohne Liste |
| GAG-14 | AH10 | done | bank-links und balance-check weiterhin ohne eigene Anzeige |
| GAG-15 | AH05 | done | Anbindung am Aufrufer statements/{id}/new-version; Prüfung gleiche GdWE wie Buchungskreis offen (422 als Folgeschritt); CRM zeigt correction_majority_check nicht an |
| GAG-16 | AH11 | partial | AH11 Teil Bank und Buchhaltung, AH12 Teil Objekte und WEG; JournalEntryForm-Test mit 20 s Timeout unter Last |
| GAG-16 | AH12 | done | AH11 Teil Bank und Buchhaltung, AH12 Teil Objekte und WEG; JournalEntryForm-Test mit 20 s Timeout unter Last |
| GAG-17 | AH13 | done | Kindkomponenten in Seitentests gestubbt |
| GAG-18 | AH14 | done | Entscheidung AH14-01 offen |
| GAG-19 | AH14 | done | Entscheidung AH14-02 offen (G2, M15-01) |
| GAG-20 | AH14 | done | Entscheidung AH14-03 offen (G2, AF07-01) |
| GAG-21 | AH14 | done | Entscheidung AH14-04 offen (M12-05) |
| GAG-22 | AH05 | done |  |
| GAG-23 | AH15 | done |  |
| GAG-24 | AH15 | done | Mandantentrennung bei POST csv-mappings korrigiert (404 statt Übernahme fremder Konten) |
| GAG-25 | AH15 | done |  |
| GAG-26 | AH16 | done | BFF leitet DELETE-Body weiter (route.test.ts) |
| GAG-27 | AH14 | done | Entscheidung AH14-05 offen |
| GAG-28 | AH17 | done | Anzeige rundet auf 3 Nachkommastellen; kein Bearbeiten einzelner Stände (API ohne Endpunkt) |
| GAG-29 | AH18 | done |  |
| GAG-30 | AH19 | done |  |
| GAG-31 | AH20 | done |  |
| GAG-32 | AH19 | done | nur in PortalAccessSection (Kontaktdetail), PortalManagement listet keine Konten |
| GAG-33 | AH14 | done | Entscheidung AH14-06 offen |
| GAG-34 | AH20 | done | Download verlangt tenant_settings:read, Link nicht nach Recht ausgeblendet |
| GAG-35 | AH21 (Koordinator) | done | test_ah21_oidc_userinfo.py: Token, Claims, Mandant nach Wechsel, Token aus dem OIDC-Token-Endpunkt |
| GAG-36 | AH19 | done |  |
| GAG-37 | AH14 | done | Entscheidung AH14-07 offen, Protokollvorlage angelegt |
| GAG-38 | AH17 | done |  |
| GAG-39 | AH20 | done |  |

## Korrektur 1.63.1 (02.10.2026): Hintergrundverarbeitung aus der API

Produktionsbefund nach dem Deploy von 1.63.0: Der Start eines FinTS-Bankdialogs scheiterte mit MHVP-BANK-0057. Ursache war kein Betriebsfehler (Redis und Worker liefen), sondern ein Fehler im API-Prozess: Aufgaben, die ein Endpunkt über `.delay` anstößt, lösen die aktuelle Celery-App auf, und die API hatte die konfigurierte App nie prozessweit gebunden. Der Aufruf ging an die eingebaute Standard-App von Celery (amqp://localhost). Betroffen waren alle Endpunkte mit `.delay` (FinTS-Schritt, finAPI-Abruf, EBICS-Abruf, Mandanten- und Objektakten-Export, Prüfexport, Zählersynchronisation, Belegeingang Paperless); Endpunkte mit `send_task` über `get_celery()` waren nicht betroffen. Korrektur: `get_celery` installiert die konfigurierte App als Standard-App, die API ruft sie beim Start auf, `create_celery` bindet die Thread-lokale App nur noch auf Anforderung. Regressionstest in `tests/unit/test_worker.py`, Testfixtures für FinTS und finAPI patchen nach dem Start der API. Nach dem Deploy ist die Verbindung in der Bankmaske neu zu starten.

## Korrektur 1.63.2 (02.10.2026): FinTS-Umsatzabruf per CAMT

Produktionsbefund nach dem ersten erfolgreichen Bankdialog mit der Volksbank: Kontenliste und Salden kamen an, der Umsatzabruf scheiterte mit MHVP-BANK-0014 ("No supported HIKAZS version found, bank supports ()"). Die Bank bietet MT940 (HKKAZ) nicht mehr an. Korrektur: Fallback auf HKCAZ (camt.052) in `mhvp.banking.fints._fetch_transactions`, neuer Parser `camt.parse_report_entries`, Statusprüfung gebucht oder vorgemerkt in beiden CAMT-Pfaden vereinheitlicht. Regressionstest in `tests/unit/test_fints.py`.

## Bewusst nicht umgesetzt (Welle 18, AG18, 02.10.2026)

- GAA-04 Konto Sonderumlage: wartet auf die Steuerberatung (P07-05, AG18-01). Die Prüfbericht-Warnung bleibt.
- GAB-12 Externes DMS als Primärspeicher: nur Spiegelbetrieb, Entscheidung offen (AG18-02).
- GAB-15 Lokale Einbettung über Ollama: nicht umgesetzt, nur auf Betreiberwunsch (AG18-03).
- GAB-17 GoCardless: nicht umgesetzt, Paket AE24 vom Betreiber gestoppt, Aggregator laut V3 finAPI (AG18-04).
- GAF-29 Platzhaltertexte im CRM: Negativbefund, keine Treffer für TODO, FIXME oder "coming soon" in `apps/web-crm/src`, keine Maßnahme nötig.
- GAF-37 Portal Bestandsfunktionen: Negativbefund. Die Terminbestätigung durch Bewohner ist bereits eingebunden (`AppointmentProposals` in `apps/web-portal/src/app/(portal)/meldungen/[id]/page.tsx`), keine Änderung nötig.
- AF08-R: Job-Schlüssel `hoa-inspection-ownership-scan` ist in `JOB_CATALOG` registriert (Mandanten-Zeitfenster möglich). Offen: GAE-11 (Ende zu Ende Test Jahresabrechnung mit gebundener Zahlung) und GAE-12 (Anbindung Planübernahme an `calc.allocation_owner`).
- AF24-R: `scripts/staging-smoke.sh` prüft `MHVP_AVAILABILITY_*_URL` optional (nur lesend).
