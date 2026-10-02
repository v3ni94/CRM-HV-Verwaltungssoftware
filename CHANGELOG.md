# Versionsverlauf MH Verwaltungsplattform

Schema MAJOR.MINOR.PATCH: erste Stelle (2.0, 3.0) für grundlegende Umbauten, zweite Stelle
(1.1, 1.2) für neue Funktionen oder Module, dritte Stelle (1.2.1, 1.2.2) für kleine
Korrekturen. Die aktuelle Nummer steht in `VERSION`, die Oberfläche zeigt sie im Footer und
unter `/version` (Quelle `apps/web-crm/src/lib/changelog.ts`). Neue Einträge oben anfügen.

## 1.64.0 (02.10.2026) Welle 19, Befunde der Lückenanalyse GAG: FinTS-Kontoeinrichtung aus der Bankzeile, Fallbacks im Bankabruf, Periodensperren und CO2-Aufteilung in der Abrechnung, Zählerstände, Löschungssperren, Importverläufe und breite Testabdeckung

- Übersicht: Welle 19 mit 20 Paketen AH01 bis AH20 zu den 39 Befunden der Lückenanalyse GAG (38 done, 1 partial, GAG-35 vom Koordinator als Paket AH21 ergänzt); keine Migration, kein Schemaeingriff; die Freigabestufen G1 bis G5 bleiben geschlossen.
- Bank: Nicht zugeordnete FinTS-Konten zeigen einen Sprung in den Einrichtungsassistenten, der das Konto vorbelegt und direkt Schritt 3 öffnet; ein internes Konto lässt sich direkt in der FinTS-Zeile anlegen und zuordnen, der Rechtsträger folgt aus Objekt und Kontoart.
- Bank FinTS: Der Abruf bricht ohne Saldoabruf (HKSAL) nicht mehr ab, fehlt der Saldo wird der Schlusssaldo aus dem camt.052-Bericht übernommen, ein Banksaldo wird nie überschrieben; Banken ohne SEPA-Kontenliste (HKSPA) werden über die Kontodaten der Bank (UPD) gelesen; leere MT940-Antworten gelten als keine Umsätze.
- Bank: Kontierungsvorschläge eines Umsatzes zeigen eine aktive Objekt-Periodensperre an (object_period_lock, MHVP-ACC-0030); ignorierte Umsätze lassen sich in der Umsatzliste mit Begründung wieder eröffnen.
- Bank: Das Speichern eines CSV-Mappings prüft das Bankkonto unter Mandantentrennung und lehnt fremde oder unbekannte Konten mit 404 ab (Befund aus den neuen Endpunkttests, zuvor umging die Fremdschlüsselprüfung die Zeilensicherheit).
- Betriebskosten: Die Abrechnungsmaske zeigt den Sperrstand samt Schalter Sperre beim Abschluss und sperrt den Abrechnungszeitraum mit Grund; neuer Bereich CO2-Kostenaufteilung berechnet Mieter- und Vermieteranteil nach Stufentabelle ohne Speicherung und ohne Buchung.
- WEG: Eine neue Abrechnungsversion mit Korrekturbeschluss liefert die Mehrheitsprüfung des Beschlusses mit (nur Anzeige, keine Statusänderung); die Mehrheitsprüfung lehnt unbekannte Abfrageparameter ab; Integrationstest Jahresabrechnung mit zweckgebundener Rücklagenzahlung über Kontoauszugsimport und Bankbuchung.
- Kautionen: Gespeicherte Abrechnungsentwürfe lassen sich im Vertrag als PDF-Vorschau öffnen, ohne Ablage, Versand oder Buchung; Integrationstest der Kautionsabrechnung mit Umbuchung im Gesamtablauf (Freigabe hinter G3, Buchung und Storno hinter G1).
- Objekte: Der Abschnitt Zähler zeigt je Zähler die Zählerstände und erlaubt mit Schreibrecht das Erfassen mit Datum, Wert, Quelle und Kennzeichen Geschätzt; unplausible Stände werden markiert.
- Dokumente: Die Karte Aufbewahrung und Sperren setzt eine Löschungssperre mit Art und Begründung und hebt sie mit Begründung auf (Vier-Augen-Prüfung der API); das BFF leitet bei DELETE einen vorhandenen JSON-Body an die API weiter.
- Objektakte: Neue Liste der Importläufe mit Status, Datum und Zahlen, neuer Endpunkt zum Leeren des übernommenen OCR-Textes (protokolliert), Verlauf und Vorschaubild-Übernahme in den Einstellungen.
- Übergabe und Altdaten: Zuordnungen der U-Protokoll-Dateien lassen sich je Importlauf auflisten und lösen (Dokument bleibt erhalten); der Bereich Altdaten zeigt je Buchungskreis die Summen der übernommenen Einzelposten je Art.
- Tickets und Kontakte: Im Ticketdetail lässt sich ein Stammdatenvorschlag aus der letzten eingehenden E-Mail berechnen, er bleibt ein prüfbarer Vorschlag; der Abschnitt Portalzugang bietet Berechtigungen neu ableiten mit Anzeige der aktiven abgeleiteten Freigaben.
- Automatisierung und Kalender: Regelvorlagen werden in den Einstellungen als inaktive Regel übernommen; die Kalenderseite bietet den Download als ICS-Datei.
- Plattform: Ein Test stellt sicher, dass jeder Fehlercode im Problemregister nur einmal vergeben ist; der Fristen-Snapshot-Test (AF14) und die Tests zu sachlicher Prüfung und SEPA-Mandaten (AF07) laufen gegen die vollständige Migrationskette.
- Tests: Endpunkttests für KI-Kontierung, CSV-Mappings, Magic-Link-Bestätigungscode, OIDC userinfo, Messdienstbestätigung und Verbrauchsimport, lexoffice push-batch und link-recipient, Abnahmeprotokoll der Migration, Demo-Kennzeichen in /auth/me; Komponententests für die übrigen Masken in Bank, Buchhaltung, Objekte und WEG sowie Seitentests für alle Portalseiten.
- Dokumentation: Sieben Entscheidungsvorlagen AH14-01 bis AH14-07 (Versicherungs-Router, Zahlungslaufmasken, B2B-Sperrcode, Vier-Augen-Antrag der Ausgangsautomatik, download-url und mirror, KI-Vorqualifizierung im Portal, Abnahmeprotokoll Anhang D) und die Protokollvorlage PROTOKOLL-ANHANG-D-VORLAGE.md mit den Fällen D01 bis D58.

## 1.63.2 (02.10.2026) Korrektur Bankabruf FinTS: Umsätze per CAMT, wenn die Bank kein MT940 mehr anbietet

- Bank FinTS: Banken, die den MT940-Umsatzabruf (HKKAZ) nicht mehr anbieten (Meldung "No supported HIKAZS version found", MHVP-BANK-0014, betrifft Volks- und Raiffeisenbanken auf Atruvia), werden jetzt automatisch über den CAMT-Abruf (HKCAZ, camt.052) gelesen; Kontenliste und Salden waren davon nicht betroffen.
- Bank: Der CAMT-Parser wertet den Buchungsstatus auch in der Textform (Sts BOOK oder PDNG ohne Code) aus; vorgemerkte Umsätze wurden in dieser Form bisher als gebucht eingelesen. Betrifft den Dateiimport CAMT.053 und den neuen FinTS-Abruf.

## 1.63.1 (02.10.2026) Korrektur Hintergrundverarbeitung aus der API (FinTS-Dialog, Exporte, Zählersynchronisation)

- Bank FinTS: Der Start eines Bankdialogs scheiterte in der Produktion mit MHVP-BANK-0057, weil der API-Prozess die konfigurierte Celery-App nie als Standard-App gebunden hatte und Aufgaben über .delay an den eingebauten Standardbroker (amqp://localhost) übergab; die API bindet die konfigurierte App jetzt beim Start prozessweit, betroffen waren alle Aufgaben, die ein Endpunkt über .delay anstößt (FinTS-Schritt, finAPI-Abruf, EBICS-Abruf, Mandanten- und Objektakten-Export, Prüfexport, Zählersynchronisation, Belegeingang Paperless).
- Technik: create_celery bindet die Thread-lokale aktuelle App nur noch auf ausdrückliche Anforderung, get_celery installiert die prozessweite Standard-App; Regressionstest prüft die Auflösung aus einem fremden Thread, die Testfixtures für FinTS und finAPI patchen erst nach dem Start der API.

## 1.63.0 (02.10.2026) Welle 18, Befunde der Lückenanalyse GAA bis GAF: führendes System je Vorgangstyp, Stapelverarbeitung der KI, Umlaufbeschluss und Belegeinsicht im Eigentümerportal, Ausgangsautomatik nur per Antrag

- Betrieb: Messlauf GAE-32 mit MHVP_PERF=1 dokumentiert (Kontaktliste P95 47 ms, 200.000 Journalzeilen mit aktivem Wächter in 16,0 s), Playwright Kernpfade beider Apps gegen die API ausgeführt (GAE-39).
- Übersicht: Welle 18 mit 20 Paketen AG01 bis AG20 zu den offenen Befunden der Lückenanalyse GAA bis GAF und den Rückständen aus Welle 17 (41 Befunde, davon 30 done und 11 partial); Migrationen 0419 bis 0438, real sind 8 (0420 führendes System, 0422 Stapelverarbeitung der KI, 0424 Auftragsbewertung, 0425 Umlaufbeschluss im Portal, 0427 Belegeinsicht, 0430 Abrechnungen der Gemeinschaft, 0437 Ziel des Automatikantrags, 0438 Zuordnungsvorschlag), die übrigen 12 sind Platzhalter ohne Schemaänderung; die Freigabestufen G1 bis G5 bleiben geschlossen.
- Datenbank: Migration 0424 liest den Namen der Check-Constraint aus dem Katalog, weil die Namenskonvention den Namen verdoppelte und das Upgrade auf frischer Datenbank scheiterte.
- Betriebskosten: Der Abnahmefall D24 ist je Variante des Schalters für offene Vorauszahlungen geprüft (Gesamtanspruch 20,00 EUR, kein doppelter Anspruch), der strikte Defekttest entfällt, der Standard bleibt Information; AC10-01 und M17-03 bleiben offen.
- Buchhaltung: Führendes System je Buchungskreis, Objekt, Vorgangstyp (Sollstellung, Mahnung, Lastschrift, Zahlungsauftrag) und Gültig-ab, Umschaltung nur per Antrag mit Freigabe durch eine zweite Person und G1 für die Plattform (Migration 0420).
- Buchhaltung: Mahnlauf, Lastschriftlauf, Zahllauf, automatische Bankbuchung und Sollstellungslauf prüfen das führende System über eine zentrale Funktion; ohne Umschaltung bleibt das Verhalten unverändert.
- CRM Buchhaltung: Abschnitt Führendes System je Vorgangstyp im Buchungskreis mit Anzeige, Antrag und Freigabe.
- Buchhaltung: Neue Leseliste der Zuordnungen von Zahlungsart zu Erlöskonto, die Kontenmaske zeigt die bestehenden Zuordnungen an.
- Buchhaltung: Der Excel-Export von Journal, Monatsmatrix und Einnahmen Ausgaben unterstützt den Filter property_id.
- Lastschrift: Neue Leseliste der Gläubiger-IDs, Anzeige unter Bank, Verbindungen und in den Einstellungen.
- Rechnungen: Der Budgetabgleich der sachlichen Prüfung zeigt Rechnungen, Gutschriften und Buchungszeilen mit Plankonto als Teilbeträge.
- Bank: Der automatische Buchungsverifier überspringt Umsätze, deren Objekt am Buchungstag durch eine aktive Objektsperre (Modus object_period) gesperrt ist.
- Bank: Die Ausgangsautomatik lässt sich nur noch über einen Antrag mit Freigabe durch eine zweite Person bei offener G1 einschalten; PUT /banking/automation/outgoing schaltet nur aus und lehnt das Einschalten mit MHVP-BANK-0064 ab.
- Bank: Anträge zum Automatikschalter tragen ein Ziel (Hauptschalter oder Ausgangsautomatik), je Ziel ist ein Antrag offen (Migration 0437).
- CRM Bank: Die Seite Automatikschalter hat einen Abschnitt Ausgangsautomatik zum Beantragen und sofortigen Ausschalten.
- Bank: EBICS Schlüsselwechsel und Sperre sind lokal per Integrationstest abgesichert (Status je Teilnehmer, Abruf und Aufträge bis zur erneuten Bankschlüsselprüfung oder dauerhaft gesperrt); die Abnahme am Testsystem der Bank bleibt Betreiberaufgabe mit Checkliste im Handbuch.
- KI: Die OpenAI-Anbindung nutzt die Responses API mit strikten Structured Outputs und fällt bei Client-Fehlern einmal auf Chat Completions zurück.
- KI: Zurückgestellte nächtliche Läufe können je Anbieterkonfiguration als Anthropic Message Batch gesendet und stündlich abgerufen werden (Schalter batch_enabled, Standard aus, Migration 0422, ADR 0025).
- KI: Der Preisfaktor für Stapelläufe gilt je Anbieterkonfiguration (Standard 1, kein Abschlag) und nur für vollständig aus dem Stapel beantwortete Läufe.
- CRM KI: Die Anbietereinstellungen enthalten Schalter Stapelverarbeitung und Preisfaktor.
- KI: Die Maskierung in Objektakte und Belegen ersetzt IBAN-förmige Zeichenfolgen nur noch bei realer IBAN-Länge (15 bis 34 Zeichen ohne Trenner), Dateinamen wie WE12.pdf bleiben für die Klassifikation lesbar.
- Berechtigungen: Der Mandantenschalter insurance_broker_access (Standard aus) gibt der Rolle Versicherungsmakler lesend insurance:read und claims:read; die Rollenauswahl kennzeichnet sie als ohne Zugriff, die Fachendpunkte sind noch nicht angeschlossen.
- Plattform: Maske für die Plattformeinstellungen (Schalter gate_superadmin_bypass) unter /plattform.
- Einstellungen: Die Zuordnungsschwellen des Personenabgleichs der Objektübernahme stehen als Regeln unter Fachliche Regeln.
- Aufträge: Bewertung abgeschlossener Aufträge je Partei (Verwaltung und betroffener Bewohner), einmalig, über POST /work-orders/{id}/rating und POST /portal/work-orders/{id}/rating (Migration 0424, Doppelbewertung 409).
- Portal: Bewertungsformular in der Meldung für abgeschlossene Aufträge; der Durchschnitt des Dienstleisters erscheint nur bei provider_rating_display = all und nie für Dienstleister.
- CRM: Die Auftragsseite zeigt Bewertungen gemäß Schalter und erlaubt der Verwaltung die Bewertung.
- WEG/Portal: Eigentümer stimmen in laufenden Umlaufverfahren im Portal je Einheit und Antrag einmal ab, mit Nachweis aus Zeitpunkt, Portalbenutzer und Prüfsumme des Antragstexts, nur mit Mandantenschalter portal_circular_resolution_enabled (Standard aus, Migration 0425) und G4.
- Portal: Neue Seite Umlaufbeschlüsse mit Stimmabgabe und Nachweisanzeige; Portalstimmen fließen nicht automatisch in die Ergebnisfeststellung ein.
- WEG/CRM: Das Formular Umlaufbeschluss erfassen zeigt die Stimmen aus dem Eigentümerportal lesend, der neue Schalter steht unter Fachliche Regeln.
- Portal: Neue Seite Reporting mit Endpunkt /portal/owner/rental-reporting zeigt Eigentümern mit Sondereigentumsverwaltung Monatsmiete, umlagefähige Kosten und Leerstandstage je Abrechnungszeitraum, nur mit owner_rental_income_enabled und G3.
- Portal: Neue Seite Belegeinsicht für Eigentümer mit Suche nach Abrechnungsjahr und Bezeichnung, hinter portal_owner_receipts_enabled (Standard aus, Migration 0427) und G4, Abruf über die bestehende Dokumentberechtigung mit Lesevermerk.
- Portal: Eigentümer reiner Mietverwaltungen erhalten einen Zugriff auf ihren eigenen Rechtsträger und sehen ihre Eigentümerabrechnung; der Zugriff endet mit dem Eigentumszeitraum.
- Portal: Die Eigentümerabrechnung zeigt nur Abrechnungen des eigenen Rechtsträgers, Abrechnungen der Gemeinschaft nur mit owner_hoa_rental_statements_enabled (Standard aus, Migration 0430); der Schalter steht in den Portalfunktionen und unter Fachliche Regeln.
- Abrechnung: Die Abrechnungswerkbank zeigt lesend die aktiven Periodensperren des Objekts.
- WEG: Der Mandantenschalter hoa_allocation_proposal_setting (Standard aus, Migration 0438) zeigt in der Vorschau der Planübernahme und je Abrechnung den Eigentümer nach der Regel je Erwerbsart neben dem verwendeten Eigentümer, ohne Buchung.
- WEG: Integrationstest der Jahresabrechnung mit gebundener Rücklagenzahlung (200,00 EUR), ungebundener Zahlung (50,00 EUR) und Aufteilungsvorschlag nach Planverhältnis (30,00 EUR und 20,00 EUR).
- Auth: GET /auth/me liefert is_demo aus dem Mandanten, das Demo-Band erscheint damit für Demo-Mandanten.
- CRM Lexware Office: Export von Kontakten und Rechnungen mit Auswahl, Zeitraum, Vorschau und Download des Ergebnisses.
- CRM Übergabe: Dateien aus dem Übergabeprotokoll lassen sich per ZIP dem Importlauf zuordnen; Liste und Lösen fehlen in der API.
- CRM Vermietung: Die OpenImmo-Übernahme bietet Auswahllisten für Objekt und Einheit.
- CRM Import: Neue Seite Übernahme aus objektakte mit Importlauf (Vorschau, Übernahme, Ergebnis), OCR-Cache-Zuordnung und Vorschaubild-Übernahme; das Leeren des OCR-Cache fehlt in der API.
- CRM Migration: Abnahmeprotokolle im Entwurf lassen sich bearbeiten, Altdaten (Einzelposten und Tickets) sind lesend einsehbar, das Vollimport enthält die Liste der bekannten Exporttypen mit erwarteten Spalten.
- Automation: Der Job-Schlüssel hoa-inspection-ownership-scan ist im Jobkatalog registriert.
- Skripte: staging-smoke prüft optional die URLs MHVP_AVAILABILITY_*_URL.
- Tests: 21 weitere Komponententests (CRM Bank, Buchhaltung, WEG, Objekte; Portal Einladung annehmen) mit Prüfung von BFF-Pfad, Fehleranzeige und Berechtigungsfall.
- Handbuch: Kapitel zu Objektakte-Einstellungen, Migrationsmasken, Demo-Band, API-Schlüsseln und Mailquellen ergänzt, Portal-Kapitel vom CRM abgegrenzt.
- Dokumentation: Entscheidungsfragen AG18-01 bis AG18-04 und Abschnitt Bewusst nicht umgesetzt in docs/plans/IMPLEMENTATION_STATUS.md.
- Offen: AG02-01 (Zuordnung der Bank-Autobuchung zum Vorgangstyp Sollstellung, Frage A17), AG04-01 (AVV-Abdeckung für Stapelergebnisse beim KI-Anbieter und vertraglicher Preisfaktor) und AG07-01 (Zulässigkeit der Portal-Stimmabgabe als Textform, Übernahme in die Ergebnisfeststellung, G4).
- Offen: AG09-01 (Umfang der Einsicht in Kostenbelege), AG12/AF25-02 (Abrechnungen der Gemeinschaft im Eigentümerportal, G3), AG14-01 (Mapping je Datensatz im Lexware Export, Liste und Lösen der Übergabedateien) und AG20-01 (Regel je Erwerbsart und Fälligkeitstag des Abrechnungsergebnisses, G4).
- Offen: AG18-01 bis AG18-04 (Sonderumlagekonto, DMS als Primärspeicher, lokale Einbettung, Aggregator), GAC-07 (Umfang, Datenschutzgrundlage und Zugriffsweg des Versicherungsmaklers) und AF01-01-V (fachliche Freigabe der Ausgangsautomatik, M12-05, G1).
- Bewusst nicht umgesetzt: GoCardless (vom Betreiber gestoppt, finAPI nach V3), DMS als Primärspeicher, lokale Einbettung, Sonderumlagekonto (Steuerberatung).

## 1.62.0 (02.10.2026) Welle 17, Befunde der Lückenanalyse GAA bis GAF und Prüfung: Buchungsautomatik nur per Antrag, Periodensperre über die Objektspalte, EBICS-Abruf, Abrechnungen im Eigentümer- und Mieterportal, asynchroner Portal-Assistent

- Übersicht: Welle 17 mit 24 Paketen AF01 bis AF24 zu den Befunden der Lückenanalyse GAA bis GAF und Prüfbericht REVIEW-W17-2026-10-02 (AF25, 5 Prüfbefunde, 2 behoben); Migrationen 0395 bis 0418, real sind 5 (0398, 0402, 0409, 0410, 0411), Platzhalter ohne Schemaänderung sind 19 (0395, 0396, 0397, 0399, 0400, 0401, 0403, 0404, 0405, 0406, 0407, 0408, 0412, 0413, 0414, 0415, 0416, 0417, 0418); 95 Befunde, davon 74 done und 18 partial; neue offene Entscheidungen (9): AF01-01, AF02-01, AF06-01, AF06-02, AF07-01, AF08-01, AF10-01, AF15-01, AF16-01.
- WEG: Die Ablage der Einzelabrechnungen bei Ausgabe und Fälligstellung ist eine Zusatzkopie; ohne konfigurierten Dokumentenspeicher findet der Statuswechsel trotzdem statt und die PDF wird beim ersten Abruf archiviert (Protokollhinweis statt MHVP-DOC-0007).
- Datenbank: Rückmigration von 0398 behält Periodensperren aus WEG-Abrechnungen als Quelle statement und hebt FORCE RLS nur für diese Transaktion auf; zuvor blieb die Datenbank bei vorhandenen Sperren halb migriert.
- Bank: Die Buchungsautomatik lässt sich nur noch über einen Antrag mit Freigabe durch eine zweite Person bei offener G1 einschalten; PUT /banking/automation schaltet nur aus und lehnt das Einschalten mit MHVP-BANK-0063 ab.
- Bank: Automatikschalter in der Oberfläche mit Schaltfläche Sofort ausschalten; die Karte auf der Seite Bankregeln zeigt Haupt- und Ausgangsautomatik und verweist auf den Antragsweg.
- Bank: Ereignis bank_transaction.booked auch bei automatischer Buchung, Ausführung eines Zahlungsauftrags und Korrektur aus der Nachkontrolle, im Webhook-Katalog wählbar.
- Betrieb: Neue Alarmmetrik payment_run_failed_24h; fehlgeschlagene geplante Zahllauf-Vorschauen werden mit Fehlertext gespeichert.
- Bank: Täglicher EBICS-Kontoauszugsabruf als Hintergrundaufgabe je Teilnehmer mit drei Wiederholungen; ohne Übertragung MHVP-BANK-0050 im Protokoll.
- Bank: Sync-Protokoll mit Zeitpunkt, Quelle, Status, Zählern und Fehlern auf der Seite Bank.
- Bank: INI-/HIA-Brief als PDF auf dem Briefbogen, Hash-Werte nur aus der Übertragung.
- Bank: FinTS-Zieladresse wird nach Namensauflösung auf öffentliche Adressen geprüft (MHVP-BANK-0062).
- Bank: Maske Bankverbindungen mit Sync-Protokoll, Schalter und Entscheidungsprotokoll je Umsatz.
- Bank: Zahlungsdateien (Sammler) unter Zahlungen nur lesend angezeigt, Erzeugen und Einreichung bleiben hinter G2.
- Buchhaltung: Gläubiger-ID je Rechtsträger in den Einstellungen pflegbar.
- Lastschrift: Vorschau einziehbarer Sollstellungen und Vorabinformation als Entwurf im Lastschriftlauf.
- Buchhaltung: Die Periodensperre je Objekt liest das Objekt direkt aus der Buchungszeile, auch Zeilen ohne Einheit sind gesperrt.
- WEG: Der Abschluss der Hausgeldabrechnung setzt mit dem Schalter auto_lock_on_close eine Periodensperre des Kalenderjahres für das Objekt (Migration 0398).
- Buchhaltung: Die Honorarbuchung prüft die Objektsperre bereits beim Erzeugen der Entwürfe.
- Buchhaltung: Der Storno einer Buchung storniert noch nicht übergebene Zahlungsaufträge ihrer Posten und Rechnungen und wird bei an die Bank übergebenen Aufträgen abgelehnt.
- Buchhaltung: Umbuchungsentwürfe freigegebener Guthabenposten lassen sich nicht mehr direkt löschen, die Rücknahme läuft über den Posten.
- CRM Buchhaltung: Objektfilter in Monatsmatrix, Einnahmen und Ausgaben und Journal, Objektwahl je Buchungszeile, neue Auswertungen Driftbericht Zeilenobjekt, Umsatzsteuer je Objekt und Offene Posten Salden.
- CRM Kontenplan: Steuerkennzeichen je Konto, Erlöskonto je Zahlungsart und Aktion Debitorenkonten aus Verträgen übernehmen.
- CRM Rechnungen: Schaltfläche Zweite Freigabe über der Betragsgrenze.
- CRM Kautionen: Bewegungen erfassen und Jahreslauf der Zinsentwürfe, BFF-Allowlist ergänzt.
- Buchhaltung: G1-Checkliste zeigt den Stand des Abnahmeregisters lesend mit Link zum Register.
- Buchhaltung: Dauerrechnung erzeugen bleibt Entwurf mit Planentwurfsnummer und wird im Modus Ablehnen bei geschlossenem G1 abgewiesen.
- Verträge: Nummernmodus der Mietrechnungsentwürfe nur mit Recht Mandanteneinstellungen ändern, sonst Anzeige.
- Verwalterhonorar: XRechnung Gutschrift mit XML, Prüfung und Ablage je Honorargutschrift.
- Steuern: Ausweis nach § 35a je Mietvertrag mit Anzeige und PDF Entwurf.
- Zahllauf: Einstellung der wöchentlichen Vorschau in der Oberfläche.
- Kontakte: SEPA-Mandate mit Verfahren B2B werden bei der Erfassung mit MHVP-CONT-0033 abgewiesen und im Formular als nicht unterstützt gekennzeichnet.
- Lastschriften: Der Sperrgrund für Nicht-CORE-Mandate nennt ausdrücklich, dass die B2B-Firmenlastschrift nicht unterstützt wird.
- Rechnungen: Der Budgetabgleich der sachlichen Prüfung zählt Gutschriften negativ und gebuchte Journalzeilen ohne Rechnungsbezug auf dem Konto der Planposition mit und zeigt die Teilbeträge.
- Handbuch: Betriebsauswirkung der Standardsperre der Umlagegrundlagen beschrieben.
- WEG: Ein erfasster Eigentümerwechsel erzeugt in offenen Einsichtsanfragen der bisherigen Eigentümerseite einen Prüfhinweis, ohne die Anfrage zu schließen (stündlicher Job und Prüfaufruf).
- WEG: Die Datenbank lässt je Abstimmungspunkt und Einheit nur eine gezählte Stimme zu; Konfliktvorgänge bleiben erhalten, die Migration bricht bei Bestandsdubletten ab statt Daten zu löschen.
- WEG: Der Korrekturbericht je Eigentümer steht hinter einem Mandantenschalter, Standard aus, einstellbar unter Fachliche Regeln.
- WEG: Neue Integrationstests für Rücklagenbindung fremder Gemeinschaften und die Sonderumlagen-Differenz nach Eigentümerwechsel je Zuordnungsvariante.
- WEG Versammlung: Empfängerliste der Einladung und Störungsprotokoll der Online-Versammlung mit Erfassung in der Versammlungsmaske.
- WEG Abrechnung: Korrekturbericht je Eigentümer mit Heizkostenüberleitung und Übernahme von Kosten aus gebuchten Belegen (costs/from-ledger).
- WEG Rücklagen: Änderungen des Anfangsbestands in der Rücklagenansicht freigeben oder ablehnen.
- Dokumente: Jedes neu angelegte Dokument erzeugt zentral genau ein Ereignis document.created, unabhängig von der Quelle.
- Dokumente: Nach der Paperless-Spiegelung wird der Volltext übernommen, solange die Texterkennung aussteht; die Detailseite zeigt bis dahin einen Hinweis.
- Dokumente: Neuer Mandantenschalter Belegerfassung nach Ablage einer Rechnung (Standard aus) startet die Rechnungsauslesung als Vorschlag; sonst Schaltfläche Beleg erfassen am Eingangsvorschlag.
- Dokumente: Objektakte-Import stellt Dokumente aus dem Papierkorb protokolliert wieder her statt mit Konflikt abzubrechen; der Mandantenexport enthält Papierkorbdokumente.
- WEG: Einzel- und Gesamtabrechnungs-PDFs werden einmalig im Dokumentenarchiv abgelegt und mit Abrechnung, Objekt, Gemeinschaft, Einheit und Eigentümer verknüpft; jeder weitere Abruf im CRM und Portal liefert die abgelegte Datei.
- Dokumente: Verknüpfungsziel hoa_statement ergänzt.
- Textbausteine: Mandantenschalter Zweitpersonprüfung (Standard an) mit Begründungspflicht beim Abschalten und Audit-Ereignis.
- Mieter-Anschreiben: Baustein letter_notice wird nur in freigegebener Fassung gedruckt, sonst Platzhalter Text nicht freigegeben.
- Ablage: Integrationstest für Informationsblatt-PDF mit freigegebenem Text.
- Dokumente: Briefbogen bettet Liberation Sans oder DejaVu Sans ein (Pfad über MHVP_PDF_FONT_DIR konfigurierbar), Helvetica nur noch als Fallback
- Infrastruktur: API-Image installiert fonts-liberation und fonts-dejavu-core
- Buchhaltung: PDF/A-3-Vorprüfung der ZUGFeRD-Rechnung ohne Schriftblocker bei eingebetteter Schrift, im Fallback mit Installationshinweis
- Billing: Prüfpunkte des Regelregisters lassen sich im CRM mit Name und Datum der fachkundigen Prüfung bestätigen.
- Billing: Neue Seite Einstellungen Abrechnung zur Pflege der Heizkosten-Regeltabellen (ohne Vorbelegung, Quelle Pflicht) und der Kostenart je Kostenkonto.
- Billing: Abrechnungswerkbank erfasst Belegeinsicht je Einheit und erzeugt Ergebnisbuchungen als Entwurf im Status fällig (Gate G3 bleibt).
- Billing: Integrationstest für Fristübersicht und Beat watch_tenant mit echtem Snapshot.
- Portal: Eigentümer sehen ausgegebene Eigentümerabrechnungen Miete und SEV ihrer eigenen Rechtsträger mit PDF, hinter Freigabestufe G3 und neuem Mandantenschalter (Standard aus).
- Portal: Hausgeldabrechnung erhält je Einheit eine Erläuterung (Kostenanteil, Vorschüsse Soll und Ist, Abrechnungsspitze, Rücklage) aus dem Snapshot, hinter G4.
- Portal: neue Seite Wirtschaftsplan mit beschlossenen Plänen und Beträgen der eigenen Einheiten, hinter G4.
- Portal: Hinweis bei leerer Mieterträge-Liste und Direktlink auf die Nutzungsbedingungen in der Annahmemaske.
- CRM: Schalter Eigentümerabrechnung im Eigentümerportal in Portalfunktionen und Fachlichen Regeln.
- Portal: Mieter sehen die ausgegebene Betriebs- und Heizkostenabrechnung ihres eigenen Vertrags mit Positionen, eigenem Anteil, Erläuterungen aus freigegebenen Textbausteinen und PDF-Abruf (Schalter Standard aus, G3).
- Portal: Abruf der Mieterabrechnung wird als Indiz vermerkt (keine Zustellung).
- Dokumente: neue Textbausteincodes portal_tenant_statement_key, _consumption, _advance, _balance.
- Portal: Der Assistent beantwortet Fragen asynchron als Job im Worker (Statusabfrage, Zeitlimit 120 Sekunden, kein doppelter Anbieteraufruf, Berechtigungsfilter unverändert); Migration 0411.
- CRM: Support-Ansicht je Portalzugang im Kontakt (lesend, Pflichtgrund, Protokoll).
- CRM: Arbeitsvorrat Offene Zuordnungsprüfungen für Tickets und E-Mails auf der Startseite.
- Dokumente: Neue Maske Eingangsvorschläge unter /dokumente/eingang zum Annehmen, Ablehnen, Bestätigen von Folgeaktionen und Zurücknehmen automatischer Ablage.
- Objektakte: Pflichtunterlagen je Verwaltungsart und Status des lokalen Klassifikationsmodells in den Einstellungen.
- Import: Migrationsabnahme je Objekt, Journalspalten und Jahresausgaben unter /importe/migration.
- CRM Kontakte: Widerspruch kann in der Kontaktakte erfasst werden, Rechtsgrundlage auf Fachliche Regeln auf Standard zurücksetzbar.
- CRM Einstellungen: neue Seiten Mailquellen (Geheimnis erneuern, Empfangsprotokoll) und API-Schlüssel (Präfix, Widerruf, Einmalanzeige).
- CRM Shell: Hinweisband für Demo-Mandanten in der Kopfzeile.
- CRM Vermietung: Besichtigungstermine je Interessent, Makler Konfiguration und OpenImmo Import sind in der Oberfläche bedienbar.
- CRM Übergabe: Import aus U-Protokoll (Vorschau, Übernahme) und Mängel als Tickets anlegen.
- CRM Lexware Office: Laufprotokoll und manueller Beleg Abruf in den Einstellungen.
- CRM KI: Schalter für schnellen Tabellenimport und Hilfreich Bewertung am Wissenseintrag.
- CRM Datenqualität: Datensatzprüfung starten und Kontaktrollen neu berechnen.
- CRM BFF: Allowlist um Besichtigungen, Makler, OpenImmo, U-Protokoll, Lexware Import/Export, Tabellenimport und Datenqualität erweitert.
- Import: GET /imports/{id}/undo-preview zeigt vor der Rücknahme je Datensatz, ob er entfernt wird oder mit Grund bestehen bleibt; das CRM nutzt dafür einen Dialog statt window.confirm.
- KI: make ai-eval prüft zusätzlich classify_document, call_summary und rent_increase_check mit je mindestens 22 synthetischen Fällen und eigenen Scorern.
- Platform: neue Massenendpunkte POST /units/bulk (Geschoss, Lage, Ausstattung) und POST /documents/bulk-link (Anlage) mit Teilerfolgsbericht, ohne Geldwirkung.
- Portal: die Annahme einer Portaländerung (E-Mail, Telefon, Bankverbindung, Adresse) löst zusätzlich contact.updated mit Feldnamen aus, damit Webhook-Abonnenten sie erhalten.
- Hilfe: Das Handbuch ist im CRM unter /hilfe mit Kapitelübersicht, Volltextsuche und Abschnittsankern lesbar, erzeugt aus docs/handbuch durch scripts/build_handbook.py, Aktualität wird in make lint geprüft.
- Datenschutz: Das Verzeichnis erkennt Schadenstool, Makler-CRM, Webhook-Ziele sowie EBICS und FinTS und zeigt je Dienst lesend die Rechtsgrundlage der Einwilligungszwecke.
- Doku: README zur Observability korrigiert, ADR 0024 (OTel-Collector und Uptime Kuma), Nachträge zu W09-01, P08-01 und P07-01.
- Tests: 25 neue Komponententests (CRM: ai, banking, accounting, hoa, documents; Portal: Beschlüsse, Ansprechpartner, Ticketkommentare, Zählerstand, Hausgeldkonto, Support-Einwilligung, Anmeldelink, Abmeldung) mit Prüfung von BFF-Pfad, Fehleranzeige und Berechtigungsfall.
- Import: Verwaltungsansicht der gemerkten Spaltenzuordnungen mit Entfernen auf der Immoware24 Importseite.
- Buchhaltung: neuer lesender Endpunkt GET /accounting/interest-tax-config mit Stand der Steuerkonten über alle Buchungskreise.
- Fachliche Regeln: Zinsabzug und Textbausteine zeigen ihren Stand als Zahl statt nur als Link.
- Plattform: Warnung im Log bei fehlenden Variablen der Verfügbarkeitsmessung und Integrationstest mit echtem HTTP Server auf 127.0.0.1.
- Banking: Der tägliche Bankabgleich übersprang bereits in 1.61.1 FinTS; in dieser Fassung bleiben auch konfigurierte EBICS-Teilnehmer unberührt, nicht eingerichtete EBICS-Verbindungen behalten den Hinweis.
- CRM: Doppelte Übersetzungs-Namensräume (BankConnections, Plattformaudit) sind zusammengeführt; die Chat-Vorschläge unterscheiden Rechnungsprüfung und Plattformaudit.
- Portal: Der EUR-Formatierer liegt in einem serverfähigen Modul; die Wirtschaftsplan-Tabellen der Eigentümerseite sind horizontal scrollbar.
- Tests: Typfehler in 18 neuen Komponententests behoben, Integrationstest Mieterportal-Nebenkostenabrechnung lauffähig gemacht.
- Migrationen: Der Rückbau der Migration 0411 behält die Protokollzeilen des Portal-Assistenten und läuft unter erzwungener Zeilensicherheit (Prüfbefund AF25-1).
- Tests: Der Test der Portal-Betriebskostenabrechnung verwendet eine gültige Objektnummer (Prüfbefund AF25-2).

## 1.61.1 (02.10.2026) Korrektur: FinTS-Verbindungen überleben den täglichen Bankabgleich, Warteschlangenfehler mit Klartext

- Banking: Der tägliche Bankabgleich (bank.sync_all) setzte aktive FinTS- und EBICS-Verbindungen jeden Morgen auf "nicht eingerichtet" zurück; beide Konnektoren werden jetzt übersprungen, die Verbindung bleibt aktiv (Regressionstest).
- Banking: Kann der FinTS-Dialog nicht an die Hintergrundverarbeitung übergeben werden (Redis oder Worker nicht erreichbar), meldet die Plattform MHVP-BANK-0057 mit Prüfhinweis statt eines Internen Fehlers.
- Handbuch: Abschnitt Banking erklärt, wie ein Interner Fehler beim Verbinden im API-Log eingegrenzt wird.

## 1.61.0 (01.10.2026) Welle 16, Prioritätenliste des Betreibers Punkte 1 bis 28 und Prüfung: Abnahmeregister, Kontenrahmen-Freigabe, Rücklagenplan, Periodensperre, Objektspalte, Guthabenposten, EBICS-Gerüst, ZUGFeRD, Zweitfaktor-Richtlinie, Portal-Assistent, Datenschutzverzeichnis, Verfügbarkeitsmessung

- Übersicht: Welle 16 mit 40 Paketen AE01 bis AE40 zu den Punkten 1 bis 28 der Prioritätenliste des Betreibers vom 01.10.2026, davon AE24 (GoCardless) vom Betreiber gestoppt und zurückgebaut; Migrationen 0357 bis 0394, real sind 33 (0357 bis 0359, 0361 bis 0369, 0371 bis 0374, 0376 bis 0379, 0381 bis 0384 und 0386 bis 0394), Platzhalter ohne Schemaänderung sind 0360 (AE04), 0370 (AE14), 0375 (AE19), 0380 (AE24) und 0385 (AE29); neue offene Entscheidungen (38): AE01-01, AE07-01, AE21-01, AE22-01, AE22-02, AE23-01 bis AE23-05, AE25-01, AE26-01 bis AE26-03, AE27-01 bis AE27-03, AE28-01 bis AE28-03, AE29-01, AE30-01, AE30-02, AE31-01, AE32-01, AE33-01 bis AE33-03, AE34-01 bis AE34-03, AE35-01, AE35-02, AE36-01, AE36-02, AE37-01, AE38-01, AE38-02; der Prüfbericht docs/reviews/REVIEW-W16-2026-10-01.md (AE40) nennt drei behobene Befunde (AE40-1 bis AE40-3) und sechs weitere Punkte (AE40-01 bis AE40-06, davon AE40-02 nach dem Bericht umgesetzt).
- Plattform: Die neue Systemrolle Fachkundige Abnahmeperson trägt das Recht acceptance:approve, das Administratoren bewusst nicht erhalten.
- Buchhaltung: Das Abnahmeregister führt je Anhang-D-Fall Sollwertfassungen (Eingaben, Sollwert, Quelle, Rechenweg) mit Freigabe durch eine zweite Person, eingefrorenen freigegebenen Fassungen und nur anhängenden Abnahmeergebnissen (Migration 0357).
- Buchhaltung: Das Abnahmeprotokoll Anhang D lässt sich als Markdown exportieren (GET /accounting/acceptance/export.md).
- CRM: Die neue Seite Plattform, Abnahmeregister Anhang D dient zum Erfassen, Einreichen, Freigeben und Abnehmen der Sollwerte.
- Buchhaltung: Die Kontenrahmen-Freigabe folgt dem Vier-Augen-Prinzip, wer zur Prüfung gibt, kann nicht selbst freigeben (Schalter je Version, Standard an, Abschalten nur mit Begründung).
- Buchhaltung: Mehrschlüsselverteilung je Vorlagenkonto wird geprüft (Summe 100 Prozent) und ist im Kontenrahmen-Entwurf pflegbar.
- Buchhaltung: Die Abrechnungsart Heizkosten steht an den Heizkostenkonten als Vorschlag mit dem Kennzeichen Freigabe offen und wird im Entwurf übernommen.
- Buchhaltung: Der Prüfbericht des Kontenrahmens weist Konten ohne Abrechnungsart, ohne gültige Verteilung und offene Vorschläge aus.
- Buchhaltung: Die G1-Öffnungsliste erfasst je Prüfpunkt eine verantwortliche Person und einen Nachweis (Dokument oder Verweis) und markiert bestandene Punkte ohne Nachweis.
- Banking: Ein neuer Vergleichsbericht stellt die Automatik der manuellen Buchung je Fallklasse gegenüber (aus dem Entscheidungsspeicher, ohne Buchung).
- Banking: Der Automatikschalter lässt sich in der Oberfläche nur bei offener G1 per Antrag und Freigabe durch eine zweite Person einschalten.
- Mietrechnungen: Entwürfe bei geschlossenem G1 tragen Entwurfsnummern ENTWURF-JJJJ-NNNNNN und verbrauchen die lückenlose Rechnungsnummer MR nicht.
- Mietrechnungen: Ein Mandantenschalter regelt den Nummernmodus von Entwürfen (Entwurfsnummer als Standard, reguläre Nummer, Ablehnung bei geschlossenem G1) mit Auswahl im CRM.
- Buchhaltung: Der Nummernmodus für Mietrechnungsentwürfe verlangt tenant_settings:update statt contracts:update (Prüfbefund AE40-02).
- Buchhaltung: Zinsbuchungen erfassen einbehaltene Kapitalertragsteuer, Solidaritätszuschlag und Kirchensteuer als Beträge laut Bankbeleg und buchen im Entwurf Geldkonto netto, Steuerkonten und Zinserlös brutto (P01-01).
- Buchhaltung: Steuerkonten für Zinsabzüge werden je Buchungskreis hinterlegt; ohne Konto wird ein Abzug mit MHVP-ACC-0011 abgelehnt.
- WEG Rücklagen: Die Rücklagenentwicklung zeigt die Steuerabzüge gebuchter Zinsbuchungen auf das Rücklagenkonto als eigene Spalte.
- Buchhaltung: Die Nebenbuchprüfung blendet ausgebuchte Posten und Posten stornierter Buchungen per Mandantenschalter (Standard ein) aus und weist sie getrennt aus.
- Buchhaltung: Der Prüfexport nebenbuchabgleich.csv enthält die Spalten Grund, Ausgebucht und Storniert.
- WEG: Der Rücklagenplan führt je Rücklage und Jahr die Soll-Zuführung mit Beschlussbezug und Status (Entwurf, beschlossen, ersetzt), wird aus dem Wirtschaftsplan abgeleitet und liefert das Soll in der Rücklagenentwicklung (Migration 0363).
- WEG: Ein Mandantenschalter regelt Änderungen des Anfangsbestands nach berechneter Abrechnung (gesperrt als Standard, protokolliert oder Vier Augen) mit Änderungsprotokoll.
- CRM: Die Seite Rücklagen zeigt den Rücklagenplan je Rücklage mit Anlage als Entwurf und Kennzeichnung als beschlossen.
- WEG: Zahlungen je Zweckrücklage zeigen Soll laut Wirtschaftsplan und Ist der gebundenen Zahlungen je Rücklage (neue Übersicht in der Jahresabrechnung).
- WEG: Ein Mandantenschalter steuert einen Aufteilungsvorschlag nicht zugeordneter Rücklagenzahlungen nach Planverhältnis, Standard aus, nur Information ohne Buchung.
- Verträge: Sollstellungen können beim Anlegen einer aktiven Zweckrücklage der Gemeinschaft zugeordnet werden.
- WEG: Unterjährige Planänderung zeigt die Differenz bereits gebuchter Monate je Einheit, Komponente und Monat als Nachforderung oder Gutschrift (AE09, M24-08).
- WEG: Ein Mandantenschalter bestimmt die Behandlung der Differenz mit den Varianten nur Hinweis (Standard), sofort fällig und Verrechnung mit der nächsten Rate; Entwürfe buchen nichts, Freigabe nur mit G4 und durch eine zweite Person (M12-L2, P07-01).
- CRM: Übernahmevorschau des Wirtschaftsplans enthält den Abschnitt Differenz gebuchter Monate mit Variantenwahl, Entwurf und Freigabe.
- WEG: Die Zuordnungsregel beim Eigentümerwechsel gilt je Erwerbsart als Mandantenregel (manuelle Freigabe als Standard, Zuordnung nach Fälligkeit oder Abrechnungsbeschluss) mit den Endpunkten GET und PUT /hoa/acquisition-rules (Migration 0366), Anzeige in der Freigabeliste und Einstellung in der Abrechnungsansicht, die Berechnung bleibt beim Standard unverändert.
- WEG: Neue Abrechnungsversion nimmt Korrekturgrund, Bezug und Beschluss auf und übernimmt Belege, Notizen und Darlehensangaben.
- WEG: Der Korrekturbericht zeigt je Eigentümer vorher, nachher und Differenz mit der Heizkostenüberleitung als eigenem Block im Versionsvergleich, nur Anzeige, Rechtsfolge offen.
- WEG: Die Mandanteneinstellung Stichtag der Übergangsregel für den Grundlagenbeschluss virtueller Versammlungen ist neu (Migration 0368, ohne Rechtswirkung, ohne Sperre).
- WEG: Das Versammlungsdetail zeigt Fristhinweise zum Grundlagenbeschluss (Dreijahresgrenze, Gültigkeitsende, Resttage, Stichtag) als Orientierung.
- CRM: Eine neue Einstellungsmaske bedient den Online-Versammlungsschalter (Standard aus), und die Versammlungseinstellungen enthalten das Stichtagsfeld.
- Portal: Mieterträge für Kapitalanleger erscheinen im Eigentümerportal nur bei eingeschaltetem Mandantenschalter (Standard aus).
- Portal: Der Umfang der Meldungen im Eigentümerportal ist je Mandant wählbar (keine, freigegebene, alle des eigenen Objekts).
- CRM: Portalfunktionen um Mieterträge-Schalter und Ticketumfang ergänzt.
- Rechnungen: Die sachliche Prüfung zeigt für verknüpfte Wirtschaftsplanpositionen einen Budgetabgleich mit Planansatz, bisher zugeordneten Rechnungen, dieser Rechnung und Rest.
- Rechnungen: Die sachliche Prüfung weist auf Beschlüsse zu einem anderen Wirtschaftsplan und auf fehlende Beschlusszuordnung bei zustimmungspflichtigen Aufträgen hin (nur Hinweise, keine Freigabe).
- Abrechnung Miete: Ein Mandantenschalter regelt offene Vorauszahlungen bei der Abrechnung (nur Information als Standard, Verrechnung per Storno, Saldo gegen Soll), Migration 0371.
- Abrechnung Miete: Snapshot und Anschreiben legen den Rechenweg für offene Vorauszahlungen offen (Saldo gegen gezahlt und gegen Soll, Gesamtsicht).
- Abrechnung Miete: Variante Verrechnung erzeugt einen Buchungsentwurf mit Ausgleich der offenen Vorauszahlungsposten nur zusammen mit den Ergebnisentwürfen hinter G3.
- CRM Abrechnung: Der Bereich Neue Vorauszahlungen bietet die Auswahl der Behandlung offener Vorauszahlungen mit Hinweis auf die offene Frage AC10-01.
- Dokumente: Textbausteine für Informationsblatt, Eigentümeranschreiben und Nachweis § 35a EStG durchlaufen Entwurf, eingereicht und Freigabe durch eine zweite Person, ausgegeben werden nur freigegebene Texte (Migration 0372).
- CRM: Die neue Pflegemaske unter Einstellungen, Textbausteine zeigt den Status je Text und den Hinweis Text nicht freigegeben.
- Verträge: Umlagevereinbarungen lassen sich je Mietvertrag und Betriebskostenart mit Klauselbezug, Nachweisdokument und Gültigkeit erfassen, die Massenerfassung je Objekt zeigt eine Vorschau.
- Abrechnung: Ein Prüfbericht zeigt fehlende Umlagegrundlagen je Kostenposition und Mietvertrag, und ein Mandantenschalter (Standard an) sperrt Statuswechsel und Informationsblatt.
- Abrechnung Miete: Die Sperre bei fehlenden Umlagegrundlagen (AE17) ist standardmäßig aktiv; bestehende Abrechnungen ohne erfasste Umlagevereinbarungen können bis zur Erfassung oder bis zum Abschalten des Schalters nicht ausgegeben werden (Hinweis für den Betrieb).
- Abrechnung: Die Abrechnungsfrist zeigt je Mietvertrag das Fristende als Orientierung und schlägt den Zugang aus dem Versand vor, die Übernahme erfolgt per Klick mit Nachweis.
- Abrechnung: Ein Mandantenschalter regelt das Verhalten nach Fristablauf (Nachforderung sperren als Standard oder nur Hinweis), und eine optionale tägliche Warnung erinnert vor Fristablauf (Migration 0374).
- Buchhaltung: Prüfpunkte des Regelregisters sind im CRM pflegbar (Datum, Bezeichnung, Quelle, Notiz) mit Vorfrist und Stand, Hinweis ohne Rechtsfolge (AB10-01).
- Abrechnung: Der Heizkostenvergleich stellt die externe der eigenen Berechnung je Nutzer gegenüber, mit pflegbarer Toleranz und Abweichungsbericht als CSV, nur lesend (M17-02).
- Buchhaltung: Die Periodensperre gilt je Objekt und Zeitraum (Tabellen period_lock und period_lock_setting, Migration 0376) mit Mandantenschaltern, als Standard sperrt nur der Buchungskreis.
- Buchhaltung: Buchen und Stornieren prüft bei aktivem Schalter die Objektsperre (MHVP-ACC-0030).
- Abrechnung: Abschluss einer Miet- oder Eigentümerabrechnung setzt die Sperre für Objekt und Zeitraum nur mit Schalter, sonst Vorschlag.
- Buchhaltung: Eine Periodensperre lässt sich nur mit Schalter, Begründung und Freigabe durch eine zweite Person aufheben, die Zeile bleibt erhalten.
- CRM: Die neue Seite Einstellungen, Buchhaltung, Periodensperren trägt den Hinweis Entscheidung offen.
- Buchhaltung: Buchungszeilen tragen ein eigenes Objekt (journal_line.property_id), abgeleitet aus Angabe, Einheit oder Vertrag des Buchungssatzes; Zeilen mit Einheit erhalten in der Datenbank stets das Objekt ihrer Einheit (Migration 0377, ADR 0023).
- Buchhaltung: Bestehende Buchungszeilen wurden einmalig aus Einheit und Vertrag befüllt; Beträge und übrige Inhalte gebuchter Zeilen bleiben unverändert, ein Storno übernimmt das Objekt der Originalzeile.
- Buchhaltung: Die USt-Übersicht je Objekt gruppiert nach dem Objekt der Buchungszeile; Monatsmatrix, Einnahmen und Ausgaben sowie das Journal lassen sich nach Objekt filtern.
- Buchhaltung: Neuer Driftbericht line-property-drift zeigt Buchungszeilen, deren Objekt nicht zu Einheit, Vertrag oder Buchungskreis passt; eine Abweichung zur Einheit erscheint zusätzlich im Prüfbericht.
- Buchhaltung: Unbekannte Einheiten oder Objekte in Buchungszeilen werden mit einer Validierungsmeldung abgelehnt statt mit einem Serverfehler.
- Buchhaltung: Guthaben aus Betriebskostenabrechnung, Eigentümerabrechnung und Kautionsabrechnung werden als auszahlbare Guthaben angezeigt und können per Vorschlag und Freigabe durch eine zweite Person (G3) zu Verbindlichkeitsposten werden (API /accounting/credit-payables).
- Buchhaltung: Ein Mandantenschalter regelt die offene Buchungsregel Q01-01 mit den Varianten Aus (Standard), Nebenbuchposten ohne Umbuchung und Umbuchung auf ein hinterlegtes Kreditorenkonto (neue Buchungsart credit_reclass, Buchung über den normalen Weg).
- Zahlungsverkehr: Ein Zahlungsauftrag ohne Rechnung lässt sich direkt aus dem Verbindlichkeitsposten eines Guthabens mit Auswahl von Empfänger- und Auftraggeberkonto erzeugen, hinter G2 und G3, weiter mit zwei Freigaben am Auftrag.
- Buchhaltung: Der Storno-Pfad für Guthabenposten umfasst Rücknahme, Verwerfen des Umbuchungsentwurfs und Storno der gebuchten Umbuchung mit G1 und ist bei beauftragten oder bezahlten Posten gesperrt.
- CRM: Der neue Abschnitt Auszahlung von Guthaben aus Abrechnungen steht unter Bank, Zahllauf.
- Banking: Das EBICS-Grundgerüst für den Kontoauszugsabruf arbeitet mit einem Mandantenschalter (Standard aus) und einer Variante des Signaturschlüssels (Standard extern bei der unterschreibenden Person).
- Banking: EBICS-Teilnehmer erhalten Schlüsselerzeugung (Standard 4096 Bit nach Krypto LifeCycle EBICS), INI, HIA, Freischaltung und Bankschlüsselabruf HPB mit Prüfung der Hash-Werte durch eine zweite Person.
- Banking: Private EBICS-Schlüssel werden nur verschlüsselt gespeichert, jeder Schlüsselwechsel wird mit Zeit, Person und Grund protokolliert und löscht den alten privaten Schlüssel.
- Banking: Der Abruf von Kontoauszügen mit Auftragsart C53 (camt.053 im ZIP) importiert ohne Dubletten mit Rohdatenablage und Auftragsprotokoll, und ohne installierte EBICS-Übertragung meldet die Plattform MHVP-BANK-0050.
- Banking: Die Bankseite zeigt den neuen Abschnitt EBICS (Grundgerüst), und das Runbook EBICS-Einrichtung beschreibt die Bedienung in der Plattform.
- Banking: Das Paket GoCardless (AE24) wurde vom Betreiber gestoppt, der Teilstand entfernt; Migration 0380 ist ein Platzhalter ohne Schemaänderung.
- Buchhaltung: Honorarrechnungen und Gutschriften lassen sich als ZUGFeRD/Factur-X herunterladen (Briefbogen-PDF mit eingebettetem CII im Profil EN 16931, gleiche Daten und Sperren wie die XRechnung).
- Buchhaltung: Der ZUGFeRD-Beleg trägt die PDF/A-3 Kennzeichnung (XMP, Factur-X Erweiterungsschema, Associated File, sRGB-Ausgabebedingung); die eigene Vorprüfung weist Blocker aus und behauptet keine Konformität.
- Buchhaltung: Der ZUGFeRD-Beleg lässt sich prüfen (CII-Struktur und PDF/A-Vorprüfung) und einmalig mit Prüfergebnis ablegen (Migration 0381), nichts wird versendet oder gebucht.
- Belegeingang: Bei ZUGFeRD-Rechnungen werden Profil (MINIMUM bis XRECHNUNG) und Containerangaben gelesen und als Hinweise im Prüfergebnis angezeigt; ZUGFeRD 1.0 erhält eine klare Meldung.
- CRM: Das Verwalterhonorar bietet die Schaltflächen ZUGFeRD, ZUGFeRD prüfen und ZUGFeRD ablegen.
- Banking: Die Meldungen zu MHVP-BANK-0010 (Bankzugang gesperrt) und MHVP-BANK-0013 (Bank nicht erreichbar) sind deutsch mit nummerierten Prüfschritten, der englische Text von python-fints wird nicht mehr angezeigt, und Verbindungsfehler der Netzwerkbibliothek führen zu MHVP-BANK-0013 mit Nennung des Rechnernamens.
- Banking: Die Meldungen zu MHVP-BANK-0009 (PIN abgelehnt) und MHVP-BANK-0012 (erneute Freigabe) sind deutsch mit dem nächsten Schritt.
- Banking: Die FinTS-Adresse einer Verbindung kann von Hand eingetragen oder zurückgesetzt werden (PATCH /banking/fints/connections/{id}, Migration 0382), geprüft auf https und einen öffentlichen Rechnernamen, mit erneuter PIN-Eingabe und ohne automatischen Anmeldeversuch.
- Banking: FinTS-Dialoge verwenden die Adresse der aktuellen Institutsliste statt der beim Anlegen gespeicherten, solange keine manuelle Adresse gesetzt ist.
- CRM: Die FinTS-Verbindungen zeigen die Prüfschritte bei gesperrtem Zugang und nicht erreichbarer Bank, die verwendete FinTS-Adresse mit Herkunft und ein Formular zum Ändern und Zurücksetzen der Adresse.
- Skripte: scripts/update_fints_institutes.py spielt die CSV-Datei der Deutschen Kreditwirtschaft in die Institutsliste ein (Trockenlauf als Standard, URLs werden nie stillschweigend entfernt), ein falsch gelesener Name (BLZ 45451555) wurde berichtigt.
- Buchhaltung: Der KoSIT-Validator ist mit make kosit-fetch, kosit-test und kosit-validate und im Repository gepinnten Prüfsummen (scripts/kosit.lock) reproduzierbar, und der CI-Job xrechnung-kosit läuft ohne Repository-Variablen und ist mit MHVP_KOSIT_ENABLED=false abschaltbar.
- Sicherheit: Die Zweitfaktor-Richtlinie je Mandant (AE27, Migration 0383) hat den Standard freiwillig gemäß Betreiberentscheidung M2-01; Pflicht für alle Verwaltungsrollen oder je Rolle ist als Mandantenwahl unter Einstellungen, Rollen einstellbar (Frage AE27-01).
- Portal: Die Pflicht des zweiten Faktors für Portalzugänge ist ein eigener Mandantenschalter, Standard aus.
- Anmeldung: Wer unter eine gewählte Pflicht fällt und noch keinen zweiten Faktor hat, richtet TOTP bei der nächsten Anmeldung auf der Seite Zweiten Faktor einrichten mit QR-Code ein; laufende Sitzungen bleiben, niemand wird ausgesperrt.
- Anmeldung: Unter einer gewählten Pflicht lassen sich TOTP und der letzte Passkey nicht entfernen (MHVP-AUTH-0015); der Anmeldelink des Portals führt bei gewählter Pflicht in den TOTP-Schritt oder die Einrichtung.
- Einstellungen: Neuer Abschnitt Zweiter Faktor je Rolle unter Rollen und Rechte; Meine Daten und Portal Sicherheit zeigen einen Hinweis, wenn der zweite Faktor vorgeschrieben ist.
- API: Neue Endpunkte GET/PUT /auth/mfa-policy, POST /auth/mfa/setup/start und /auth/mfa/setup/confirm, Feld mfa_required in /auth/me und Status mfa_setup_required beim Login.
- Portal: Ein neuer Assistent beantwortet Fragen zu den freigegebenen Unterlagen (Menüpunkt Assistent, Seite /assistent) mit Berechtigungsfilter nach access_grant, fremde Einheiten und Dokumente antworten 404, und ein Zugang ohne Freigaben erhält eine leere Antwort ohne Anbieteraufruf.
- Portal: Die Portalfunktionen der Einstellungen enthalten die Mandantenschalter Chat-Bot und Datenschutz-Feature (beide ab Werk aus), Migration 0384.
- KI: Antworten im Portal-Assistenten gibt es nur mit freigegebenem Datenschutzhinweis (Textbaustein, Freigabe durch eine zweite Person), Kenntnisnahme je Zugang und Fassung und geöffnetem Gateway-Gate, sonst erscheinen nur Treffer der Dokumentsuche mit Nennung des Grundes.
- KI: Portalfragen laufen mit dem Prompt portal_v1 ohne Wissensbasis, Plattformsuche, Werkzeuge, Änderungsvorschläge und Beispiele, mit maskierter Frage und Quellenprüfung nach dem Lauf, und die Deduplizierung gibt nie die Antwort eines Zugangs an einen anderen.
- KI: Die Stichwortsuche der Dokumente filtert den Zugriffsumfang vor dem Limit, damit fremde Treffer erlaubte Dokumente nicht verdrängen.
- Portal: Alle Fragen an den Assistenten werden protokolliert (maskiert, mit Ergebnis, Quellen und Grund), das CRM zeigt das Protokoll in den Portalfunktionen, und je Zugang gilt ein Stundenlimit von 20 Fragen.
- Plattform: Rechtstexte des Portals je Mandant (Impressum, Datenschutz, Nutzungsbedingungen) sind Textbausteine mit Freigabe durch eine zweite Person, und der öffentliche Abruf liefert nur die freigegebene Fassung nach Portal-Host.
- Portal: Fuß der Seite und Anmeldeseite verlinken die freigegebenen Rechtstexte (Seite Rechtliches), sonst den externen Link der Markenanpassung; ohne Freigabe erscheint der Hinweis Text nicht freigegeben.
- Plattform: Die Fassung der Nutzungsbedingungen in der Einwilligungsrichtlinie lautet NB und Textversion, der Mandantenschalter folgt von Hand oder dem freigegebenen Text, die Übernahme erfolgt ausdrücklich mit Bestätigung und Protokoll.
- CRM: Die neue Einstellungsseite Rechtstexte des Portals zeigt Freigabestand, Pflegemaske und Abgleich der Fassung, und die Textbausteine-Seite führt nur noch die Brief- und Nachweistexte.
- Portal: Der Formularbaukasten ist final mit Typregister für 20 Elementtypen (Wertformat und Prüfregel je Typ, Anschrift, Standort, Unterschrift und Textfelder strenger geprüft) und den neuen Endpunkten GET /portal-admin/forms/element-types und POST /portal-admin/forms/preview (Trockenlauf ohne Speichern).
- CRM: Formularvorlagen zeigen eine Vorschau mit Prüfung von Beispielwerten und eine aufklappbare Übersicht der Elementtypen mit Prüfregeln und Quellenstatus.
- Portal: Formulare zeigen Hinweise und Längengrenzen zu Anschrift, Standort, Unterschrift und Betrag und die Meldung der Prüfung direkt am Feld.
- Portal: Bewertungen von Dienstleistern stehen hinter dem Mandantenschalter provider_rating_display (Standard aus, Migration 0386), die Übersicht nur für die Verwaltung zeigt Anzahl, Durchschnitt und Verteilung ohne Freitext, Dienstleister und Dritte sehen nichts.
- WEG: Eine Mandantenregel legt für Vollmacht gegen eigene Stimme vier Varianten fest, der Standard markiert den Konflikt als Prüfhinweis und verwirft keine Stimme, die Regel gilt für Portal und CRM-Stimmerfassung.
- WEG: Versammlungsleitung entscheidet Stimmkonflikte im CRM (erste Stimme bestätigen oder zweite zählen), beide Stimmen bleiben im Vorgang erhalten.
- WEG: Prüfpunkte zur Versammlungsform (Beschlussgrundlage, Status, Gültigkeitsende, Dreijahresgrenze, Konferenzlink) erscheinen als Übersicht erfasster Angaben ohne Rechtsaussage.
- WEG: Protokollentwurf enthält Online-Zusagen, Portalvollmachten, Wortmeldungen, Online-Stimmen je TOP und Prüfhinweise zu Stimmkonflikten.
- CRM: Der Online-Schalter bietet die Regelauswahl an, und die Versammlungsseite zeigt Prüfpunkte und Stimmkonflikte.
- Portal: Das Portal weist darauf hin, wenn eine Stimme zur Prüfung gespeichert und nicht gezählt wird.
- Datenbank: Die Migration 0387 legt Regelfeld, Stimmquelle und die Tabelle für Stimmkonflikte an.
- Datenschutz: Das Register erfasst je Verarbeitungstätigkeit die Rolle von GdWE, Verwalter und Betreiber, die Rechtsgrundlage und die eingesetzten Auftragsverarbeiter als Pflegefelder ohne Vorbelegung (Migration 0388).
- Datenschutz: Die Drittlandübermittlung wird je Anbieter mit Status offen, nein oder ja samt Ländern und Garantien erfasst, bestehende Einträge ohne Drittlandangabe gelten als offen.
- Datenschutz: Neue Übersicht Dienstleister laut Konfiguration erkennt aus Einstellungen und Konnektoren (Gmail, Google Kalender, Drive, Paperless, finAPI, GoCardless, KI-Anbieter, LetterXpress und weitere) die genutzten Dienste und übernimmt fehlende als Unterauftragnehmer mit offenen Prüffeldern.
- Datenschutz: Das Verzeichnis von Verarbeitungstätigkeiten lässt sich als PDF-Entwurf herunterladen und listet offene Punkte sowie Dienste ohne Registereintrag.
- CRM Einstellungen, Datenschutz: Registereinträge sind bearbeitbar (Rollen, Rechtsgrundlage, Auftragsverarbeiter, AVV, Drittland, Prüfstatus).
- Dokumente: Papierkorb als Mandantenschalter (Standard aus, Frist 30 Tage nur als Vorschlag): zulässig gelöschte Dokumente bleiben bis Fristende erhalten, Wiederherstellung und vorzeitige endgültige Löschung mit Begründung protokolliert, täglicher Löschauftrag prüft Sperren und Fristen erneut (AC07-03).
- Dokumente: Löschcheckliste um das Ziel Papierkorb und den Status im Papierkorb erweitert, Löschjournal und Replay führen Ablegen und Wiederherstellen mit (AC07-03).
- Dokumente: Die neue CRM-Seite Papierkorb bietet Wiederherstellen und endgültiges Löschen, der Schalter steht unter Einstellungen, Aufbewahrung (AC07-03).
- Kontakte: Der Umfang der DSGVO-Auskunft (andere Personen mit Name und Rolle, interne Vermerke) ist ein Mandantenschalter mit unverändert zurückhaltendem Standard, der Umfang wird je Auskunft bei der Vorbereitung festgehalten (AC07-01).
- Betrieb: Das Runbook Backup beschreibt zusätzlich Papierkorb, Journal und Replay bei einer Wiederherstellung (AC07-03).
- Kontakte: Die Rechtsgrundlage je Verarbeitung (Einwilligung, Vertrag, berechtigtes Interesse) ist je Mandant mit Begründung pflegbar (GET, PUT, DELETE /consent-legal-basis); E-Mail-Zustellung, Weitergabe an Dienstleister und Werbung folgen der gewählten Grundlage, der Standard bleibt die Einwilligung.
- Kontakte: Ein Widerspruch bei berechtigtem Interesse lässt sich erfassen (POST /contacts/{id}/objections) und sperrt die Verarbeitung für den Kontakt bis zur Rücknahme; eine widerrufene Einwilligung gilt dort ebenfalls als Sperre.
- Portal: Die veröffentlichte Fassung der Nutzungsbedingungen ist ohne Anmeldung abrufbar (GET /portal/public/terms?tenant=), bei unbekanntem oder nicht veröffentlichendem Mandanten antwortet die Schnittstelle immer gleich mit 404.
- Portal: Die Annahme der Nutzungsbedingungen wird mit Zeitpunkt, Fassung und einem Hash der Verbindungsadresse protokolliert (Migration 0390); die Einladungsseite zeigt die Annahme schon vor der Aktivierung.
- CRM: Widersprüche erscheinen in der Einwilligungsliste des Kontakts als Widerspruch mit der Aktion Zurücknehmen.
- Plattform: Ein Beat-Job prüft jede Minute die Health-Adressen von API, CRM und Portal (nur bei gesetzten Adressen MHVP_AVAILABILITY_API_URL, MHVP_AVAILABILITY_CRM_URL und MHVP_AVAILABILITY_PORTAL_URL) und speichert die Messpunkte der Eigenmessung der Verfügbarkeit (Migration 0391).
- Plattform: Die Monatsauswertung der Eigenmessung läuft automatisch täglich und weist den Wert aus allen Prüfungen und den Wert ohne Wartungsfenster getrennt aus, beendete Monate werden festgeschrieben.
- Plattform: Neuer Schalter Wartungsfenster zählen als Ausfall (Standard aus, auditiert) bestimmt, welcher Wert gegen das Ziel 99,5 Prozent bewertet wird; die Entscheidung dazu bleibt offen (AD10-02, AE35-01).
- Plattform: Ein Löschlauf entfernt Minutenwerte nach der Aufbewahrung (Standard 120 Tage), aber nur für festgeschriebene Monate.
- CRM: Die Seite Plattform, Wartung und Verfügbarkeit zeigt die Eigenmessung mit letzter Prüfung, 24 Stunden, Fehlschlägen, Schalter und Monatstabelle.
- Runbook: verfuegbarkeit.md Abschnitt 4 beschreibt Einrichtung, Auswertung, Löschlauf und Grenzen der Eigenmessung.
- Betrieb: Die Auslöser der Jahrespartitionierung nach ADR 0021 (Zeilen und Größe von journal_entry, journal_line und bank_transaction, P95 der Journal- und Bankumsatzliste, Dauer des Wiederherstellungstests, produktive Mandanten) werden als Plattformkennzahlen gemessen, wöchentlich gespeichert und bei einem neuen Auslöser an die Plattformadministratoren gemeldet (Migration 0392, Seite Plattform, Betrieb, API /platform/ops/scale).
- Betrieb: Die Betriebskennzahlen /platform/ops/metrics enthalten Zeilen, Größe und P95 der Listen sowie die Alarme scale_trigger_partition_review und scale_trigger_measure_again; Mandantenzahl und Fachzähler lassen Demo-Mandanten weg.
- Plattform: Mandanten tragen ein Demo-Kennzeichen (tenant.is_demo, Migration 0392, PUT /platform/tenants/{id}/demo, Merkmal und Schaltfläche in der Plattformansicht); das Setzen ist bei geöffneter Freigabestufe nicht möglich.
- Plattform: Demo-Mandanten sind aus Lizenz, Nutzungszählung, Abrechnungsvorschau, Mandantenexport, Journal-Export, DATEV, Prüfexport und der mandantenübergreifenden Arbeitsansicht ausgeschlossen (409 MHVP-DEMO-0001).
- Betrieb: Der Befehl make seed-demo erzeugt nur synthetische IBANs (Bankleitzahl 00000000) mit Selbstprüfung, setzt das Demo-Kennzeichen und die freiwillige Zweitfaktor-Richtlinie des Demo-Mandanten, und das neue Runbook demo-mandant.md beschreibt den Ablauf.
- Importe: Der Importassistent erkennt die Kopfzeile einer beliebigen CSV- oder XLSX-Datei in den ersten 30 Zeilen und überspringt Titelzeilen; die erkannte Zeile wird mit Begründung angezeigt und lässt sich von Hand ersetzen.
- Importe: Die Spaltenzuordnung wird je Zielfeld vorgeschlagen (gespeicherte Zuordnung, Feldbezeichnung, Fachbegriff, ähnliche Schreibweise, Typprüfung der Beispielwerte) und zeigt Status und Prozentwert; ohne Speichern der Vorlage wird nichts verwendet.
- Importe: Bestätigte Spaltenzuordnungen werden je Mandant und Berichtstyp gemerkt (neue Tabelle import_column_assignment, Migration 0393) und bei der nächsten Datei zuerst vorgeschlagen.
- Importe: Neuer Prüfbericht vor dem Speichern zeigt Pflichtspalten, leere und fremde Spalten, Beispielwerte je Feld sowie Beispielzeilen und fehlerhafte Zeilen, ohne Daten zu verändern.
- Importe: Abschnitt Benötigte Exporte zeigt je Berichtsart, ob eine Datei vorliegt, ob die Pflichtfelder gemerkt sind und ob übernommen wurde; die Anforderungsliste docs/integrations/immoware24-exporte.md enthält die offenen Angaben für den Betreiber.
- Postfach: Ein neuer eingehender Webhook (POST /api/v1/mail/inbound/sources/{id}/classified-mails) nimmt klassifizierte Mails des Bestandsprogramms an, mit API-Schlüssel (Recht mail_inbound:ingest), HMAC-Signatur mit fünf Minuten Zeitfenster, Idempotenz je event_id (Wiederholung 200, anderer Inhalt 409) und Größenlimit 1 MiB.
- Postfach: Mailquellen für den Webhook lassen sich unter /api/v1/mail/inbound/sources anlegen (Geheimnis einmalig sichtbar), ändern, deaktivieren, mit neuem Geheimnis versehen und mit Empfangsprotokoll lesen.
- Postfach: Die Klassifikation des Bestandsprogramms wird nur als Vorschlag in classification.external gespeichert, die Mail durchläuft dieselbe Zuordnung und Ticketregel wie jede eingehende Mail.
- Integrationen: Eine Dossier-Vorlage nach Anhang B und eine Checkliste je Bestandstool sind angelegt (DOSSIER-VORLAGE.md, CHECKLISTE-BESTANDSTOOLS.md), und der Vertrag inbound-mail-webhook.md beschreibt den Webhook.
- Datenbank: Die Migration 0394 legt die Tabellen inbound_mail_source und inbound_mail_event mit Row Level Security an.
- CRM Einstellungen: Neue Seite Fachliche Regeln (/einstellungen/fachliche-regeln) zeigt 54 Mandantenschalter für fachlich offene Entscheidungen mit aktuellem Wert, Standard, Varianten, Hinweis Entscheidung offen und Nummer der Frage in docs/OPEN_QUESTIONS.md; geändert wird dort über die vorhandenen PUT- und PATCH-Endpunkte, eine Abweichung vom Standard verlangt eine Rückfrage.
- CRM Einstellungen: Die Einstellungsübersicht hat die Karten Fachliche Regeln und Textbausteine, die Suche findet jeden Schalter der neuen Seite über seine Bezeichnung.
- CRM Assistent: Seitenkontext und Vorschläge für Abnahmeregister, Papierkorb, Fachliche Regeln, Periodensperren, Textbausteine und Rechtstexte des Portals.
- CRM Korrekturen: Die Seite Periodensperren lädt ihren Übersetzungsnamensraum korrekt, sechs Tabellen der Welle 16 liegen in einem Scroll-Wrapper, zwei TypeScript-Fehler (StatementVersionDiff, TextBlocksAdmin-Test) sind behoben.
- CRM BFF: Die Allowlist erlaubt PUT consent-legal-basis/{Zweck} für die Rechtsgrundlage der Einwilligungen.
- Handbuch: Das Kapitel Einstellungen enthält den neuen Abschnitt Fachliche Regeln mit einer Tabelle aller Schalter.
- Plattform: Die Genehmigung einer Freigabestufe G1 bis G5 wird für einen Demo-Mandanten mit 409 MHVP-DEMO-0001 abgelehnt, der Antrag bleibt beantragt (Review W16, AE40-1).
- Dokumente: Textbausteine, Rechtstexte des Portals und der Datenschutzhinweis des Portal-Assistenten können nicht mehr von einer Person freigegeben werden, die die Fassung bearbeitet hat (Review W16, AE40-2).
- Buchhaltung: Ein Entwurf einer Zinsbuchung mit Steuerabzügen lässt sich wieder löschen, die Abzugszeile des Entwurfs wird mit entfernt (vorher Serverfehler, Review W16, AE40-3).
- Dokumentation: Der Prüfbericht der Welle 16 mit drei behobenen Befunden und sechs weiteren Punkten steht in docs/reviews/REVIEW-W16-2026-10-01.md.
- Plattform: Das Gate-Routenregister führt zusätzlich die Freigabewege Abnahmeregister, Periodensperre und Textbausteine (ohne Geldfluss).
- Datenbank: Die Migrationskette 0357 bis 0394 ist linear und wurde auf einer frischen Datenbank bis head, bis base zurück und erneut hinauf sowie im Autogenerate-Abgleich ohne Drift geprüft (Review W16).
- Betrieb: Neue Umgebungsvariablen MHVP_AVAILABILITY_API_URL, MHVP_AVAILABILITY_CRM_URL, MHVP_AVAILABILITY_PORTAL_URL (Eigenmessung); die neue Rolle acceptance_expert erscheint bei Bestandsmandanten nach python -m mhvp.platform.sync_roles; der CI-Job xrechnung-kosit läuft bei jedem Push (abschaltbar mit MHVP_KOSIT_ENABLED=false).
- Dokumentation: Die neue Übersicht docs/plans/IMPLEMENTATION_STATUS.md zeigt den Stand der Punkte 1 bis 28 der Prioritätenliste, Lückenliste und Entscheidungsliste tragen den Stand der Welle 16.

## 1.60.0 (01.10.2026) Welle 15, Leistungsfehler, Restpunkte und Portal-Versammlung: Buchungswächter mit Indexzugriff, Online-Versammlung im Portal, Wartungsfenster und Verfügbarkeit, Domainprüfung, Portalsprachen

- Übersicht: Welle 15 mit 11 Paketen AD01 bis AD11, Migrationen 0346 bis 0356; real sind 0346 (Buchungszeilen-Wächter indexierbar, Index bank_transaction tenant_id/booking_date), 0351 (Online-Versammlung), 0352 (Domainprüfung) und 0355 (Wartungsfenster, Verfügbarkeit), alle anderen sind Platzhalter ohne Schemaänderung. Neue offene Entscheidungen: AD03-01, AD03-02, AD06-01 bis AD06-03, AD10-01, AD10-02.
- Buchhaltung: Die Datenbankwache für Buchungszeilen sucht die Buchung jetzt über den Primärschlüsselindex (gleiche Regeln, Migration 0346), statt die Buchungstabelle linear zu durchsuchen.
- Banking: Neuer Index auf Mandant und Buchungsdatum für die Bankumsatzliste.
- Leistung: Lastdatengenerator lädt Buchungen mit aktiver Wache; Runbook und ADR 0021 beschreiben den Wartungsjob für ANALYZE nach Massenimporten.
- Kern: If-Match-Pruefungen fuer Regeln, Vertragsbemerkungen und Dokumente laden die Zeile mit Zeilensperre (FOR UPDATE), sodass von zwei gleichzeitigen Schreibvorgaengen mit demselben ETag nur einer durchgeht und der andere 412 erhaelt.
- Tickets: Kontaktdaten des Mieters oder Eigentümers gehen im Auftrag an den Dienstleister nur mit Einwilligung data_sharing (oder Mandantenregel), sonst ohne personenbezogene Felder und mit Protokollgrund.
- Automatisierung: Webhooks zu contact.updated werden ohne Einwilligung data_sharing ohne personenbezogene Felder eingereiht und als Ereignis protokolliert.
- Portal: Annahmemaske für die Nutzungsbedingungen nach der Anmeldung und bei der Aktivierung (Fassung, Annahme per POST /portal/terms/accept).
- KI: Anbieterkonfiguration hat je Stufe den Schalter Werkzeuge (Tool Use), Standard aus, mit Hinweis auf Vier-Augen-Freigabe und offene Entscheidung AC08-01.
- KI: GET /ai/conversations/{id} liefert je Antwort die verwendeten Nachschlagewerkzeuge (tools_used), sodass sie im wieder geöffneten Chat sichtbar bleiben.
- KI: Treffer der Nachschlagewerkzeuge erscheinen als Chat-Links zu Kontakt, Vertrag, Dokument und Objekt, ohne Telefon und E-Mail.
- Portal: Die Seite Dienstleister im Portal zeigt ohne das Recht tenant_settings:read einen Hinweistext statt einer leeren Rechtsträgerauswahl.
- Tests: Rechtsträgerauswahl des Portals ist mit einem echten Rechtsträger eines Fremdmandanten geprüft (nicht gelistet, Klassenfreigabe 404).
- Betrieb: Runbook Backup, Schritt 3 beschreibt Replay mit Spiegelschritten statt der veralteten Sperre durch offene DMS-Spiegel.
- Doku: Handbuch um Hinweis zur Rechtsträgerauswahl, Verknüpfungsziele und E-Mail-Einwilligung ergänzt.
- WEG: Online-Versammlung im Eigentümerportal technisch vorbereitet (Zusage online, Vollmacht mit Zeitraum und Widerruf, Wortmeldung, Stimmabgabe je TOP), Mandantenschalter Standard aus, Vollmacht und Stimme zusätzlich hinter G4.
- WEG: Verwaltung öffnet und schließt die Online-Abstimmung je TOP und arbeitet Wortmeldungen im CRM ab; Übersicht der Online-Teilnahme auf der Versammlungsseite.
- Portal: Versammlungsseite zeigt Konferenzlink, Tagesordnung mit Abstimmungsstand und Ergebnisse erst nach Verkündung.
- Datenbank: Migration 0351 mit Tabellen für Schalter, Vollmachten und Wortmeldungen sowie Abstimmungsfenster je TOP.
- Plattform: Kundendomains lassen sich per DNS prüfen (CNAME oder A-Eintrag gegen den Plattformhost), Status, Zeitpunkt und Befund werden gespeichert, in der CRM-Seite angezeigt und im Plattformaudit protokolliert.
- Tests: Playwright-Läufe gegen eine frische Datenbank, CRM 58 von 63 bestanden (ein Test rot durch den Fehler der Objektliste im Vertragsformular, vier übersprungen), Portal 18 von 18; die Spec core-paths-ga01 lief erstmals und wurde korrigiert, die Portal-Konfiguration nutzt die Sprache de-DE.
- Dokumentation: Dritte Lückenanalyse des Master-Prompts gegen 1.59.0 mit fünf neuen Befunden (API-Verschachtelung, Portalsprachen, Wartungsankündigung, Verfügbarkeitsnachweis, veraltete Befehlstabelle in CLAUDE.md) unter docs/plans/LUECKENLISTE-2026-10-02.md.
- Plattform: Wartungsfenster können von Plattformadministratoren angekündigt, geändert und abgesagt werden (Beginn, Ende, Text Deutsch und Englisch, Vorlaufzeit je Fenster oder Standard 48 Stunden), mit Eintrag im Plattformaudit und öffentlichem Feed GET /platform/maintenance/current als Quelle für die Statusseite.
- CRM und Portal: Ein Hinweisbanner zeigt angekündigte und laufende Wartungsfenster ab der Vorlaufzeit an.
- Plattform: Neue Seite Wartung und Verfügbarkeit mit Wartungsfenstern und der Monatsauswertung der Verfügbarkeit gegen das Ziel 99,5 Prozent (Import der Monatszahl je Messpunkt aus Uptime Kuma, geplante Ausfallzeit der Wartungsfenster getrennt ausgewiesen, Migration 0355).
- Runbook: Neues Runbook verfuegbarkeit.md mit Verfügbarkeitsziel, Monatsauswertung und Ankündigung von Wartungsfenstern; deploy.md um den Ankündigungsschritt ergänzt.
- Portal: Die Sprachliste wird aus den Dateien unter messages/ abgeleitet, eine weitere Sprache braucht keine Codeänderung mehr; fehlende Schlüssel fallen auf Deutsch zurück, das Backend validiert Sprachcodes über MHVP_PORTAL_LOCALES.
- Dokumentation: ADR 0022 (Proposed) hält die Abweichung von Abschnitt 12 zur Verschachtelung der API Pfade fest (127 Pfade, Alternativen, Empfehlung), Frage AD10-01.
- Kommunikation: Kurz senden signiert immer mit dem angemeldeten Nutzer; ein Namens- oder Firmenblock des Vorschlags nach der Grußformel wird beim Anlegen des Entwurfs entfernt, damit Name und Firma nur einmal in der Signatur stehen.
- Kommunikation: GET /mail/signature/preview liefert position_missing, wenn die eigene Funktionsbezeichnung fehlt (nicht beim Einzelunternehmen).
- Postfach: Die Kompaktansicht zeigt vor dem Senden den eigenen Signaturblock und bei fehlender Position einen Hinweis mit Link zum Profil.
- Banking: Die FinTS-Institutsliste leitet die abgeschalteten Altadressen hbci-pintan.gad.de und hbci11.fiducia.de auf die Atruvia-Adressen fints1.atruvia.de bzw. fints2.atruvia.de um (Volks- und Raiffeisenbanken waren sonst nicht erreichbar).
- CRM: Vertrag anlegen und Benutzerverwaltung laden die Objektliste seitenweise (vorher 422 bei page_size über 200, Objektauswahl leer).
- CRM: Die WEG-Liste unter Verwaltung nutzt dieselbe Darstellung wie Mietverwaltung und SEV (Suche, Karten und Tabelle mit Adresse, Verwaltungsart, Eigentümer und Status); die Zeilen öffnen die WEG-Verwaltung des Objekts.
- Plattform: Die Schemaklassen der Wartungsfenster heißen jetzt MaintenanceWindowIn/Out/Patch (Namenskollision mit den Instandhaltungs-Schemata der Objekte im OpenAPI-Client behoben).
- Plattform: Entzogener Portalzugang eines Mitarbeiters erhält den Status revoked (Status disabled verletzte die Prüfregel aus 0310; bestehende Zeilen werden in Migration 0310 bereinigt).
- Betrieb: Neue Umgebungsvariablen MHVP_MAINTENANCE_NOTICE_HOURS und MHVP_PORTAL_LOCALES (Compose und env.prod.example); NEXT_PUBLIC_PORTAL_LOCALES wird im Portal zur Bauzeit eingebettet.
- Dokumentation: CLAUDE.md und AGENTS.md nennen make deploy, make backup, make backup-verify und make staging-smoke; Quelle ist docs/AGENT_RULES.md.

## 1.59.0 (01.10.2026) Welle 14, Prüfung der Wellen 12 und 13 und technischer Rest: Sicherheitskorrekturen, Auskunftsexport mit Vier-Augen-Freigabe, Einwilligungsregeln, KI-Nachschlagewerkzeuge, Löschcheckliste, Skalierung

- Übersicht: Welle 14 mit 12 Paketen AC01 bis AC12, Migrationen 0334 bis 0345 sämtlich als Platzhalter ohne Schemaänderung (noop). Die Prüfung der Wellen 12 und 13 (docs/reviews/REVIEW-W1213-2026-10-01.md) ergab drei Korrekturen, die umgesetzt sind. Neue offene Entscheidungen: AC03-01, AC06-01 bis AC06-03, AC07-01 bis AC07-03, AC08-01, AC09-01, AC10-01, AC11-01.
- Sicherheit: Unbekannte Abfrageparameter ergeben ohne Anmeldung 401 statt 422 (keine Schemaangaben an Unangemeldete); Listen nennen Unangemeldeten keine erlaubten Filter- oder Sortierspalten mehr.
- Plattform: Eigene Plattform-Hosts sind als Kundendomain gesperrt (422); API, CRM und Portal der Plattform können nicht für einen Mandanten eingetragen werden.
- Plattform: Änderungen mit If-Match in Vermietung (Interessenten) und SLA (Regeln) sperren die Zeile, gleichzeitige Schreibvorgänge mit demselben ETag überschreiben sich nicht mehr.
- Plattform: Neue Seite Plattformaudit listet die festgeschriebenen Plattformaktionen mit Filter nach Aktion, Paginierung und aufklappbarem Payload.
- Plattform: Das Register der gate-pflichtigen Routen trennt Routen mit Gate, Routen des Freigabeverfahrens und Routen mit Entwurf statt Ablehnung; Informationsblatt, Ausgaben der Eigentümerabrechnung und Versand des Vermögensberichts sind aufgenommen.
- Plattform: Der Laufzeitnachweis legt für Routen mit vorgelagerter Datensatzprüfung den Datensatz an und weist die Ablehnung bei geschlossenem Gate für jede Route des Registers nach.
- Kontakte: Auskunftsexport nach Art. 15 DSGVO mit Feld-Allowlist, Fremdpersonenschutz und Vier-Augen-Freigabe; alter Endpunkt GET /contacts/{id}/export antwortet 409
- Kontakte: Der Auskunftsexport enthält keine Hashwerte, Tokens, internen Vermerke und KI-Rohdaten; andere Personen erscheinen nur mit Rolle. Download erst nach Freigabe durch eine zweite Person, protokolliert.
- Kontakte: Einwilligungsregeln je Mandant unter /consent-policy (E-Mail-Zustellung, Weitergabe, Fassung der Portal-Nutzungsbedingungen), Standard restriktiv; die Prüfung der Weitergabe an Dienstleister an der Einwilligung data_sharing ist vorbereitet.
- Kontakte: Portalzugang der Kontaktakte mit Schalter Einladung sofort senden, Beschriftung aller sechs Status und Aktion Einladen für nicht eingeladene Zugänge.
- Kommunikation: Zustellung per E-Mail fällt ohne email_delivery-Einwilligung auf Post zurück (Mandantenschalter, Protokollgrund)
- Kommunikation: Serienversand mit Kennzeichen Werbung erreicht nur Kontakte mit gültiger Werbeeinwilligung, übersprungene werden gezählt und protokolliert.
- Portal: Aktivierung und Zugang setzen bei veröffentlichter Fassung die Annahme der Nutzungsbedingungen voraus, Zeitpunkt und Fassung werden gespeichert.
- Portal: Neuer Lesepfad GET /portal-admin/legal-entities (tenant_settings:read, nur Id und Name) für die Rechtsträgerauswahl der Seite Dienstleister im Portal.
- Dokumente: Löschcheckliste je Ziel (Index, Original, Paperless, Drive, Embeddings, KI-Auszüge) mit täglichem Nachlauf und Schaltfläche in den Löschvorschlägen; Löschung und Replay entfernen Embeddings und ersetzen KI-Auszüge in derselben Transaktion, erneute Löschung nach Wiederherstellung setzt Spiegelschritte zurück.
- Dokumente: Vermögensbericht (asset_report) und Abrechnungslauf (statement) sind Verknüpfungsziele; Versandbrief und Informationsblatt hängen direkt am Bericht bzw. Lauf.
- WEG: Der Versandstatus im Bereitstellungsprotokoll des Vermögensberichts wird auf Deutsch und Englisch angezeigt.
- Buchhaltung: Erlöskonto im Honorarformular wird aus den Erlöskonten des Objekts gewählt statt als ID eingegeben.
- Buchhaltung: Die Startseite listet fällige Prüfpunkte des Regelregisters mit dem Hinweis ohne Rechtsfolge.
- Buchhaltung: Die Beschreibung des Prüfexports nennt die Tabelle nebenbuchabgleich.csv.
- Buchhaltung: Regelversion am Abrechnungslauf und Freigabepunkt § 13b UStG sind als getestete Komponenten umgesetzt.
- Buchhaltung: Analyse zu D24 (offene Mietvorauszahlungen bei Abrechnungserteilung) als Regeldokument AC10-d24 mit Rechenbeispiel ergänzt, Entscheidungsfrage AC10-01 angelegt, Verhalten unverändert hinter G3.
- KI: Der Chat-Assistent kann über Nachschlagewerkzeuge (Kontakte, Verträge, offene Posten, Dokumente, Termine, Kontenplan) selbst in den Fachdaten nachsehen, nur lesend, mit den Rechten des fragenden Nutzers, höchstens sechs Abfragen je Frage, Standard aus (Schalter tool_use je Anbieterstufe).
- KI: Werkzeugaufrufe werden am KI-Lauf mit Werkzeug, maskiertem Suchtext und Trefferzahl protokolliert und über GET /ai/runs/{id} als tools_used ausgegeben; Werkzeugausgaben gehen nur maskiert an den Anbieter. Das Chat-Widget im CRM zeigt die verwendeten Werkzeuge mit Trefferzahl oder dem Hinweis ohne Berechtigung.
- Betrieb: Leistungsbefund journal_line_guard (Suche ohne Index, Korrektur in Folgewelle geplant), ADR 0021 Skalierung
- Betrieb: ADR 0021 beschreibt Ist-Analyse, Alternativen, Auslöser und Messplan der Jahrespartitionierung von journal_entry und bank_transaction (ohne Schemaänderung); Lasttest mit 100.000 Buchungen und 100.000 Bankumsätzen (nur mit MHVP_PERF=1), Messwerte im Runbook leistungsmessung.md.
- Betrieb: Runbook Backup um Löschcheckliste, Nachlauf und Hinweis ergänzt, dass Backups nicht bearbeitet werden.
- Betrieb: Runbook xrechnung-kosit mit gepinnten Fassungen und Prüfsummen von KoSIT-Validator 1.5.0 und XRechnung-Konfiguration 3.0.2; lokaler Lauf der Generatorrechnungen ohne Fehler und Warnungen, CI-Job bleibt inaktiv bis zur Betreiberentscheidung AC11-01.
- Doku: Abnahmeprotokoll der Wellen 12 und 13 für die Releases 1.57.0 und 1.58.0 angelegt, Freigabefelder leer.
- Doku: Bericht docs/plans/BERICHT-2026-10-01-WELLEN-11-13.md und 38 Fragen AA01-01 bis AB12-01 mit Prioritäten in docs/plans/ENTSCHEIDUNGEN-2026-10-01.md.
- Doku: Prüfbericht docs/reviews/REVIEW-W1213-2026-10-01.md mit den drei umgesetzten Korrekturen und den offenen Punkten AC01-01 und AC01-02.
- API: Felder tool_use (KI-Anbieterstufe) und accept_terms (Portalaktivierung) sind optional (Kompatibilität des API-Clients, Standard aus)
- Tests: Bestandstests zu Übergabeprotokoll und Lastschrift-Vorankündigung erteilen die E-Mail-Einwilligung, eigene Namensräume für Regelketten-Tests

## 1.58.0 (01.10.2026) Welle 13, Folgearbeiten der zweiten Lückenanalyse: Freigabestufen mit Objektbezug, Nebenbuchabgleich, strikte Listenparameter, WEG-Versammlung und Vermögensbericht, Portalstatus, Plattformaudit

- Übersicht: Welle 13 der zweiten Lückenanalyse (Folgearbeiten zu Welle 12) mit 14 Paketen AB01 bis AB14, Migrationen 0320 bis 0333, davon 0331 (portal_account.locale) und 0332 (platform_audit_event) als echte Migrationen und die übrigen (0320 bis 0330 und 0333) als Platzhalter ohne Schemaänderung. Neue offene Entscheidungen: AB10-01, AB12-01.
- API: Listenendpunkte lehnen unbekannte Abfrageparameter mit 422 ab (strict_query an allen GET-Listen); externe API-Nutzer prüfen ihre Parameter, /tenant/events akzeptiert limit als Alias für page_size
- API: filter[feld], sort und fields stehen nun auch an Auftragsliste, SLA-Uhren, Notfallalarmen, Regeln, Synchronisationsläufen, Abrufaufträgen, Bankregeln, Zahlungsaufträgen, Anzeigen und Interessenten bereit; filter, sort, fields, include und as_of nur dort, wo die Liste sie anbietet.
- API: Änderungen an SLA-Regeln, Automatisierungsregeln, Anzeigen, Interessenten, Zahlungsaufträgen, Teams und Postfächern prüfen If-Match (412 bei veraltetem Stand) und liefern ETag.
- Plattform: Buchungs- und Zahlungsrouten mit Objektbezug (führendes System, Sofortbuchung Ausgleich, Zahlungsdatei herunterladen und einreichen) prüfen die Freigabestufe mit Objekt und Rechtsträger, eine begrenzte Freigabe öffnet nur das Pilotobjekt.
- Plattform: Neue CRM-Seite Freigabestufen mit Stand je Mandant, Checkliste, Antrag mit Nachweisdokument, Genehmigung, Ablehnung und Widerruf mit Kommentar sowie Anzeige von Öffnung und Widerruf.
- Plattform: Neuer Endpunkt GET /platform/tenants/{id}/release-gates liefert Stand und Anträge eines Mandanten für Plattformadministratoren.
- Plattform: Plattformaktionen ohne Mandantenkontext (Kundendomain, Mandantenstatus, OIDC-Client anlegen, Secret erneuern, aktivieren, deaktivieren) werden in der unveränderlichen Tabelle platform_audit_event festgeschrieben, ohne Secrets im Payload (Migration 0332).
- Plattform: Neuer Endpunkt GET /platform/audit-events listet das Plattformaudit paginiert und nach Aktion filterbar, nur für Plattformadministratoren.
- Plattform: Die Objektsuche im Zuordnungsassistenten des Messdienstes nutzt page_size und liest die Seitenantwort korrekt.
- Plattform: Ein Integrationstest ruft jede registrierte gate-pflichtige Route bei geschlossenem Gate auf und weist die Ablehnung mit MHVP-GATE-0001 und dem zuständigen Gate nach, Routen mit vorgelagerter Datensatzprüfung sind mit Grund aufgeführt.
- Buchhaltung: Die Auswertungen zeigen den Nebenbuchabgleich je Debitor und Kreditor zum gewählten Stichtag mit hervorgehobenen Differenzen.
- Buchhaltung: Der Prüfexport enthält die Tabelle nebenbuchabgleich.csv mit Hauptbuchsaldo, offenen Posten und Differenz je Debitor und Kreditor zum Zeitraumende.
- Buchhaltung: Das Verwalterhonorar-Formular im CRM ist um Verwalterkontakt, Kündigungsdatum, Fälligkeitsregel, Erlöskonto und SE-Gebührenbetrag erweitert, die Honorarliste zeigt die Felder an.
- Buchhaltung: Rechnungspläne zeigen das Kennzeichen automatische Buchung (ja/nein, Umschalter); der Planlauf meldet den Sperrzustand (G1, Automatikschalter) und erzeugt weiterhin nur Entwürfe.
- Buchhaltung: Die Kreditorenansicht erklärt die Standard-Bankregel (Vorschlag, keine Buchung); Integrationstests für Honorarfelder, Standardregel und Planflag ergänzt.
- Buchhaltung: Der Abrechnungslauf speichert ID und Wirksamkeitsdatum des Registereintrags im Snapshot und zeigt die Regelversion im CRM an.
- Buchhaltung: Fällige Prüfpunkte des Regelregisters werden über rule-versions/due-checkpoints als Hinweis ohne Rechtsfolge gemeldet.
- Buchhaltung: Die Eingangsrechnung zeigt den Freigabepunkt § 13b UStG bei Reverse Charge, ohne Automatik.
- WEG: Wiederholungs- und Fortsetzungsversammlungen sind im CRM mit Auswahl der Ursprungsversammlung anlegbar, Vorlagen werden aus einer Liste gewählt.
- WEG: Die öffentliche Beschreibung der Versammlung wird Eigentümern im Portal angezeigt, die interne nie.
- WEG: Der Hinweis zur Geltungsdauer des Grundlagenbeschlusses zur virtuellen Versammlung über drei Jahre erscheint dauerhaft in der Versammlungsdetailansicht (API und CRM).
- WEG: Der Vermögensbericht kann nach Ausgabe je Eigentümer per Brief über den bestehenden Versand bereitgestellt werden (Zustellweg aus Kontakt oder Mandantenstandard, standardmäßig nur ohne Portalabruf, hinter G4); das Bereitstellungsprotokoll zeigt Abrufe und Briefe je Eigentümer.
- WEG: Sonderfälle Ersterwerb, Zwangsversteigerung und Sonderrechtsnachfolge erscheinen mit deutscher Fallbezeichnung in Befund und Freigabeliste des Abrechnungspakets; die Zuordnung bleibt offen (AA07-01).
- WEG: Das Informationsblatt zur Betriebskostenabrechnung kann als Dokument am Abrechnungslauf abgelegt werden (G3), Vorschau und Liste der Ausgaben im CRM; Texte zu Belegeinsicht und Einwendungen sind als "Text nicht freigegeben" gekennzeichnet.
- WEG: Für die Eigentümerabrechnung gibt es eine Vorschau von Anschreiben und eigenem Nachweis nach § 35a, beide Dokumente werden nach interner Freigabe am Abrechnungslauf abgelegt (G3); der steuerliche Hinweis ist als "Text nicht freigegeben" gekennzeichnet.
- Portal: Der Status des Portalzugangs (nicht eingeladen, eingeladen, aktiv, gesperrt, abgelaufen, entzogen) wird gespeichert; ein Beat-Job setzt abgelaufene Einladungen auf expired und gesperrte Zugänge auf locked.
- Portal: Portalzugänge lassen sich ohne Einladung anlegen (send_invitation=false) und später einladen; die Annahme setzt den Status invited voraus.
- Portal: Die Sprachwahl wird am Portalkonto gespeichert (Migration 0331, PATCH /portal/me/locale), bei der Anmeldung übernommen und ist auch auf der Anmeldeseite wählbar.
- Portal: Neue CRM-Einstellungsseite Dienstleister im Portal zur Pflege der Verfügbarkeitsfenster und der Freigaben je Unterlagenklasse.
- Kommunikation: message.delivered_at wird bei Versandannahme und Zugangsnachweis gesetzt, read_at beim Öffnen eines Dokuments der Nachricht im Portal (Indizien ohne Rechtswirkung).
- Kommunikation: Tests erzeugen bank_transaction.imported, portal_account.activated, contract.changed und contract_payment.changed über den Fachpfad und prüfen Signatur und Mindestnutzlast.
- Dokumente: Neue CRM-Seite Erzeugte Dokumente mit Filter nach Vorlage und Zeitraum und Link zum Dokument.
- Dokumente: Kontexttypen einer Vorlage sind per PATCH und im Vorlagenformular pflegbar, verwendete Platzhalter werden angezeigt.
- Dokumente: Der Verweis auf den Freigabe-Workflow ist am Auftrag per PATCH und auf der CRM-Auftragsseite pflegbar.
- Automatisierung: Der Job Dokumenteneingang serialisiert gleichzeitige Läufe je Mandant per Sperre, ein zweiter Lauf indexiert keine Datei doppelt; der Job Verbrauchsinformation ist ebenso je Mandant gesperrt.
- Automatisierung: Tests für Direktablage in beiden Schalterzuständen mit Mandantentrennung und Protokollierung sowie Parallellauf und Wiederholung beider Jobs.
- Import: Schreiber für die HeiWaKo-Satzarten L und M mit Roundtrip- und Byte-Identitätstests gegen den Parser ergänzt, nur mit im Repo belegten Feldern.
- Betrieb: Integrationstests für die konfigurierte Vertragsnummer (Format, Startwert nur bei unbenutztem Kreis) und den Mandantenstandard des Zustellwegs im Versand; Komponententests für die Plattformseiten Domains und OIDC-Clients; Test für contact.updated mit Fehlzustellung und Neuzustellung geschärft.
- Doku: Abschnitt Faktenstand mit Zweck, Stack, Datenmodell, Schnittstellen und Status in den Dossiers Übergabeprotokoll, Müller FLOW und smart-einzug ergänzt.
- Buchhaltung: Registerverweis im Abrechnungs-Snapshot verträgt ungespeicherte Regelversionen (Feld id leer statt Zeichenkette None)
- KI-Chat: Seitenkontext kennt die neuen Seiten Erzeugte Dokumente und Freigabestufen
- Dokumente: Liste der erzeugten Dokumente mit Scroll-Rahmen auf schmalen Bildschirmen

## 1.57.0 (01.10.2026) Welle 12 der zweiten Lückenanalyse: Freigabestufen, Buchhaltungsprüfungen, WEG-Versammlung und Vermögensbericht, Schwarzes Brett, Portal, Automatisierung

- Übersicht: Welle 12 der zweiten Lückenanalyse (Lückenliste vom 01.10.2026) mit 17 Paketen AA01 bis AA17, Migrationen 0303 bis 0319, davon 0303, 0304, 0305, 0307, 0308, 0309, 0310, 0311, 0312, 0313 und 0316 als echte Migrationen und die übrigen (0306, 0314, 0315, 0317, 0318, 0319) als Platzhalter ohne Schemaänderung. Neue offene Entscheidungen: AA01-01, AA02-01 bis AA02-03, AA03-01, AA04-01, AA05-01 bis AA05-03, AA06-01, AA06-02, AA07-01, AA07-02, AA08-01, AA10-01 bis AA10-03, AA11-01 bis AA11-03, AA12-01 bis AA12-04, AA13-01, AA14-01 bis AA14-03, AA15-01, AA15-02, AA16-01 bis AA16-03, AA17-01 bis AA17-03.
- Buchhaltung: Die Konsistenzprüfung meldet Lücken in der Nummernfolge je Geschäftsjahr und Abweichungen des Nummernzählers (B04).
- Buchhaltung: Die Konsistenzprüfung gleicht je Debitor und Kreditor die offenen Posten mit dem Hauptbuchsaldo zum Stichtag ab und zeigt Differenzen zur Prüfung (B09).
- Buchhaltung: Gebuchte Sätze erhalten versionierte, unveränderliche Vermerke getrennt vom Buchungsinhalt, mit Anzeige und Erfassung im Journal des CRM (B03, Migration 0303).
- Buchhaltung: Verwalterhonorar um Verwalterkontakt, Kündigungsdatum, Fälligkeitsregel, Erlöskonto und SE-Gebührenbetrag erweitert (Migration 0312), Kündigungsdatum begrenzt den Lauf.
- Buchhaltung: Rechnungsplan mit Kennzeichen auto_post (Standard aus, nur bei freigeschalteter Automatik setzbar, bucht nichts).
- Buchhaltung: Beim Anlegen eines Dienstleisterverhältnisses mit create_default_bank_rule entsteht eine Standard-Bankregel als Vorschlag.
- Buchhaltung: Eigentümerwechsel und Betragswechsel im Monat bei Eigentumsverträgen (WEG) werden auch mit freigegebener Zeitanteilsregel nicht tageweise berechnet, sondern als manueller Posten ausgewiesen (GA06-01).
- Buchhaltung: Fristausnahme mit Nachweisdokument, Erfasser und Zeitpunkt; eine Nachforderung nach Fristablauf wird nur mit Grund und Nachweis freigegeben, CRM-Abschnitt in der Abrechnungsansicht (GA06-04).
- Buchhaltung: Informationsblatt zur Abrechnung als eigenes PDF und wahlweise hinter jedem Anschreiben, Texte zu Belegeinsicht und Einwendungen bis zur Freigabe als Platzhalter (GA06-02).
- Buchhaltung: Belegliste der gebuchten Ausgaben mit Hinweis auf fehlende Belege, Option zum Anfügen der Belege an die PDF-Ausgabe (GA03-08).
- Buchhaltung: belegte Lohnanteile nach § 35a EStG aus der WEG-Einzelabrechnung als Information in Abrechnung, PDF und CRM (GA06-03).
- Buchhaltung: Regelregister mit Auswahl nach Abrechnungsbeginn, Abrechnungs-Snapshot hält den wirksamen Registereintrag fest.
- Buchhaltung: Entwurfs-Prüfpunkte für HeizkostenV §§ 5 und 12 sowie CO2KostAufG §§ 5a bis 5d über rule-versions/seed-checkpoints, ohne Rechtsfolge.
- Buchhaltung: Reverse Charge erzeugt Hinweis auf § 13b UStG als gesonderten Freigabepunkt ohne Automatik.
- Buchhaltung: Block E-Rechnung zeigt Profil, Prüfer, Version, Ergebnis und Meldungen.
- WEG: Beschlussstatus und Nachrichtenänderung prüfen If-Match (412 bei veraltetem Stand) und liefern ETag.
- WEG: Versammlungsarten Wiederholung, Fortsetzung (mit Ursprungsversammlung), Teilversammlung und Umlaufverfahren sowie Ende, Vorlagen für Einladung, Vollmacht und Stimmzettel und öffentliche und interne Beschreibung ergänzt.
- WEG: Ergebnis je TOP (angenommen, abgelehnt, vertagt, ohne Abstimmung), Protokolltext je TOP, Stimmprinzip je TOP und Beschlussregel Zustimmung aller Eigentümer ergänzt.
- WEG: Jede Stimme trägt ihren Kanal (Präsenz, online, Umlauf); Auszählung und Mitgliederliste zeigen ihn.
- WEG: Ort, gerichtliche Vermerke, Eintragungszeitpunkt sowie die Status gelöscht und gegenstandslos als Vermerk ergänzt.
- WEG: Hinweis bei einer Geltungsdauer des Grundlagenbeschlusses über drei Jahre, Sperre nur mit Mandantenschalter (Standard aus).
- WEG: Vermögensbericht wird nach Ausstellung im Eigentümerportal bereitgestellt (Liste und PDF hinter G4), der Abruf wird je Eigentumsvertrag protokolliert und im CRM als Bereitstellungsprotokoll angezeigt (Migration 0309).
- WEG: Sondererwerbe im Abrechnungsjahr (Ersterwerb, Erbfall, Zwangsversteigerung, Schenkung, sonstiger Erwerb, Sondernachfolgehaftung) sperren das Abrechnungspaket, bis eine zweite Person die beantragte Freigabe erteilt hat; der Zuordnungsvorschlag je Erwerbsart ist nur ein Text ohne Rechtsregel.
- Portal: Seite Abrechnungen zeigt den freigegebenen Vermögensbericht der Gemeinschaft mit PDF-Abruf.
- Portal: Portalzugänge führen Rollen und den Einladungszeitpunkt; abgelaufene Einladungen und gesperrte Zugänge erscheinen mit den Status expired und locked.
- Portal: Aushänge haben jetzt Kategorie, Hinweisstufe (neutral, Info, Warnung, Gefahr), mehrere Zielgruppen (Mieter, Eigentümer, Dienstleister) und mehrere Anlagen (Migration 0311).
- Portal: Mieter, Eigentümer und Dienstleister können einen Aushang im Portal als gelesen bestätigen, das CRM zeigt die Lesequote und die einzelnen Bestätigungen als Hinweis auf die Kenntnisnahme, nicht als Zustellung.
- Portal: Aushänge zeigen die Hinweisstufe farbig mit Text und bieten jede Anlage einzeln zum Download an.
- Portal: Zugriffsmatrix um den Bereich document_class erweitert, Freigabe einer Unterlagenklasse je Rechtsträger und Rolle (Migration 0316).
- Portal: Sprachwahl Deutsch und English im Kopf, weitere Sprachen allein über Übersetzungsdateien.
- Portal: Formularbaukasten auf 20 Elementtypen erweitert (Anschrift, Standort, Unterschrift, Einwilligung, Betrag, Trennlinie).
- Portal: Dienstleister sehen Rahmenverträge und Verfügbarkeitskalender lesend, die Verwaltung erfasst die Zeitfenster.
- Portal: Zugriffspfadprotokoll als Test über Liste, Download, Sammel-Download, Suche, Export und KI-Abruf.
- Portal: Sprachermittlung robust bei leerem Accept-Language-Eintrag
- Plattform: Hintergrundjobs lesen die Freigabestufe je Mandant aus der Datenbank, ein geöffnetes G1 wird im Worker erkannt, andere Mandanten bleiben geschlossen.
- Plattform: Ein Register gate-pflichtiger Routen mit Test verhindert, dass neue Geld-, Abrechnungs- oder Versandrouten ohne Gate-Prüfung unbemerkt hinzukommen.
- Plattform: Freigabeanträge G2 bis G4 lassen sich nur mit vollständiger Checkliste aus 18.0 und verknüpftem Nachweisdokument genehmigen, Checkliste abrufbar unter /tenant/release-gates/checklists.
- Plattform: Freigaben speichern Öffnung (opened_by, opened_at) und Widerruf (revoked_by, revoked_at, Kommentar) getrennt, Migration 0304.
- Plattform: Freigaben lassen sich auf Objekte, Rechtsträger und Funktionen begrenzen; eine begrenzte Freigabe öffnet die Stufe nicht für den ganzen Mandanten.
- Plattform: ticket.category_id verweist auf den Kategoriekatalog (vorhandene Vorlagen), der Freitext bleibt Fallback.
- Plattform: Neuer Listenbaustein ListSpec lehnt nicht angebotene Parameter, Filter, Sortierungen und Stichtage mit 422 ab und unterstützt as_of für zeitlich gültige Daten.
- Plattform: Aufträge haben die optionale Verweisspalte approval_workflow_id (Migration 0307).
- Plattform: Abrechnungszeiträume haben einen Status (offen, Ergebnisse erstellt, bestätigt, abgeschlossen) mit Statuswechsel-Endpunkt, Sperrzeitpunkt und Löschschutz nach Abschluss; die Objektansicht zeigt den Status mit Schaltfläche für den nächsten Schritt.
- Plattform: Der Energieausweis eines Gebäudes lässt sich mit einem Dokument des Dokumentenarchivs verknüpfen.
- Plattform: Wartungsposten und Dienstleisterverhältnisse nehmen Dokumentverweise auf.
- Plattform: make seed-demo legt einen Demo-Mandanten mit erfundenen Daten an (3 Objekte, 40 Einheiten, 60 Kontakte, 36 Buchungsentwürfe, 200 Bankumsätze), nur in dev, test und staging.
- Plattform: Neuer Standard-Zustellweg je Mandant (Post, E-Mail, Portal), der im Versand gilt, wenn Position und Kontakt keinen Zustellweg vorgeben.
- Plattform: Neue Seite Nummernkreise mit Präfix, Stellenzahl, Startwert, Jahresbezug und Vorschau; wirkt bei Vertragsnummern, der Rechnungsnummernkreis bleibt gesperrt.
- Plattform: Neue Seite Domains zum Pflegen der Kundendomains je Mandant mit CNAME-Hinweis und zum Sperren oder Entsperren eines Mandanten.
- Plattform: Neue Seite OIDC-Clients zum Anlegen, Secret erneuern und (de)aktivieren per API und Oberfläche.
- Dokumente: Vorlagen tragen Kontexttypen, Briefbogenvorlage und berechnete Platzhalter, die Vorlagenliste filtert nach Kontext und ein Brief mit nicht erlaubtem Kontext wird abgelehnt.
- Dokumente: Neue Tabelle generated_document hält Vorlage, Version, Kontext, Empfänger und Versandvorgang erzeugter Briefe fest, abrufbar über GET /generated-documents.
- Dokumente: Der Eingangsvorschlag ordnet zusätzlich Einheit, am Dokumentdatum gültigen Vertrag, IBAN und Kundennummer zu und verknüpft Einheit und Vertrag beim Bestätigen.
- Dokumente: Nach dem Bestätigen entstehen Folgevorschläge für Rechnung, Schadensfoto, Vertrag und Protokoll, die nur Ticket oder Vertrag verknüpfen und nichts buchen.
- Dokumente: Direktablage eindeutiger Zuordnungen hinter einem Mandantenschalter (Standard aus) mit Meldung und Rücknahme.
- Dokumente: Das DocumentStore-Protokoll umfasst get, search und list_changes, dazu ein MinioStore-Adapter.
- Kommunikation: Nachrichten führen delivered_at, read_at und provider_message_id (Migration 0305).
- Automatisierung: Dokumenteneingang, Abstimmungsbericht und Zahllauf Vorschau beachten die Jobeinstellung je Mandant (Schalter und Uhrzeit), der Zahllauf ist im Jobkatalog, die plattformweite Wiederherstellungsprüfung nicht mehr.
- Automatisierung: Einstellungen, Automatisierung zeigt die Standardjobs je Mandant mit Schalter und Uhrzeit sowie im Regelformular den Schalter Testmodus (nur Protokoll) mit Kennzeichnung und Ergebnisfilter im Protokoll.
- Automatisierung: Die Jobzeitfenster öffnen bei der Zeitumstellung (29.03. und 25.10.) genau einmal, Mahnlauf und Zahllauf Vorschau legen je Mandant und Tag nur einen geplanten Lauf an, auch bei parallelem Aufruf; Tests für Sommerzeit, Wiederholung und parallele Läufe.
- Import: Schreiber für HeiWaKo-Satzart A (Ordnungsbegriffe) mit Roundtrip-Test ergänzt, nicht an eine Übermittlung angebunden.
- Betrieb: optionaler Job xrechnung-kosit prüft Generatorrechnungen mit dem KoSIT-Validator, sobald Version und Prüfsummen hinterlegt sind.
- Betrieb: Folgefälligkeit wiederkehrender Wartungen und Historie der Umsatzsteueroption (Überlappung, Wechsel Leerstand zu Vertrag) sind durch Integrationstests abgedeckt.
- Betrieb: Runbook Vorfall (docs/runbooks/incident.md), Messung der Detailseiten (P95) mit wöchentlichem Workflow perf.yml.
- Betrieb: Playwright-Spec für Objekt-Formular, Vertragsformular und Dokument-Upload ergänzt (nicht ausgeführt).
- Doku: ADR 0020 Formatversionen mit Kompatibilitätstest der nebeneinander genutzten pain-Versionen.
- Doku: Übersicht der Bestandstools mit Zweck, Schnittstelle, Status und offenen Punkten sowie Abgleich der Hub-Parser dokumentiert.
- API: ticket.commented (ohne Kommentartext), bank_transaction.imported (gebündelt je Importlauf und Konto), portal_account.activated sowie contract.changed und contract_payment.changed werden erzeugt und per Webhook zugestellt.
- API: Bankumsätze, Beschluss-Sammlung, Mahnläufe und Vorgangsliste unterstützen filter[feld], sort und fields (Vorgangsliste ohne sort).
- API: Test für contact.updated bei Eigentümerkontakten mit Fehlzustellung und Neuzustellung ergänzt.
- API: Ereigniskatalog der Webhooks bereinigt (doppelter Schlüssel contract_payment.changed)
- KI: Lernbeispiele werden eingebettet und als Few-Shot nach Ähnlichkeit ausgewählt, nur bei freigegebener Einbettungsroute.
- KI: Die Kontaktvorschau erlaubt eine Rolle je Zeile und die Übernahme leerer Felder beim Verknüpfen.
- KI: Feld merge_fields der Kontaktzuordnung optional (Kompatibilität des API-Clients)
- DMS: Konfigurierbares Ordnerschema der Google-Drive-Direktablage (Platzhalter objekt, jahr, kategorie) in der DMS-Maske.
- DMS: Hilfetext der Pfadvorlage zeigt Platzhalter korrekt an
- Betrieb: Celery-App für Konfigurationsprüfungen ohne Umschalten der aktiven App (create_celery mit set_as_current), behebt Testüberlagerung zwischen Beat-Prüfung und FinTS
- Portal: Entzug des Mitarbeiterzugangs setzt den Kontostatus auf revoked statt disabled (Statusmodell 6.2, Migration 0310 bereinigt Altwerte)
- KI-Chat: Seitenkontext und Einstellungssuche kennen die neuen Seiten Kundendomains, OIDC-Clients und Nummernkreise

## 1.56.0 (01.10.2026) Welle 10 der Lückenliste: Objektzuordnung Restbereiche, finAPI-Abgleich, Mailinhalt, Prüfung der Wellen 7 bis 9

- Übersicht: Welle 10 der Lückenliste vom 30.09.2026 mit 5 Paketen, keine Migration: Restbereiche der Objektzuordnung (Mandatsvorschläge, Abgleichberichte, historische Bankverknüpfungen, Immoware24-Importe nur für unbeschränkte Mitglieder), täglicher finAPI-Zustimmungsabgleich hinter Mandantenschalter, Inhaltsmodus der Benachrichtigungsmails, Sicherheits- und Geldflussprüfung der Wellen 7 bis 9 mit sechs Behebungen (docs/reviews/REVIEW-W79-2026-10-01.md), Dokumentation der Wellen 7 bis 9. Neue Entscheidungen: T14-01a, U15-05, Y02-01, Y04-01, Y04-02.
- Portal: Mandatsvorschläge der Portalverwaltung folgen der Objektzuordnung der Mitgliedschaft (Liste gefiltert, Entscheidung außerhalb 404).
- Import: Abgleichberichte des Parallelbetriebs zeigen bei Objektzuordnung nur zugeordnete Objekte mit neu gebildeten Summen.
- Import: Historische Bankverknüpfungen und Journalkandidaten folgen dem Bankkonto des Umsatzes.
- Import: Immoware24 Datei- und Vollimporte ohne Zielobjekt sind für Mitglieder mit Objektzuordnung gesperrt (403).
- Banking: Täglicher Beat-Job gleicht den Ablauf der Bankzustimmung beim Anbieter ab und schreibt nur bei geänderter Angabe, hinter einem Mandantenschalter (Standard aus).
- Banking: Neue Einstellung unter Einstellungen, Bank zum Ein- und Ausschalten des Zustimmungsabgleichs (API /banking/consent-sync/settings).
- Benachrichtigungen: Mandantenschalter für den Mailinhalt (voll oder nur Hinweis mit Anzahl und CRM-Link), Standard voll, Schalter unter Einstellungen, Benachrichtigungen.
- WEG: Beschlüsse, Versammlungen, Sonderumlagen, Darlehen, Maßnahmen und Versicherungsfälle sind für Mitglieder mit Rechtsträgerbereich (Steuerberater) nur noch für die zugewiesenen Gemeinschaften abrufbar.
- Dokumente: Der Beschluss als Fristbeginn der Aufbewahrung muss zur Gemeinschaft des Dokuments gehören.
- WEG: Anfangsbestand und Anfangsjahr einer Rücklage sind auch bei berechneter Abrechnung eines Folgejahres gesperrt.
- Plattform: Ein Mandantenexport ist ab Ablauf der Aufbewahrung nicht mehr herunterladbar, auch vor dem nächtlichen Löschlauf.
- WEG: Der Protokollabschluss lehnt Dokumente außerhalb des Zugriffsbereichs oder einer anderen Gemeinschaft ab und sperrt die Versammlung während der Abschlussschritte.
- Buchhaltung: Die Honorarbuchung prüft die Kontoart der Zahlerkonten beim Anlegen der Entwürfe.
- Handbuch: Wellen 7 bis 9 dokumentiert, Versionsnummer 1.55.0, mit Schwerpunkt auf Korrektionen, Sicherheitshärtung und Verbesserungen zur Stabilisierung.
- Regeln: Seed-Kontenrahmen und WebAuthn-Mengenbegrenzung im Regelindex ergänzt.
- Entscheidungen: Neue Punkte zu Sammelkonten, WebAuthn-Freischaltung und Portal-Suchindizes mit Empfehlungen hinzugefügt.

## 1.55.0 (01.10.2026) Welle 9 der Lückenliste: Passkey-Mengenbegrenzung und Einstellungsseite Übernahme-Tickets

- Übersicht: Welle 9 der Lückenliste vom 30.09.2026 mit 2 Paketen, keine Migration: Mengenbegrenzung der Passkey-Endpunkte und Einstellungsseite für die Übernahme-Tickets.
- Auth: Passkey-Optionen (Anmeldung und Registrierung) sind je Client-Adresse und je Benutzer mengenbegrenzt (429 mit Retry-After).
- Einstellungen: Neue Seite Übernahme-Tickets zur Auswahl von Standardteam und Zuständigem für Tickets aus der Übernahme-Checkliste, mit Hinweis auf fehlende Leserechte und Suchtreffer in den Einstellungen.

## 1.54.0 (01.10.2026) Welle 8 der Lückenliste: Passkey-Prüfung, Ticket-Ereignisse, Oberflächenreste, Messung, Abnahmeprotokoll, Entscheidungsliste

- Übersicht: Welle 8 der Lückenliste vom 30.09.2026 mit 6 Paketen, keine Migration. Schwerpunkte: Sicherheitsprüfung der Passkey-Implementierung mit sieben Behebungen (docs/reviews/WEBAUTHN-2026-10-01.md, Freigabe bleibt Betreiberentscheidung), Ticket-Ereignisse bei Einzel- und Sammelaktionen, Dokumentauswahl beim Protokollabschluss und Beschlussauswahl bei der Aufbewahrung, Messung der Portal-Belegsuche, Kontoartprüfung der Honorar-Kontenzuordnung und Standardzuweisung der Übernahme-Tickets, Abnahmeprotokoll der Wellen 4 bis 7 (docs/acceptance) und Entscheidungsliste für den Vorstand (docs/plans/ENTSCHEIDUNGEN-2026-10-01.md, 44 Fragen mit Empfehlung und Alternativen).
- Auth: WebAuthn-Prüfung gehärtet (strenges base64url, CBOR ohne doppelte Schlüssel und nicht minimale Längen, keine Restbytes, AT-Flag nur bei Registrierung, Erweiterungsdaten als CBOR-Map geprüft).
- Auth: Passwortlose Passkey-Anmeldung prüft den userHandle gegen den Inhaber des Credentials.
- Auth: Fehlerursachen der Passkey-Prüfung werden nur serverseitig protokolliert, die Antwort bleibt allgemein; inaktive Konten antworten wie unbekannte Credentials.
- Docs: Sicherheitsprüfung WebAuthn vom 01.10.2026 mit Freigabeempfehlung ergänzt.
- Tickets: Änderungen von Priorität und Team (Einzel- und Sammelaktion) werden als Ereignisse im Ticketverlauf mit altem und neuem Wert protokolliert.
- CRM Weg: Protokollabschluss waehlt das unterschriebene Protokoll per Dokumentsuche statt ID-Eingabe.
- CRM Dokumente: Karte Aufbewahrung und Sperren erhaelt ein Auswahlfeld Beschluss fuer die Startregel Beschluss, die Startregel ist in den Profilen waehlbar.
- CRM Weg: Versammlungsstatus gestoert ist uebersetzt (de, en).
- Tests: Messtest der Portal-Belegsuche prüft Indexnutzung per EXPLAIN (Mandantenindex unter RLS, Trigramm-Indizes ohne RLS-Schranke) und dokumentiert den Messwert im Runbook Leistungsmessung.
- Buchhaltung: Die Kontenzuordnung der Honorarbuchung prueft die Kontoart der Verwalterkonten (Forderung Aktiv, Erloes Ertrag, Umsatzsteuer Passiv) und lehnt Abweichungen mit 422 ab.
- KI Onboarding: Standardteam und Zustaendiger der Aufgaben aus der Objektuebernahme sind als Mandanteneinstellung festlegbar (leer = ohne Zuweisung), neue Aufgaben der Checkliste werden danach zugewiesen.
- Dokumentation: Abnahmeprotokoll der Wellen 4 bis 7 mit ausgeführten und nicht ausgeführten Tests, Teilergebnissen und offenen Punkten je Paket ergänzt.
- Dokumentation: Entscheidungsliste für den Vorstand vom 01.10.2026 mit allen offenen Fragen der Wellen 4 bis 7, gruppiert nach Gate, mit Empfehlung und drei Alternativen je Frage ergänzt.

## 1.53.0 (01.10.2026) Welle 7 der Lückenliste: Prüfbefunde, Passkeys, Aufbewahrung, Protokollabschluss, Onboarding, Build und Playwright

- Übersicht: Welle 7 der Lückenliste vom 30.09.2026 mit 12 Paketen (Befunde der Prüfung U15, technische Reste der Welle 6, Verifikation von Build und Playwright), Migrationen 0300 bis 0302. Schwerpunkte: Hash-Prüfung bei der Freigabe des KI-Antwortentwurfs, Objektprüfung der Rechnungsverknüpfungen, Sperre des Rücklagen-Anfangsbestands, serverseitige Passkey-Sperre für Portalkonten, Umstellung alter Selbstauskunft-Token, Startregel Beschluss und Sperrstatus im CRM, Einladung erneuern, Aufbewahrung der Exportarchive, Protokollabschluss der Versammlung im Vier-Augen-Prinzip, Onboarding bei mehreren Eigentümern, Seed-Kontenrahmen mit Schlüsselverteilung, Prüfung der Welle 6 mit neun Befunden, Build beider Web-Apps fehlerfrei, Playwright CRM (56 Specs) und Portal (24 Specs) gegen das Backend grün mit behobenen Produktfehlern. Reste und Entscheidungen stehen in docs/OPEN_QUESTIONS.md (V01-01, V05-01, V06-01, V10-01).
- Kommunikation: Freigabe des KI-Antwortentwurfs verlangt den Hash des gesehenen Entwurfs (draft_hash), bei zwischenzeitlicher Neuerzeugung antwortet der Server mit 409 MHVP-COMM-0010, das CRM sendet den Hash mit.
- Buchhaltung: Auftrag, Beschluss, Wirtschaftsplanposition und Rechnungsplan einer Eingangsrechnung müssen zum Objekt, zur Gemeinschaft bzw. zum Buchungskreis der Rechnung gehören, sonst 422 MHVP-ACC-0008.
- WEG: Anfangsbestand und Anfangsjahr einer Rücklage sind nach berechneter oder freigegebener Abrechnung des Anfangsjahres gesperrt (409 MHVP-HOA-0005), Korrektur nur per neuer Bewegung.
- WEG: Rücklagen lehnen beendete Bankkonten und inaktive Buchungskonten jetzt serverseitig mit 422 ab.
- Auth: Passwortlose Passkey-Registrierung und Anmeldung sind für reine Portalkonten serverseitig gesperrt (403, Fehlercode MHVP-AUTH-0014), Passkey als zweiter Faktor bleibt möglich.
- Letting: Selbstauskunft-Token aus Altzeilen werden per idempotentem Task und Plattform-Admin-Endpunkt auf SHA-256 umgestellt, versandte Links bleiben gültig.
- Portal: Die Rechnungseinreichung des Dienstleisters akzeptiert nur eigene Portal-Uploads als Rechnungsdokument, fremde Dokumente werden mit 404 abgelehnt.
- Portal: Beim Anlegen einer Vollmacht wird das Nachweisdokument gegen den Rechtseinheits- und Objektbereich des Benutzers geprüft.
- Dokumente: Neue Startregel Beschluss für den Fristbeginn der Aufbewahrung mit Bezug auf einen WEG-Beschluss (retention_resolution_id, Migration 0300).
- Dokumente: Das Dokumentdetail im CRM zeigt Aufbewahrungsfrist, Sperrgrund, Sperrart und den Vier-Augen-Hinweis aus retention-status.
- Dokumente: Eine bestehende Löschungssperre wird nicht mehr überschrieben, ein erneutes Setzen liefert 409.
- Portal: Schaltfläche Einladung erneuern am Kontakt für abgelaufene, nicht angenommene Portaleinladungen.
- Plattform: Aufbewahrung der Mandantenexport-Archive als Mandanteneinstellung in Tagen (Standard keine automatische Löschung), täglicher Löschlauf setzt abgelaufene Exporte auf Status expired und protokolliert die Löschung.
- Einstellungen: Neue Karte Aufbewahrung der Exportarchive, Exportliste zeigt Ablaufdatum und Status Abgelaufen.
- WEG: Protokollabschluss der Eigentümerversammlung im Vier-Augen-Prinzip (Antrag mit unterschriebenem Protokoll, Bestätigung durch zweite Person, Rückzug), danach Sperre von Tagesordnung, Anwesenheit und Beschlussfassung, Ereignis meeting.closed (Migration 0302).
- CRM: Karte Protokollabschluss auf der Versammlungsseite mit Hinweis, dass keine Protokollfrist berechnet wird.
- KI Onboarding: Bei mehreren passenden Rechtsträgern werden Bank- und Debitorenkonten nicht mehr automatisch angelegt, sondern als Entscheidungspunkt ausgewiesen und nach Auswahl des Rechtsträgers je Konto über resolve-entities angelegt.
- CRM: Bestätigungsmaske des Objektvorschlags um die Auswahl des Rechtsträgers je Konto erweitert.
- Abrechnung: Die Seite stürzte clientseitig ab, weil die Objektliste jetzt als Seite geliefert wird; Heizkostenimport und Flow-Import lesen beide Formen und laden bis zu 200 Objekte.
- Oberfläche: Hinweisblasen der Statusanzeigen ragen im geschlossenen Zustand nicht mehr über den Bildschirmrand von Telefonen.
- Übergabeprotokoll: Zählerstände in der Liste erscheinen in deutscher Schreibweise (1.234,5 statt 1234.500).
- Tests: Die E2E Specs gegen das echte Backend laufen wieder durch (Selektoren, Kontonummern, eindeutige IBANs je Lauf, Wartebedingungen und neue Dreiphasen-Menüschaltung angepasst).
- Portal: Menülinks der Navigation erreichen auf Touch-Tablets 44 px Mindesthöhe.
- Portal E2E: Übergabe-Linkauswahl eindeutig, Rollenumschalter-Test robust gegen Hydration, Admin-Token wird zwischengespeichert.
- E2E-Skript: Limit für anonyme Anfragen im Backend-Lauf angehoben (scripts/e2e-backend.sh).
- Buchhaltung: Seed-Kontenrahmen enthält je eindeutigem Kostenkonto eine Schlüsselverteilung (ein Schlüssel zu 100 %), Konto 028100 die Art der Abrechnung Hausgeld, neue Buchungskreise übernehmen die Verteilung bei vorhandenen Schlüsseln.
- Bankimport: Der CSV-Import sperrt Dateien, deren Auftragskonto vom gewählten Konto abweicht, und meldet Zeilen mit fremdem Auftragskonto oder abweichender Währung als Fehler.
- Bankimport: Mehrdeutige CSV-Beträge (mehr als zwei Nachkommastellen, NaN, Exponent) werden als Zeilenfehler abgewiesen statt geraten.
- Migrationsimport: Die SEPA-Übersicht legt keine Zahlungspläne nach Vertragsende mehr an, die Rücknahme öffnet den Vorgängerplan nur bis zum Vertragsende.
- Prüfung: Prüfbericht Welle 6 unter docs/reviews/REVIEW-W6-2026-10-01.md.
- Handbuch: neuer Abschnitt Welle 6 mit Übersicht der Erweiterungen seit Version 1.49.0 (Passkeys, Vollmacht/Vertreter, Sammelaktionen, Rücklagen, Rechnungseinreichung, Import-Rücknahme).
- Rules Index: fehlende Regeln M21-05-vertretung und U09-invoice-submission im Indexnachtrag nachgetragen, Gesamtindex gegen Dateisystem geprüft.

## 1.52.0 (01.10.2026) Welle 6 der Lückenliste: CRM-Masken, Passkeys, Portal, Tickets, Leistung, Sperren, Prüfung der Wellen 4 und 5

- Übersicht: Welle 6 der Lückenliste vom 30.09.2026 mit 16 Paketen (Reste der Welle 5 und technische Restpunkte), Migrationen 0298 und 0299. Schwerpunkte: CRM-Masken für Honorarbuchung, Rechnungsprüfung, Heizkostenimport und Rücklagen, Anmeldung mit Passkey (hinter Schalter, Standard aus), Vertreterrolle im Portal, Ticket-Sammelaktionen, Suchindex der Portal-Belegsuche, Leistungsmessung Sollstellung und Abrechnung, Rechnungseinreichung mit Netto, USt und IBAN, Immoware24-Umsatzformat, Verfahrenssperren für Dokumente, Abnahmefall PÜ11, Importreste, Python-Client-Generator, Sicherheits- und Datenflussprüfung der Wellen 4 und 5 mit acht Behebungen sowie Dokumentation. Reste und Entscheidungen stehen in docs/OPEN_QUESTIONS.md (U04-01 bis U15-04, M11-09-01, M17-09-01).
- CRM Buchhaltung: Neue Einstellungsmaske Honorarbuchung für die Kontenzuordnung des Verwalterhonorars mit Kontenauswahl je Buchungskreis und Prüfung der Kontonummern.
- CRM Buchhaltung: Neue Einstellungsmaske Rechnungsprüfung für die Preis und Mengentoleranzen der sachlichen Prüfung.
- CRM Rechnungen: Rechnungserfassung bietet Auswahlfelder für Auftrag, Beschluss, Wirtschaftsplanposition und Rechnungsplan zur sachlichen Prüfung.
- CRM BFF: Lesezugriff auf Wirtschaftspläne und Beschlüsse für die Auswahl in der Rechnungserfassung freigegeben.
- Abrechnung: Neue Maske Heizkostenimport des Messdiensts mit Liste je Objekt, Anlage mit Originaldokument, CSV-Upload mit Spaltenzuordnung, Nutzerzuordnung, Prüfbefunden und Übernahme in eine Abrechnung im Entwurf (M17-09).
- Abrechnung: BFF erlaubt das Lesen der Abrechnungsliste für die Auswahl der Zielabrechnung.
- CRM: Rücklagenformular mit Auswahl von Bankkonto des Rechtsträgers und Buchungskonto.
- CRM: Hausgeldabrechnung zeigt die Entwicklung je Rücklage und Jahr.
- CRM: Statusverlauf der Eigentümer- und Rücklagenabrechnung mit Überschrift und Hinweis bei leerem Verlauf.
- Anmeldung: Passkeys (WebAuthn) als zweiter Faktor neben TOTP mit einmaliger Challenge (300 Sekunden), Prüfung von Origin, RP ID, Signatur und streng steigendem Signaturzähler.
- Anmeldung: Optional je Passkey Anmeldung ohne Passwort im CRM (nur mit Benutzerverifikation), neue Spalte webauthn_credential.passwordless (Migration 0298).
- CRM: Anmeldeseite mit Schaltfläche Mit Passkey anmelden, zweiter Faktor mit Passkey, Meine Daten mit Passkeys hinzufügen und entfernen.
- Portal: Passkey als zweiter Faktor bei der Anmeldung und Verwaltung unter Sicherheit, ohne passwortlose Anmeldung.
- Betrieb: Passkeys bleiben hinter MHVP_WEBAUTHN_ENABLED (Standard aus) mit MHVP_WEBAUTHN_RP_ID und MHVP_WEBAUTHN_ORIGINS; neuer Fehlercode MHVP-AUTH-0013.
- Portal: Rolle Vertreter mit Seite Vertretung (Vertretener, Zeitraum, Restlaufzeit) und Endpunkt GET /portal/representations; abgelaufene oder widerrufene Vollmachten zeigen den Zustand und gewaehren keinen Zugriff mehr.
- Tickets: POST /tickets/bulk ändert neben dem Status auch Bearbeiter, Team und Priorität mit Teilerfolgsbericht je Ticket, bulk-status bleibt Alias.
- CRM: Die Ticketliste nutzt die Sammelaktion über /tickets/bulk, bietet Sammelzuweisung von Bearbeiter, Team und Priorität und zeigt den Bericht mit den nicht geänderten Tickets.
- Portal: Trigramm-Indizes auf lower(title) und lower(filename) der Dokumente für die Belegsuche (Migration 0299) samt Messtest mit 5.000 Dokumenten.
- Buchhaltung: Kontenplan zeigt Art der Abrechnung je Konto und die Mehrschlüsselverteilung auf Umlageschlüssel.
- Leistung: Messtests für Sollstellungslauf mit 1.000 Verträgen (48,3 s) und Abrechnungsausgabe als PDF (1,7 s) ergänzt, Messwerte unter Last im Runbook Leistungsmessung.
- Portal: Die Rechnungseinreichung des Dienstleisters nimmt optional Netto, USt-Satz und IBAN an und prüft sie auf Plausibilität.
- Belegeingang: Der Belegentwurf aus einer angenommenen Rechnungseinreichung übernimmt Netto, USt und IBAN und zeigt Befunde zum IBAN-Abgleich mit dem Kreditorenstamm und zu möglichen Duplikaten im Rechnungsbuch.
- Banking: Immoware24-Umsatzexport wird im CSV-Import über die Kopfzeile erkannt (Format immoware24_umsatz_csv, Vertrauen zu prüfen, Annahme A-M11-09-01).
- Dokumente: Dokumente zu einem Vertrag mit aktiver Mahnsperre Prozess oder Insolvenz sind automatisch gegen Löschung gesperrt, auch in Löschvorschlägen.
- Dokumente: Eine Löschungssperre am Dokument oder am Vorgang hebt nur eine zweite Person auf, nicht die setzende.
- Dokumente: Neuer Endpunkt GET /documents/{id}/retention-status zeigt Sperren, WEG-Dauerunterlage und den Grund, warum ein Dokument nicht gelöscht wird.
- Portal: abgelaufene, nie angenommene Einladung wird über Portalzugang einladen erneut ausgestellt (neues Token, Ablauf zurückgesetzt), aktive oder gültige Einladung bleibt 409.
- Tests: Abnahmefall PÜ11 (Mieter-Belegeinsicht mit geschwärzter Kopie und Vier Augen Freigabe) als Integrationstest mit Protokoll.
- Import: Der Prüfbericht der Einzelposten vergleicht Kautionen und Darlehen über die Kontoart des Kontenrahmens (Darlehenskonto, verknüpftes getrenntes Kautionsbankkonto) mit der Eröffnungsbilanz.
- Import: Die Rücknahme eines Imports der SEPA-Übersicht entfernt Zahlungsplan und SEPA-Mandat, sofern unverwendet, und öffnet einen beendeten Vorgängerplan wieder.
- Import: Die Rücknahme eines Dokumentindex-Imports entfernt die angelegten Dokumentverknüpfungen, das Dokument bleibt erhalten.
- Tooling: Optionaler Python-Client wird über make client-py aus der OpenAPI-Spezifikation erzeugt (nicht eingecheckt), mit Anleitung unter docs/integrations/python-client.md.
- WEG: Zweckgebundene Rücklagen sind per Kennung nur noch im zugeordneten Objekt und Rechtsträger les- und änderbar.
- Portal: Vollmachten und Portalvorschläge in der Portalverwaltung beachten die Objektzuordnung des Mitglieds.
- Buchhaltung: Rechnungen und Honorar-Buchungsentwürfe beachten zusätzlich den Rechtsträgerbereich (Steuerberaterzugang).
- Arbeitsplatz: Benachrichtigungsmails gehen nur an aktive Mitglieder, täglich gesammelte Einträge blockieren den Sofortversand nicht mehr.
- Mandant: Fehlgeschlagene Mandantenexporte zeigen nur die Fehlerart ohne technische Details.
- Banking: Parallele Archivierung von Bankrohdaten desselben Tages überschreibt kein Original mehr.
- Kommunikation: Fehler beim KI-Antwortentwurf geben keine technischen Details mehr aus.
- Dokumentation: Statuszeilen in docs/plans/M*.md für alle Welle-5-Pakete (T01 bis T16) aktualisiert oder überprüft; Version 1.51.0 umfasst M23-04 (Benachrichtigungsmail-Zustellung je Art), M23 Statuszeile ergänzt.
- Dokumentation: Hilfe-Index (help_index.json) regeneriert und überprüft gegen Handbuch-Kapitel und CRM-Navigation.

## 1.51.0 (01.10.2026) Welle 5 der Lückenliste: Export, Tracing, Banking, Honorar, Rechnungsprüfung, Heizkosten, Rücklagen, Statusmodell, Rechte

- Übersicht: Welle 5 der Lückenliste vom 30.09.2026 mit 16 Paketen (verbliebene offene und teilweise Befunde ohne Entscheidungsbedarf), Migrationen 0289 bis 0297. Schwerpunkte: Mandantenexport als Hintergrundjob, OpenTelemetry-Tracing, Bankrohdaten-Ablage und finAPI-Zustimmungsablauf, Honorarrechnungen mit Storno und Buchungsentwürfen, sachliche Rechnungsprüfung, Heizkostenimport, Benachrichtigungen per E-Mail, Rücklagen je Position und Rücklagenabrechnung, Import-Berichtsarten, einheitliches Statusmodell der Eigentümerabrechnung, KI-Antwortentwurf als eigene Aufgabe, Abnahmefälle PÜ12, W13 und PÜ13, Objektzuordnung in den Restbereichen, Prüfbericht Geheimnisverschlüsselung, Portal-Logo und Barrierefreiheit. Reste und Entscheidungen stehen in docs/OPEN_QUESTIONS.md (T01-01 bis T14-01, S69-01-01, S16-03-01).
- Mandant: Vollständiger Mandantenexport als Hintergrundjob für den Mandantenadministrator (Einstellungen, Mandant) mit JSON je Tabelle und Dokumentdateien als ZIP, Protokoll im Audit.
- Mandant: Exportumfang um offene Posten, Ausgleiche, Bankkonten und Bankumsätze erweitert.
- Beobachtbarkeit: Optionales OpenTelemetry-Tracing (MHVP_OTEL_ENDPOINT, Standard aus) für API, SQLAlchemy, Celery und httpx mit traceparent im Antwort-Header und trace_id im Log.
- Betrieb: Compose-Profil otel mit Collector-Beispielkonfiguration und Runbook beobachtung.md.
- Banking: Rohdaten von Kontoauszugsdateien und finAPI-Abrufen werden unveraendert unter bank/<mandant>/<konto>/<datum>.<ext> abgelegt und mit dem Aufbewahrungsprofil 10 Jahre (Entwurf) indiziert.
- Banking: Das Ablaufdatum der finAPI-Zustimmung wird beim Pruefen der Verbindung aus der Anbieterantwort gelesen, die Erinnerung 10 Tage vorher legt zusaetzlich eine Aufgabe an.
- CRM: Bankverbindungen zeigen dauerhaft das Ablaufdatum der Zustimmung oder einen Hinweis, wenn keines vorliegt.
- Buchhaltung: Honorarrechnungen haben den Status storniert, die Liste ist nach Status filterbar, auch die Gutschrift kann freigegeben werden.
- Buchhaltung: Freigegebene Honorarrechnungen und Gutschriften erzeugen hinter Freigabestufe G1 je einen Buchungsentwurf im Buchungskreis des Zahlers und des Verwalters, Konten nur aus der neuen Kontenzuordnung je Mandant ohne Vorgabe.
- CRM: Seite Verwalterhonorar mit Statusfilter und Aktion Buchungsentwurf.
- Rechnungsprüfung: Sachliche Prüfung als Befunde gegen verknüpften Auftrag (Angebot, Kostengrenze, Status), Dienstleistervertrag, WEG Beschluss, Wirtschaftsplanposition und Rechnungsplan (Betrag, Rhythmus) mit Mengenabgleich je Position und Zuständigkeitsvorschlag Objektverwalter, ohne automatische Freigabe.
- Rechnungsprüfung: Toleranzen für Preis- und Mengenabgleich je Mandant (Standard 0 %) über /accounting/invoice-check-settings.
- CRM Rechnungen: Abschnitt Sachliche Prüfung (Befunde) in der Rechnungsansicht.
- Abrechnung: Heizkostenabrechnungen des Messdiensts werden als eigener Import mit Originaldokument, Zeitraum, Belegsumme, Nutzerzuordnung und Kostenbestandteilen je Einheit erfasst (M17-09).
- Abrechnung: Der Heizkostenimport prüft Summen gegen die Belegsumme, die CO2-Aufteilung nach der hinterlegten Stufentabelle und mögliche Doppelerfassungen im Rechnungsbuch und wird erst nach Prüfung in die Betriebskostenabrechnung übernommen.
- Abrechnung: CSV-Import der Messdienstwerte mit frei wählbarer Spaltenzuordnung ohne Formatannahmen.
- Workspace: Benachrichtigungseinstellungen haben je Art die Zustellung sofort oder täglich, die Mails werden je Benutzer als Sammelmail gesendet (Migration 0293, Beat täglich 07:30).
- CRM: Die Einstellungsseite Benachrichtigungen bietet die Auswahl Zustellung je Art.
- WEG: Zweckgebundene Rücklagen führen Bankkonto des Rechtsträgers, Anfangsbestand und Anfangsjahr (Migration 0294).
- WEG: Neue Entwicklung je Rücklage und Jahr mit Anfang, Zuführung, Entnahme, Steuern, Gebühren, Zinsen und Ende, auch in Abrechnungssnapshot und Vermögensbericht.
- WEG: Erfasste Mittelverwendung je Abrechnung ist abrufbar und im Entwurf entfernbar.
- CRM: Rücklagenseite mit Ändern, Entwicklung je Jahr und Liste der Mittelverwendung mit Belegstatus.
- Import: Neue Berichtsarten Kautionen, Umlageschlüssel mit Einheitenwerten, Zähler, Energieausweise, Dienstleisterverhältnisse und Portalnutzer (nur Status) mit Vorprüfung, Übernahme und Rücknahme (Migration 0297 für die Enum-Werte).
- Abrechnung: Die Eigentümerabrechnung durchläuft jetzt das einheitliche Statusmodell (Beiratsprüfung, ausgeben, fällig, gebucht, gesperrt) mit Vier-Augen bei der internen Freigabe und Statusverlauf; ausgeben, fällig und gebucht nur mit Freigabestufe G3.
- WEG: Neue Rücklagenabrechnung je Jahr als eigenes Abrechnungsobjekt, erzeugt aus den Rücklagendaten der Hausgeldabrechnung, mit gleichem Statusmodell; ausgeben, fällig und gebucht nur mit Freigabestufe G4.
- CRM: Statusanzeige und Statusaktionen in der Eigentümerabrechnung und ein Bereich Rücklagenabrechnung auf der Seite WEG, Rücklagen.
- KI: Neue Aufgabe reply_draft (Migration 0296) erzeugt Antwortentwürfe mit eigenem Anbieterschema, Tonfall und Platzhaltern nach den Stilvorgaben des Postfachs; der Entwurf gilt erst nach ausdrücklicher Freigabe und wird nie automatisch versendet.
- Kommunikation: Kompaktansicht mit Button Antwortentwurf (KI) und Freigabe, Kurz senden bleibt bis zur Freigabe gesperrt, neue Endpunkte POST /mail/messages/{id}/reply-ai und /reply-ai/approve.
- Automatisierung: Neue Aktion Feld setzen für Aufträge (Status angefragt oder in Arbeit, Termin, Zuständiger des Tickets) und Dokumente (Kategorie, Objektverknüpfung) aus einer geschlossenen Feldliste mit Testlauf.
- Tests: Abnahmefälle PÜ12, W13 und PÜ13 (SD-05 bis SD-07) als Integrationstests ergänzt und mit Protokoll vom 01.10.2026 dokumentiert.
- Rechte: Die Portalverwaltung zeigt eingeschränkten Mitgliedern nur Zugänge von Kontakten mit Vertrag auf einem zugeordneten Objekt, Einladungen und Zugangsaktionen außerhalb antworten 404.
- Objektakte: Vollständigkeit, Listen und Abgabeexporte je Objekt folgen der Objektzuordnung, die Gesamtliste fehlender Unterlagen ist gefiltert.
- Importe: Migrationsimporte (Objekt, Buchungskreis, Eröffnungssalden, Wechselanträge, Abgleichberichte, Abnahmeprotokolle) und Altdaten (historische Tickets, Einzelposten) folgen der Objektzuordnung.
- WEG: Prüfberichte des Beirats per Id prüfen die Objektzuordnung über Prüfauftrag und Gemeinschaft.
- Banking: Bankregeln, Regelvorschläge, Sync-Protokoll und Klärungsliste folgen der Objektzuordnung; ein Konto lässt sich nur zugeordneten Objekten zuordnen; die Kontoliste filtert vor dem Limit.
- Sicherheit: Prüfbericht docs/reviews/SECRETS-2026-10-01.md zur Feldverschlüsselung aller Geheimnisklassen (S16-03).
- Kern: Zentrale Maskierung von Geheimnissen (Passwörter, PINs, Tokens, API-Schlüssel, Secrets) in allen Logzeilen, Domain Events und im Audit-Log.
- Kern: Zugriffslog maskiert Tokens im Pfad von Selbstauskunft-Links und Kalender-Abo.
- Vermietung: Selbstauskunft-Link-Token wird nur noch als SHA-256 gespeichert, nicht mehr im Klartext.
- Einstellungen: Das Portal-Logo lässt sich in den Mandanteneinstellungen als PNG oder JPEG hochladen und wird über die Dokument-ID im Branding gesetzt.
- Barrierefreiheit: Formulare in Vertrag, Mandantenverwaltung, Benutzerverwaltung, Profil, Buchungsstorno, FinTS, Belegungsliste, Kontakt- und Objektsuche sowie im Portal (Dokumente, Beirat) tragen einen aria-label.
- Tests: Playwright-Spec für die Detailseite des Wirtschaftsplans (Plan anlegen, Position, Berechnung, Rücksprung).

## 1.50.0 (01.10.2026) Welle 4 der Lückenliste: Rechnungen, Dokumente, Übernahme, Import, Rechte, Kautionen, Portal, Prüfungen

- Übersicht: Welle 4 der Lückenliste vom 30.09.2026 mit 16 Paketen (Reste aus Welle 3 und Prüfungen), Migrationen 0284 bis 0288. Schwerpunkte: Belegmaske mit Anlagen, Rechnungsplan-Erfassung, Sammelrückmeldung Lastschriften, Honorarlauf mit PDF, Jahresübernahme, geschwärzte Kopien und Eingangsadresse je Mandant, Tickets aus der Übernahme-Checkliste, Onboarding-Anlage von Konten und Schlüsseln, Prüfbericht und Rücknahme des Altdatenimports, Einsichtspaket-Frist, Stummschalten, Wartungs-Sammelaktion, include-Parameter und Webhook statement.confirmed, Objektzuordnung in Banking, Abrechnung, WEG, Suche und Assistent, If-Match im CRM, KI-Automatik-Schalter, Kautionszinsverlauf, Portal-Branding und Anmeldestrenge, Leistungs- und Playwright-Tests, Sicherheits- und Geldflussprüfung (docs/reviews), Navigation, Hilfeindex und Handbuch. Reste und Entscheidungen stehen in docs/OPEN_QUESTIONS.md (R02 bis R09).
- Migrationen: Die Rücknahme der Migrationen 0257 und 0278 entfernt Einsichtsereignisse jetzt mit aufgehobener Zeilensicherheit, vorher scheiterte der Rücklauf auf Datenbanken mit Ereigniszeilen.
- API: Das Eingabeschema der KI-Automatikschalter heißt AiAutomationIn, der Name kollidierte mit dem Banking-Schema in der generierten Schnittstelle.
- Rechnungen: Die Belegmaske nimmt jetzt Anlagen und Seiten des Originals als Menge von Dokument-IDs auf (höchstens 50, ungültige oder doppelte IDs sperren das Speichern).
- Rechnungen: Unter Rechnungspläne gibt es eine Erfassungsmaske für neue Rechnungspläne mit Aussteller, Kostenkonto, Betrag, Rhythmus und erster Fälligkeit.
- Lastschriften: Die Abstimmung erlaubt eine Sammelrückmeldung für mehrere ausgewählte Lastschriften in einem Schritt (alles oder nichts).
- Verwalterhonorar: Neuer Honorarlauf mit Vorschau und Bestätigung sowie PDF-Erzeugung und Download der Honorarrechnung im CRM.
- Buchhaltung: Am Buchungskreis lässt sich die Jahresübernahme der Schlussbestände anzeigen und als Entwurf anlegen.
- WEG: Die Gesamtabrechnung kann in der Abrechnungsansicht als PDF heruntergeladen werden (nach interner Freigabe und bei offenem G4).
- Dokumente: Am Dokument gibt es den Abschnitt Geschwärzte Kopien mit Anlage, Freigabe durch eine zweite Person und Liste.
- Dokumente: Einstellungen, DMS enthalten die Eingangsadresse je Mandant mit Absenderliste, Token-Erneuerung und Verteilungsschalter.
- Dokumente: Der Dokumenteingang verteilt Nachrichten eines gemeinsamen Sammelpostfachs nach Token an den Zielmandanten, wenn der Hub die Verteilung eingeschaltet hat.
- Dokumente: Der direkte Upload per signierter URL ist im CRM nur mit Mandantenschalter (Standard aus) aktiv und fällt bei Fehlern auf den Upload über die API zurück.
- Mandant: Die Abfrage der Mandanteneinstellungen liefert wieder, wenn strukturierte Einträge (Eingangsadresse) hinterlegt sind.
- Betrieb: Runbook Objektspeicher um Abschnitt zu Erreichbarkeit und CORS für den direkten Upload ergänzt.
- Objekte: Aus offenen oder angeforderten Punkten der Checkliste Objektübernahme legt der Knopf 'Aufgaben für fehlende Punkte anlegen' interne Tickets am Objekt an (idempotent, Migration 0285, Endpunkt POST /properties/{id}/takeover-checklist/tickets).
- Portal: Eigentümer sehen den Stand der Objektübernahme ihrer Objekte lesend auf der Seite Eigentum (GET /portal/owner/takeover-checklist, ohne Notizen und Dokumente).
- KI-Onboarding: Beim Übernehmen eines Objektvorschlags werden Bankkonten, Umlageschlüssel aller Arten mit Einheitenwerten, Debitorenkonten und Dokumentverknüpfungen in derselben Transaktion angelegt und per Import-Rücknahme wieder entfernt.
- KI-Onboarding: Der Import-Dialog zeigt die Vorschau des Personenabgleichs als Tabelle (neuer Endpunkt POST /onboarding/person-match-batch, schreibt nichts).
- Import: Prüfbericht vergleicht die Einzelposten der Altdaten je Gruppe mit der Eröffnungsbilanz (Vorzeichenregel als Annahme A-Q08-01), ohne automatische Korrektur.
- Import: Kandidatenliste schlägt zu historischen Bankumsätzen Journalbuchungen nach Datum und Betrag vor, ohne automatische Zuordnung.
- Import: Die Rücknahme eines Imports entfernt jetzt auch übernommene Konten, historische Bankumsätze, Tickets und Einzelposten, soweit unverändert.
- Arbeitsbereich: Die globale Suche findet Zählernummern, Rechnungsnummern und Mieter über die Objektadresse.
- Hausverwaltung/WEG: Standardfrist für Einsichtspakete als Mandanteneinstellung (leer bedeutet ohne Ablauf, je Paket überschreibbar), Migration 0287 und Karte unter Einstellungen, Mandant.
- Portal: Belegsuche und Sortierung laufen in der Datenbankabfrage statt im Speicher, Platzhalterzeichen werden maskiert.
- Tests: Positivpfade für Einzelabrechnung als PDF im Eigentümerportal und für den Prüfkontext einer Position mit Auftrag, Zahlung und Umlageschlüssel.
- Portal: Angenommene Rechnungseinreichungen verlinken im Kontakt direkt den Belegentwurf im Belegeingang.
- Workspace: Neue Sammelaktion Alle Benachrichtigungen stummschalten (1 Stunde, 24 Stunden, 7 Tage, aufheben) im Benachrichtigungsmenü, verpflichtende Hinweise bleiben aktiv.
- Tickets: Der Auftragstermin erscheint beim Setzen sofort im internen Kalender (CRM und Portal), der Tagesjob bleibt Auffangnetz.
- Objekte: Sammelaktion Wartungen als erledigt erfassen mit Erledigungsdatum in der Wartungsliste; Wartungen mit Intervall rücken die Fälligkeit vor, statt geschlossen zu werden.
- Tickets: Neuer Endpunkt POST /tickets/bulk meldet die Sammelaktion Status im gemeinsamen Teilerfolgsbericht (je Ticket Erfolg oder Fehlercode).
- Listen: Kontakte, Objekte, Vertraege, Dokumente und Rechnungen bieten include an (Objekte, Rechtstraeger, Vertragspartei und Objekt, Objekte, Kreditor); eingebettete Objekte beachten die Objektzuordnung.
- Webhooks: statement.confirmed wird bei Ausgabe der Mietabrechnung und bei interner Freigabe der Hausgeldabrechnung erzeugt.
- Dokumentation: Annahmen A-R07-01 und A-R07-02 sowie offene Frage R07-01 zum fehlenden Protokollabschluss fuer meeting.closed.
- Rechte: Die Objektzuordnung je Mitgliedschaft wirkt jetzt auch im Banking (Bankkonten, Umsätze, Zahlungsaufträge und Sammler nach Heimatobjekt oder Kontozuordnung, fremde Datensätze 404).
- Abrechnung: Betriebskosten-, Eigentümerabrechnungen und Verbrauchsinformationen außerhalb der Objektzuordnung antworten 404, die Listen sind gefiltert.
- WEG: Abrechnungen, Wirtschaftspläne, Versammlungen, Beschlüsse, Sonderumlagen, Darlehen, Maßnahmen, Versicherungsfälle, Prüfaufträge, Vermögensberichte und Einsichtsanfragen folgen der Objektzuordnung.
- Buchhaltung: Auswertungen eines Buchungskreises und das Umsatzsteuerprofil je Objekt folgen der Objektzuordnung.
- Objekte: Übernahme, Stammdaten, Kreditoren, Teiländerung, Bankkonten und Dienstleister, Verwaltungsende und Aushänge prüfen die Objektzuordnung; Dienstleisterverträge und Kautionsabrechnungen ebenso.
- Suche: Die globale Suche zeigt nur Treffer der zugeordneten Objekte und übernimmt dafür Rechtsträger- und Objektzuordnung des Benutzers.
- Assistent: Die Nachschlagewerkzeuge beachten die Objektzuordnung; ein geöffneter Datensatz außerhalb wird wie nicht vorhanden behandelt.
- CRM: Verträge, Tickets, Dokumente und Eingangsrechnungen senden beim Speichern den beim Laden gemerkten Änderungsstand (If-Match) und melden einen zwischenzeitlichen Fremdstand mit Hinweis zum Neuladen.
- KI: Neue Schalter für automatische KI-Läufe (Einstellungen, KI), beide standardmäßig aus, mit GET und PUT /ai/automation.
- Vermietung: Neue oder geänderte Mieterhöhungsfälle stoßen bei eingeschaltetem Schalter und freigegebenem Anbieter die KI-Prüfung an und verknüpfen sie als ai_check_id.
- KI: Der nächtliche Sammellauf klassifiziert E-Mails ohne Vorschlag (höchstens 100 je Mandant und Nacht) hinter einem Mandantenschalter.
- Postfach: Die Kompaktansicht zeigt zum Antwortvorschlag Tonfall und Platzhalter ohne Wert aus dem Ergebnisobjekt draft_reply.
- Verträge: Kautionen haben einen Zinssatzverlauf je Kautionskonto mit Gültigkeitsdatum, die Zinsart Zinssatz der Kaution rechnet die Kautionsabrechnung bei Vertragsende taggenau mit diesem Verlauf.
- Verträge: Die jährliche Zinsgutschrift der Kaution entsteht als Entwurf (einzeln oder im Jahreslauf), die Bestätigung erfasst nur eine Zinsbewegung ohne Buchung und Zahlung, Versicherung, Bürgschaft und Patronatserklärung werden nicht verzinst.
- Portal: Das Kundenportal zeigt je Mandant Logo, Anzeigename, Farben sowie Impressum und Datenschutz aus den Mandanteneinstellungen und bleibt ohne Angaben neutral.
- Plattform: Das Branding ist je Portal-Domain öffentlich abrufbar (inklusive Logo als PNG oder JPEG), die Einstellungen kennen Anzeigename, Impressum und Datenschutz des Portals.
- Portal: Die Anmeldestrenge ist je Mandant einstellbar, Standard bleibt die Wahl je Konto, die Option Pflicht verlangt bei der Anmeldung per Link immer den E-Mail-Code.
- Leistung: Konnektor-Attrappe fuer den Bankabruf von 100 Konten und Abrechnungsdaten-Seed fuer 100 Einheiten, Leistungstests laufen mit MHVP_PERF=1, Messwerte im Runbook Leistungsmessung.
- E2E: Playwright-Kernpfade für die neuen CRM-Seiten der Wellen 2 und 3 (Zahllauf, Verwalterhonorar, Kreditoren, Rechnungspläne, Bank, SEPA, Lizenzen, Zusammenführung, Datenschutz, Mietspiegel, Benachrichtigungen, Rücklagen) gegen das Backend ergänzt.
- E2E: Playwright-Kernpfade im Portal für Dokumentensuche, Hausgeldabrechnungen und Rollenwechsel ergänzt.
- Dokumente: Der ZIP-Massenupload begrenzt zusätzlich die Gesamtgröße aller entpackten Dateien auf das Achtfache der Einzelgrenze.
- Portal: Der E-Rechnungs-Upload liest Dateien nur bis zur Größengrenze und bereinigt den Dateinamen.
- Portal: Antworten der Verwaltung im Portal-Chat sind nur zu Meldungen zugeordneter Objekte möglich.
- Portal: Das Inhaltsverzeichnis des Sammel-Downloads schützt Titel und Dateinamen vor Formelausführung in Tabellenprogrammen.
- Anmeldung: Ein Passwortwechsel beendet alle Sitzungen des Nutzers, sobald deren Zugangstoken abläuft.
- Datenschutz: Freigabe, Ablehnung und Ausführung von Löschanträgen sperren den Antrag gegen parallele Bearbeitung.
- Zahlungsverkehr: Zahlungsauftrag aus einer Rechnung sperrt den offenen Posten, parallele Anfragen erzeugen keinen zweiten Auftrag.
- Verwalterhonorar: Der Honorarlauf prüft den bereits abgerechneten Zeitraum erneut unter Sperre, parallele Läufe stellen keine Doppelrechnung aus.
- Betriebskostenabrechnung: Ergebnisbuchungen einer korrigierten Version erst nach Storno der Ergebnisbuchungen der ersetzten Version.
- WEG-Abrechnung: Kostenübernahme aus der Buchhaltung überspringt im Jahr stornierte Buchungen samt Storno und meldet Stornos bereits übernommener Buchungen.
- Mahnwesen: Verzugszinsentwurf wird bei aktiver Mahnsperre am Vertrag oder Posten abgelehnt.
- Navigation: Hauptmenüpunkt Aufträge und Kachel Benachrichtigungen in der Einstellungsübersicht ergänzt.
- Hilfeindex: Aufträge und zehn weitere Handbuchkapitel den CRM-Seiten zugeordnet, Index neu erzeugt.
- Oberfläche: Verwalterhonorar, Kreditoren und Rechnungspläne zeigen Ladefehler sichtbar an.
- Barrierefreiheit: aria-label an Formularen in CRM (11) und Portal (8), Spaltenkopf Saldo übersetzbar.
- Tests: surface-consistency.test.ts prüft Menü, Fehlerzustände und Formularbeschriftung.
- Handbuch: Abschnitte Schadenbearbeiter, Mandantenübersicht und Löschvorschläge ergänzt, Kapitelindex vollständig.
- Regeln: Index um neun fehlende Regeldateien ergänzt.
- Pläne: Statuszeilen Version 1.49.0 mit den Lieferungen der Welle 3 nachgezogen.

## 1.49.0 (01.10.2026) Welle 3 der Lückenliste: Oberflächen, Dokumente, Datenschutz, Assistent, Import, WEG, Portal, API

- Übersicht: Welle 3 der Lückenliste vom 30.09.2026 mit 17 Paketen (Reste aus Welle 2), Migrationen 0271 bis 0283. Schwerpunkte: Freigabeentscheidungen mit Snapshot-Hash und gepflegte Offene-Posten-Tabelle, CRM-Oberflächen für Mahnwesen, Zahllauf, Rechnungspläne, Stammdaten, Vollmachten und Teams, Dokumentablage mit Ablagezone, ZIP-Import, Eingangsadresse, Drive-Abgleich und Schwärzungskopien, Kontakt-Zusammenführung und Datenschutzoberfläche, Chat-Aktionen und Modellkaskade des Assistenten, Objektübernahme-Checkliste und Personenabgleich, weitere Immoware24-Berichtsarten, WEG-Rücklagenbindung und Gesamtabrechnung, Portal-Belegsuche und Eigentümerabrechnung, Benachrichtigungseinstellungen und Sammelaktionen, generische Listenparameter und Massenendpunkte, Objektzuordnung je Mitgliedschaft mit ETag und Schlüsselrotation, Mietspiegel und Exposé, Honorar-PDF und Jahresübernahme, Mahnlauf-Fehlerstatus und gespeicherte Filter. Reste und Entscheidungen stehen in docs/OPEN_QUESTIONS.md (Q01 bis Q16).
- Buchhaltung: Zentrale Freigabeentscheidung mit Hash des Vorgangs für Zahlungs- und Rechnungsfreigaben, Änderungen setzen sie dauerhaft auf ungültig (S69-02).
- Bank: Hinweis bei möglicher Personengleichheit zweier Freigebender über getrennte Kontakte (E-Mail, Name und Geburtsdatum), ohne Sperre (S69-03).
- Buchhaltung: Offene Posten zum Stichtag als gepflegte Lesekopie mit Nachtjob und manueller Neuberechnung (S69-04).
- Objekte: Kreditorenkonto entsteht automatisch beim Anlegen eines Dienstleisterverhältnisses (M10-05).
- Einstellungen: Schalter für die monatliche Vorschau der Sollstellungen, Standard aus (P02-03).
- CRM Mahnwesen: Je Mahnfall Prüfhinweise, Zinsaufschlagsvorschlag, Zinsberechnung je Basiszinssatzzeitraum mit Zinsentwurf, Zustellnachweise und Mahnsperren je Posten; Basiszinssatzhistorie auf der Mahnwesen-Startseite.
- CRM Bank: Bankrückmeldung und Abstimmung je Lastschrift in der Lastschriftliste sowie Banklimits und Einreichungsfristen je Auftraggeberkonto im Zahllauf.
- CRM Rechnungen: Rechnungspläne bearbeitbar, Knopf zum Anlegen der Kreditorenkonten und optionale Prüfangaben (Leistungsort, Aussteller, Anzahlung, Einbehalt, Skonto, Reverse Charge, Bauabzugsteuer) bei der Erfassung.
- Dokumente: Direkter Upload und Download über signierte URLs des Objektspeichers mit denselben Prüfungen wie der Upload über die API.
- Dokumente: Temporäre Uploads unter tmp/ erhalten eine Lebenszyklusregel und werden täglich nach einem Tag entfernt.
- Dokumente: ZIP-Massenupload legt jede Datei einzeln ab, listet abgewiesene Dateien mit Grund und wird als Importlauf protokolliert.
- Dokumente: Geschwärzte Belegkopien mit Grund, Umfang und Bearbeitungsschritten, Original bleibt unverändert, Freigabe für das Portal im Vier-Augen-Prinzip.
- Dokumente: Löschungssperren mit Sperrart, Weitergabe der Sperre zwischen Original und abgeleiteten Dokumenten, Kennzeichen WEG-Dauerunterlage und Aufbewahrungsprofil je Rechtsträgerart.
- Dokumente: Eingangsadresse je Mandant mit Plus-Adressierung und optionaler Absenderliste für weitergeleitete Belege.
- Dokumente: Abgleich der Google-Drive-Änderungen mit Cursor, entfernte Spiegeldateien werden vermerkt, nichts wird gelöscht.
- CRM: Ablagezone in der Kopfleiste für Dateien und ZIP-Archive mit Objekt- und Kategorievorgabe.
- CRM: Seite Briefe und Vorlagen mit PDF-Vorschau, Serienbrief und Vorlagenversionen.
- CRM: Kategoriebaum in den Einstellungen mit Zuordnung zu Paperless-Dokumenttyp, Paperless-Tag und Drive-Ordner.
- Kontakte: Zusammenführung zweier Kontakte als Vorschlag mit Prüfung, Ausführung im Vier-Augen-Prinzip und Audit, alle Verweise (Verträge, Parteien, Bankkonten, Tickets, Dokumente) gehen auf das Ziel über, die Quelle bleibt als zusammengeführt erhalten (Migration 0273, Seite Kontakte, Zusammenführen).
- Suche: Die globale Suche findet Verträge zusätzlich über den Namen der Partei, Einheiten über die Objektstraße und Dokumente über Titel und Dateiname.
- Datenschutz: Neue CRM-Seite unter Einstellungen mit Löschprofilen und Freigabe, Löschanträgen mit Sperrgründen und Vier-Augen, Register der Auftragsverarbeiter sowie Verzeichnis-Entwurf zum Herunterladen.
- Datenschutz: Die Sperrprüfung der Löschanträge überspringt Tabellen, deren Migration im verbundenen Schema noch fehlt.
- CRM Kontakte: Vertragsparteien werden im Reiter Beziehungen angelegt, bearbeitet (Name, Mitglieder, Rollen, Anteile) und gelöscht.
- CRM Einstellungen: Neue Seite Kontakt-Tags zum Umbenennen, Zusammenführen und Löschen von Tags des Mandanten.
- CRM Einstellungen: Neue Seite Teams zum Anlegen, Ändern und Löschen von Ticketteams.
- CRM Einheiten: Historie der Umsatzsteueroptionen mit Zeitraum und Belegung sowie Erfassung neuer Zeiträume.
- CRM Objekte: Bildgalerie mit Upload, Reihenfolge und Entfernen sowie Belegungsliste mit Stichtag und Leerstandsfilter.
- CRM Kontakte: Portalstatus neben dem Namen und Vollmachten im Portal (Liste, Anlage mit Vollmachtsdokument, Widerruf) im Reiter Freigaben.
- CRM Tickets: Gebäude, Beginn und Wiedervorlage im Anlageformular und am Ticket, Sammelzuweisung des Bearbeiters in der Ticketliste.
- Portal: GET /portal-admin/representations nennt zusätzlich Kontakt und Anmeldeadresse des Vertreters.
- KI-Assistent: Chat-Aktionen Objekt anlegen (Vorschlag im Status Übernahme), Dokument ablegen, Portaleinladung vorbereiten und Brief aus Vorlage als Entwurf, jeweils erst nach Bestätigung und ohne Versand.
- KI-Assistent: Nach bestätigtem Import oder Chat-Aktion bietet der Chat Folgeschritte an (Portaleinladungen, Verträge, Formularanfrage, Einheiten, Unterlagen).
- KI-Assistent: Reiter Assistent am Kontakt und Bereich Assistent am Objekt öffnen den Chat mit dem Datensatz als Kontext.
- KI-Gateway: Kaskade vom kleinen zum großen Modell bei Schemafehler oder Konfidenz unter der eingetragenen Schwelle, Kosten je Stufe getrennt im Lauf ausgewiesen.
- KI-Gateway: Bei erreichtem Monatsbudget erhalten die Einstellungsberechtigten eine Benachrichtigung über die Sperre.
- KI-Gateway: Nächtlicher Sammellauf für zurückgestellte, nicht zeitkritische KI-Läufe.
- Vermietung: KI-Plausibilität des Mieterhöhungsfalls als eigene Aufgabe mit Hinweisen und Schweregrad, verknüpft am Fall, ohne Freigabe oder Rechtsprüfung.
- Portal: KI-Vorqualifizierung des Chats läuft bei freigegebenem Anbieter mit maskiertem Text über das KI-Gateway, nur als Vorschlag für die Verwaltung.
- KI-Kontierung: Historische Bankzuordnungen aus der Datenübernahme dienen als nur lesende Lernbeispiele.
- Objekte: Checkliste Objektübernahme mit sieben Kategorien und Status je Punkt, API und Anzeige im CRM am Objekt.
- KI Onboarding: Personenabgleich gegen das Adressbuch (IBAN, E-Mail, Name, Adresse) mit Schwellwerten je Mandant, Treffer werden im Objektimport verknüpft, Nichttreffer als unvollständiger Kontakt angelegt.
- Import: Neue Berichtsarten Kontenplan, SEPA-Übersicht, Bankumsätze (Historie), Offene Posten, DMS-Dokumente und historische Tickets im Immoware24-Importassistenten mit frei zuordenbaren Spalten, Testlauf und idempotenter Übernahme (M8-02 bis M8-07).
- Import: SEPA-Übersicht legt den Zahlungsplan an und erfasst ein Mandat nur mit vollständigem Nachweis, der Einzug bleibt bis G2 gesperrt.
- Import: Historische Bankumsätze werden als nicht abgleichbare Historie bis zum Migrationsstichtag übernommen und über die Buchungsnummer dem Migrationsjournal zugeordnet (Migration 0277).
- Import: Einzelposten offener Posten, Guthaben, Kautionen, Rücklagen, Darlehen und Sonderumlagen mit Ursprungsfälligkeit und Teilzahlung sowie historische Tickets sind nur lesend abrufbar (/imports/immoware24/history).
- WEG: Zahlungen werden je zweckgebundener Rücklage ausgewiesen, wenn der Vorschuss der Einheit an genau eine Rücklage gebunden ist; Sollstellung und Zahlungsplan tragen die Zweckbindung (Migration 0278).
- WEG: Neue CRM-Seite Rücklagen mit Anlage, Mittelverwendung und der Entwicklung je Rücklage als eigener Block.
- WEG: Die Gesamtabrechnung steht als PDF auf dem Briefbogen des Mandanten bereit (Entwurf, nur mit G4 und nach interner Freigabe).
- WEG: Der Wirtschaftsplan zeigt im CRM den Vergleich mit dem Vorjahr je Komponente und Position; beim Anlegen sind Zahlungsrhythmus, Fälligkeitstag und Vergleichsplan wählbar.
- WEG: Vierteljährliche und jährliche Vorschüsse lassen sich in die Vertragszahlungen übernehmen (Zahlungsplan je Vertrag, Periodenbetrag in der Vorschau).
- Buchhaltung: Die Abrechnungsarten Sonderumlage und Heizung stehen für Konten zur Wahl.
- WEG: Einsichtsanfragen protokollieren die Benachrichtigung als eigenes Ereignis, prüfen die Eigentümerstellung des Antragstellers und zeigen Ablauf und Widerruf der Bereitstellung im CRM.
- WEG: Prüfaufträge zeigen den Änderungsverlauf je Position und erlauben die Bestätigung einer Berichtsversion im CRM; die Regel Prüfrolle ohne Buchungsrecht ist dokumentiert und getestet.
- Portal: Belegliste mit Suche, Sortierung und Sammel-Download als ZIP mit Index.
- Portal: Rollenwechsel fuer Konten mit mehreren Portalrollen, portal_roles in /portal/me aus core/auth/portal_roles abgeleitet.
- Portal: Eigentuemer erhalten die freigegebene Einzelabrechnung Hausgeld als PDF, ihren Anteil an Wirtschaftsplan und Sonderumlage, Umlageschluessel und Mieterertraege je Objekt.
- Portal: Dienstleister lesen eine XML-E-Rechnung ein und uebernehmen Nummer, Datum und Betrag als Vorschlag.
- Portal: Beirat sieht zu jeder Pruefposition Buchung, Rechnung, Auftrag, Zahlung, Umlageschluessel, Vorjahr und fehlende Unterlagen.
- Tickets: external_comments und external_attachments werden im Portal durchgesetzt, Standard open (Migration 0279).
- Kalender: Der Tagesjob legt aus dem Auftragstermin eines Auftrags einen internen Kalendereintrag an (ohne Einladung) und führt ihn bei Terminänderung nach.
- Benachrichtigungen: Neue Seite Einstellungen, Benachrichtigungen mit Kanal in der App und per E-Mail je Art und Stummschaltung; Fristen, SLA-Eskalation und Bankzustimmung bleiben verpflichtend (Migration 0280).
- Arbeitsplatz: Sammelaktionen in der Dokumentliste (Kategorie setzen, mit Objekt verknüpfen) und in der Fristenliste (Markierte erledigen).
- Automatisierung: Neue Regelaktionen Feld setzen (Notizfelder von Objekt, Kontakt, Vertrag, anhängend) und Entwurf an Dienstleister (nie automatisch versendet).
- Portal: Die angenommene Rechnungseinreichung eines Dienstleisters legt einen Belegentwurf im Belegeingang an und setzt den Auftrag auf abgerechnet, ohne Buchung.
- API: Allgemeine Listenparameter filter[feld], sort, fields und include an Kontakten, Objekten, Verträgen, Tickets, Dokumenten und Eingangsrechnungen; nicht angebotene Werte werden mit 422 abgelehnt.
- API: Massenendpunkte POST /contacts/bulk, /properties/bulk und /contracts/bulk mit Teilerfolgsbericht je Eintrag.
- Automatisierung: Jobschalter je Mandant wirken jetzt in Bankabruf, Wochenübersicht Bank, Mahn- und Sollstellungsvorschau, Verbrauchsinformation, Erinnerungen, Tagesübersicht und Fristenhinweisen.
- Ereignisse: invoice.received, invoice.approved, invoice.paid, dunning_case.created, dunning_case.sent, work_order.created, work_order.completed, document.shared und ai_proposal.decided werden erzeugt.
- Berechtigungen: Die Objektzuordnung je Mitgliedschaft filtert jetzt Objekte, Einheiten, Verträge, Tickets, Dokumente und Eingangsrechnungen; Datensätze fremder Objekte antworten mit nicht gefunden.
- Schnittstelle: Verträge (Bemerkungen), Tickets, Dokumente und Eingangsrechnungen liefern ein ETag und lehnen Änderungen mit veraltetem If-Match mit 412 ab; ohne Header bleibt das Verhalten unverändert.
- Sicherheit: Neues Werkzeug python -m mhvp.core.key_rotation stellt alle verschlüsselten Felder und zugehörige IBAN-Fingerabdrücke mit Probelauf und Protokoll ohne Klartext auf einen neuen Master-Schlüssel um.
- Vermietung: Das Exposé-PDF enthält jetzt die Bilder der Anzeige (PNG und JPEG, höchstens acht), ein Button an der Einheit legt es im Dokumentenbereich ab.
- Vermietung: Der Interessentenabgleich ist im CRM an der Einheit mit Anzeige abrufbar und reiht die Interessenten nach erfüllten, nicht erfüllten und nicht prüfbaren Kriterien.
- Vermietung: Neue Seite Mietspiegel zur Pflege der Werte je Gemeinde (Erfassen, Löschen, CSV mit Vorschau); im Mieterhöhungsfall im Entwurf wird die Spanne (Untergrenze, Mittelwert, Obergrenze) per Schnittstelle übernommen und der Fall neu geprüft.
- Verträge: Das Vertragsformular zeigt die Mieterhöhungsfälle des Vertrags und warnt, wenn ein offener Fall vor Ablauf der Mieterhöhungssperre wirksam wird; Migration 0281 ergänzt ai_check_id am Mieterhöhungsfall mit Verweis auf die KI-Prüfung.
- Postfach: Antwortentwürfe der KI tragen ein eigenes Schema draft_reply (Text, Tonfall, Platzhalter, unbekannte Platzhalter, Postfachstil) und die Stilregeln sind in den Postfacheinstellungen pflegbar.
- Postfach: HTML-Mails erscheinen in einem Sandbox-Rahmen ohne Skripte mit Content Security Policy, Bilder aus dem Internet werden erst nach Klick geladen.
- Zustellung: Der Kanal Post legt den Postauftrag automatisch an, sofern der Postdienst freigegeben ist und das Recht communication:approve vorliegt (manueller Anbieter immer), sonst bleibt die Zustellung vorbereitet.
- Buchhaltung: Honorarrechnungen und Gutschriften können als PDF auf dem Briefbogen des Mandanten abgelegt werden (Migration 0282), die Gutschrift-XRechnung lässt sich als Dokument ablegen.
- Buchhaltung: Der Honorarlauf stellt alle fälligen Honorare eines Zeitraums gesammelt aus (Vorschau vorab, eigene lückenlose Rechnungsnummer je Rechnung, Fehler einzelner Honorare stoppen den Lauf nicht).
- Buchhaltung: Neue USt-Übersicht je Objekt und Kostenstelle als Entwurf (Objekt über die Einheit der Buchungszeile).
- Buchhaltung: Jahreswechsel-Übernahme erzeugt Abschluss- und Anfangsbestandsentwurf aus den Schlussbeständen, Buchen des Anfangsbestands nur nach Prüfung durch eine zweite Person.
- Buchhaltung, Mahnwesen: Der geplante Mahnlauf legt bei einem Fehler je Mandant einen Lauf mit Status Fehlgeschlagen und Fehlertext an (Migration 0283) und läuft für die übrigen Mandanten weiter; Betriebskennzahl dunning_runs_failed_24h löst den Alarm aus.
- Workspace: Gespeicherte Filter auch für Bankbewegungen und die Rechnungsliste (Rechnungsliste filterbar nach Nummer, Prüfstatus und Buchungsstatus).
- Betrieb: Prüfskript scripts/backup-offsite-check.sh für den Offsite-Lauf als Trockenlauf gegen ein lokales Verzeichnis.
- Betrieb: Lastdaten-Seed mit 100 Einheiten und 100 Bankkonten für die Leistungstests, Prüfung des Login-Limits hinter dem BFF dokumentiert.

## 1.48.0 (01.10.2026) Welle 2 der Lückenliste: Buchhaltung, Bank, Zahlläufe, Mahnwesen, Abrechnung, WEG, Postfach, Portal, Sicherheit, Datenschutz

- Übersicht: Welle 2 der Lückenliste vom 30.09.2026 mit 22 Paketen und 20 parallelen Agenten, Migrationen 0250 bis 0270. Umgesetzt sind Betreiberentscheidungen 2 bis 13 nach Alternative a (Zahlungsrückmeldungen pain.002 und camt.054, Mahnsperren und Zinsentwurf, KI-Kontierung Stufe 2, IMAP-Abruf, Portal-Chat und Vertreterrolle, Mietspiegel-Datenmodell, Passwortregeln und WebAuthn-Vorbereitung, Datenschutzmodul, Steuerauswertungen, Vorschau-Zeitpläne, Preismodell), die Kompaktansicht für Mail und Ticket, die Fehlerbehebungen HTML-Mails und Ticket-Dokumente sowie die Betreiberwünsche Rechtsträger-Zeile und getrennte Banken ausgeblendet. Reste stehen in docs/plans/LUECKENLISTE-2026-09-30.md und docs/OPEN_QUESTIONS.md (P01 bis P21).
- Buchhaltung: Verteilung eines Kostenkontos auf Umlageschlüssel per API und im Kontenblatt, Summe muss genau 100 % ergeben.
- Buchhaltung: Buchungssätze im CRM als Entwurf erfassen, buchen, mit Grund stornieren, Anfangsbestände durch zweite Person prüfen und Buchungskreis festschreiben.
- Buchhaltung: Kontenplan im CRM mit Ergänzen, Ändern (Buchungstexte, Umsatzsteueroption, Kassenbericht, Sichtbarkeit) und Deaktivieren von Konten.
- Buchhaltung: Kontenblatt je Konto mit Anfangssaldo, Laufsaldo und Zeitraumfilter im CRM.
- Buchhaltung: Kreditorenkonten werden per Abgleich aus den Dienstleisterverhältnissen angelegt und zugeordnet.
- Buchhaltung: Eigene Vorgänge für Kostenkorrektur und Zinsbuchung als Entwurf, Steuer auf Zinsen bleibt offene Frage.
- Buchhaltung: Sollstellungsposten tragen Vertragsversion, Zahlungsplan, Geltungsbeginn, Grund und Quelldokument als Nachweis.
- Buchhaltung: Eine Betragsänderung nach gebuchter Sollstellung erzeugt einen manuellen Differenzposten mit Verweis auf den gebuchten Posten.
- Buchhaltung: Sollstellungsläufe sind je Monat, Bereich und Status auflistbar, Posten eines Laufs filterbar.
- Buchhaltung: Monatlicher Vorschau-Lauf der Sollstellung am 1. um 05:00 je Mandant zuschaltbar, gebucht wird weiter von Hand.
- Verwalterhonorar: Einstellungen lassen sich auflisten, ändern, beenden und ohne Rechnungen löschen.
- Verwalterhonorar: Rechnungen haben einen Leistungszeitraum, je Zeitraum wird nur eine Rechnung ausgestellt, fällige Zeiträume sind als Vorschau abrufbar.
- Verwalterhonorar: Honorarrechnungen sind auflistbar, freigebbar und per Gutschrift mit eigener Nummer stornierbar.
- CRM: Neue Seite Buchhaltung, Verwalterhonorar mit Einrichten, Ausstellen, Freigeben, XRechnung laden, prüfen, ablegen und Stornieren.
- Heizkosten: Die Verbrauchsinformation läuft wie spezifiziert am 3. des Monats.
- Rechnungseingang: Leistungsort, Steuerangaben des Ausstellers, Anlagen, Vertragsbezug und Pflichtangaben-Checkliste nach PÜ01 an der Eingangsrechnung.
- Rechnungseingang: Skonto wird nachgerechnet, Anzahlung und Sicherheitseinbehalt mindern den Zahlbetrag, Reverse Charge und Bauabzugsteuer sind Prüfkennzeichen.
- Rechnungseingang: Hinweise auf verbundene Unternehmen, Interessenkonflikte, inhaltsgleiche Dateien und geänderte IBAN gegenüber der Vorversion.
- Rechnungseingang: Gutschriften brauchen die Ursprungsrechnung und werden nur innerhalb deren Betrag gebucht.
- Rechnungseingang: Prüfschritte dokumentieren Vertretung und geprüfte Seiten, Positionen und Anlagen.
- Kreditoren: neue Übersicht mit Saldo, offenen Posten und Kontoauszug je Kreditor (API und CRM).
- Rechnungspläne: Liste, Ändern, Beenden und Löschen, Monatsende über Ankertag, Leistungszeitraum und Umsatzsteuer im Entwurf (API und CRM).
- Belegeingang: E-Rechnungen speichern Profil, Prüfergebnis, Prüfsummen und hybride Abweichungen; externes Validatorergebnis erfassbar.
- E-Rechnung: Gutschrift zur stornierten Honorarrechnung als XRechnung CreditNote 381 mit Ursprungsbezug.
- Zahllauf: Vorschau zahlbarer Rechnungen je Rechtsträger mit Auftraggeberkonten, fälligen Lastschriftläufen und fehlenden Vorabinformationen, Sammelanlage von Auftragsentwürfen (Seite Bank, Zahllauf).
- Zahllauf: Einzel- und Tageslimit je Auftraggeberkonto, Zahlungsdatei über dem Limit wird abgelehnt, Hinweis auf Empfängerüberprüfung der Bank.
- Zahllauf: Auszahlungen ohne Rechnung (Eigentümerauszahlung, Guthaben, Kautionsrückzahlung) als Entwurf mit Vier-Augen-Freigabe.
- Bankstatus: Import von pain.002 und camt.054, Statusabgleich je Auftrag über die Ende-zu-Ende-Referenz, Wiederholung ohne Wirkung, keine Buchung.
- Lastschriften: Rückmeldung je Lastschrift (angenommen, abgelehnt, eingezogen, zurückgegeben) und Abstimmung mit den offenen Posten.
- Lastschriften: Einreichungsfristen je Verfahren (FRST, RCUR) und Frist der Vorabinformation als konfigurierbare Prüfung, gekennzeichnet zu verifizieren.
- Zahllauf: wöchentliche Vorschau montags 08:00, je Mandant einschaltbar, erzeugt nur eine Liste.
- Mahnwesen: Zustellnachweise (Einschreiben, Post, E-Mail, Portal) mit Datum, Referenz und Dokument je versendetem Mahnfall erfassbar.
- Mahnwesen: Basiszinssätze mit Gültigkeitsbeginn und Quelle pflegbar; Verzugszinsen werden bei Basiszinsänderungen zeitanteilig je Zeitraum berechnet und am Fall ausgewiesen.
- Mahnwesen: Mahnsperre je offenem Posten mit Grund (Ratenplan, bestrittener Posten, Aufrechnung, Prozess, Insolvenz); gesperrte Posten gehen in keinen Mahnlauf ein.
- Mahnwesen: Prüfhinweise zu Verjährung, Verzugsbeginn und gerichtlichen Schritten am Mahnfall, ohne berechnetes Verjährungsdatum.
- Mahnwesen: Verzugszinsen nach Freigabe des Laufs auf Anforderung als Buchungsentwurf, Buchung nur über die Vier-Augen-Freigabe bei geöffnetem G1.
- Mahnwesen: Vorschlag des Zinsaufschlags aus dem Verbraucherkennzeichen des Schuldners, ohne automatische Anwendung.
- Abrechnung Miete: Ergebnisbuchung als Buchungsentwurf je Mieter (Forderung bei Nachzahlung, Gutschrift bei Guthaben) nur mit Freigabestufe G3 im Status fällig; Status gebucht erst nach Buchung aller Entwürfe.
- Abrechnung Miete: Kostenaufstellung je Position (Kostenart, Gesamtbetrag, Schlüssel, Anteil) im Anschreiben und im Ergebnis je Vertrag.
- Abrechnung Miete: Zugang je Mieter mit Versandart, Datum und Nachweis erfassbar, Einwendungsfrist als Orientierung angezeigt.
- Abrechnung Miete: unterjährige Abrechnung nur mit ausgewiesenem Zweck, Einstellungen für Anschreiben und Heizkosten.
- Abrechnung Miete: Differenzbericht zwischen neuer und ersetzter Version je Mieter und Position.
- Abrechnung Miete: Belegeinsicht mit Anfrage, Bereitstellung, Schwärzungsvermerk, Einwendung und Abschluss (API).
- Abrechnung Miete: Kostenpositionen und Kopfdaten im Entwurf änderbar und löschbar.
- CRM Abrechnung: Bereich Anschreiben und Zugang je Mieter mit PDF-Vorschau und Ablage als Entwurf.
- Verbrauchsinformation: Ersatzprozess ohne Portal mit druckbarer Fassung, Liste nicht zugestellter Einheiten und Zustellnachweis.
- WEG: Zweckgebundene Rücklagen mit Entnahmen, Steuern, Gebühren und Zinsen je Abrechnung und Entwicklung je Rücklage in der Hausgeldabrechnung.
- WEG: Kostenpositionen lassen sich aus den gebuchten Belegen eines Kontos übernehmen; das Abrechnungspaket zeigt Buchung, Beleg, Zahlung und fehlende Belege je Position.
- WEG: Ausweis belegter Lohnanteile nach § 35a EStG je Kostenposition und Einheit mit Sperre gegen doppelten Ausweis desselben Belegs.
- WEG: Quelle einer Teilverteilung als Beschluss oder Dokument statt Freitextprüfung.
- WEG: Kennzahlen und Debitorenliste der Hausgeldabrechnung (verteilte Kosten, Vorschuss Soll und Ist, Rückstände).
- WEG: Wirtschaftsplan mit Bezeichnung, Stichtag, Zahlungsrhythmus, Fälligkeit, Fortgeltung, Vergleichsgrundlage und Abweichung je Position; ältere Pläne werden bei Übernahme als überholt markiert.
- WEG: Einzelabrechnung je Einheit als PDF-Entwurf nach interner Freigabe, nur mit Freigabestufe G4.
- WEG Prüfung: Prüfaufträge speichern Berechtigungsnachweis und Datenstand, beides erscheint im Prüfbericht.
- WEG Prüfung: Prüfpositionen sind nach Betrag, fehlendem Beleg, Risikohinweis und Prüfstatus filterbar, Risikohinweis je Position ergänzt.
- WEG Prüfung: Jede Änderung einer Prüfposition wird mit altem und neuem Wert im Verlauf protokolliert.
- WEG Prüfung: Prüfberichtsversionen können einmalig bestätigt werden, ohne Beschluss oder Entlastung auszulösen.
- WEG Einsicht: Bereitstellungspakete lassen sich befristen und widerrufen, danach ist der Abruf gesperrt.
- Bank: Konnektorschnittstelle um Saldenabruf, Zustimmungsstatus und Zahlungseinreichung ergänzt; Lesekonnektoren lehnen Zahlungen ab, Zahlungen bleiben hinter G2.
- Bank: Kontoabruf je Konto wiederholt vorübergehende Anbieterfehler bis zu dreimal mit wachsendem Abstand.
- Bank: Uhrzeit des täglichen Bankabrufs je Mandant einstellbar und manueller Gesamtabruf aller Konten (Einstellungen, Bank).
- Bank: Sync-Protokoll zeigt je Lauf die Zahl der Vorschläge und der automatischen Buchungen.
- Bank: Tilgungsbestimmung prüft Einheit und Objekt aus dem Verwendungszweck gegen den offenen Posten.
- Bank: Wochendigest der Stufe L3 mit Bestätigungspflicht und Kopplung an die Bankabstimmung des Vormonats; ohne Bestätigung bucht L3 nicht automatisch.
- Bank: Zahler-IBAN kann nach bestätigter Buchung zur Vier-Augen-Freigabe beim Kontakt vorgeschlagen werden.
- Bank: KI-Kontierung im Buchungsdialog sichtbar mit Modell, Kosten, Begründung und Konfidenz; Mandantenschalter unter Einstellungen, KI.
- KI: Kontierungsprompt v2 mit minimierten Beispielen derselben Gegenpartei hinter dem Schalter für Lernbeispiele; 20 Evaluationsfälle.
- Bank: Synthetischer Testbestand mit 20 Umsätzen einschließlich Ausgangsfällen.
- Bank: Getrennte Bankverbindungen werden standardmäßig ausgeblendet und lassen sich mit 'Getrennte anzeigen' einblenden.
- Doku: Runbook EBICS-Einrichtung mit INI/HIA-Briefen und Bankschlüsselprüfung.
- Buchhaltung: Neue Auswertungen Monatsmatrix, Soll/Ist der Forderungen und Bankkontoabrechnung mit Abgleich zum Kontoauszug, jeweils mit einheitlichen Kopfangaben (Rechtsträger, Zeitraum, Stichtag, Datenstand, Filter, Entwurf).
- Buchhaltung: Journal und Auswertungen lassen sich als Excel (XLSX) laden, jeder Abruf wird mit Prüfsumme als Exportlauf protokolliert.
- Buchhaltung: Die Auswertungsseite zeigt Kontenblatt, Saldenliste und Offene Posten mit Stichtag sowie die neuen Ansichten.
- Buchhaltung: Umsatzsteuer- und Vorsteuerübersicht sowie Einnahmen-und-Ausgaben-Ansicht je Rechtsträger als Entwurf ohne steuerliche Bewertung, mit Prüfpunkten zu E-Rechnungspflicht und Vorsteuerberichtigung.
- Buchhaltung: Kennzeichen EÜR, USt und Prüfung gemischter Nutzung je Konto (Migration 0259), änderbar nur mit Freigaberecht.
- Buchhaltung: Regelversionsregister mit Wirksamkeitsdatum, betroffenen Fallgruppen und erfasster fachkundiger Bestätigung (Migration 0259).
- Buchhaltung: Verfahrensdokumentation wird als Entwurf aus den Betriebsdaten erzeugt und kann geladen werden.
- Buchhaltung: Der Prüfexport enthält die vollständige Vertragshistorie (Tabelle vertraege) sowie Freigaben von Mahnläufen und Zahlungsaufträgen.
- Dokumente: Der Reiter Dokumente im Ticket zeigt nur noch Paperless-Dokumente mit Bezug zum Ticket, Kontakt oder Objekt und keine Dokumente mehr, die nur dieselben Ziffern enthalten.
- Tickets: Neue Auftragsliste mit Filtern und Auftragsdetail per Schnittstelle sowie CRM-Seite Aufträge.
- Tickets: Teams lassen sich lesen, ändern und löschen, die Teamliste der Automatisierungsseite lädt wieder.
- Tickets: Neue Felder Gebäude, Beginn, Wiedervorlage, externe Kommentare und externe Anhänge (Migration 0260).
- Tickets: Kommentare lassen sich archivieren, der Text bleibt als Nachweis gespeichert.
- Portal: Dienstleister können Aufträge annehmen, mit Begründung ablehnen, sehen den Stand ihrer Rechnungseinreichung und das Angebotsdokument; doppelte Rechnungsnummern werden abgewiesen.
- Portal: Schritte des Dienstleisters erzeugen Ereignisse und erscheinen im Ticketverlauf.
- Postfach: HTML-Mails und Newsletter werden ohne CSS, Skripte und Kommentare als Text angezeigt, bereits gespeicherte Mails werden beim Öffnen neu aus dem HTML-Teil gelesen.
- Postfach: Kompaktansicht über jeder Eingangsmail und im Ticket-Mailverlauf mit Zusammenfassung, CRM-Hinweis und Antwortvorschlag, Kurz senden reicht über die bestehende Freigabe ein.
- Postfach: lange Mailtexte sind eingeklappt und über Vollständig anzeigen aufklappbar.
- Postfach: IMAP-Postfächer werden alle zwei Minuten lesend abgerufen und laufen durch dieselbe Verarbeitung wie Gmail.
- KI: classify_email Prompt v3 liefert geprüfte Kontakt- und Objekt-ID, Terminbezug, Rechnungskopie-Absicht mit Rechnungsnummer, Anhangshinweis, Tonfall und Platzhalter.
- Postfach: Tonfall für KI-Antwortentwürfe je Postfach einstellbar, das Standardpostfach gilt für den Mandanten.
- Portal: Chat zur Meldung als Nachrichtenkanal am Ticket mit Verlauf, Benachrichtigung und Antwort aus dem CRM, je Mandant schaltbar.
- Portal: Vorqualifizierung von Chatnachrichten als regelbasierter Vorschlag, KI-Stufe nur hinter AVV-Schalter.
- Portal: Dokumentliste zeigt Status Neu oder Gelesen und Kontext je Dokument.
- Portal: Schadensmeldung erfasst den Standort.
- Portal: Vertreterrolle mit Vollmachtsdokument und Zeitraum, lesender Zugriff auf die Eigentümeransicht, Widerruf beendet sofort.
- Portal: Support-Sicht nur lesend, nur mit befristeter Einwilligung des Nutzers und mit Protokoll.
- Portal: Eigentümerseite Eigentum mit beschlossenen Zahlungen, freigegebenen Meldungen und Verbrauchsinformation selbst genutzter Einheiten.
- Portal: Funktionsschalter und Nutzungsstatistik je Mandant im CRM.
- Portal: Formularbaukasten mit 14 Elementtypen und Zustellung als Ticket oder E-Mail.
- Anmeldung: Passwörter müssen mindestens 12 Zeichen haben und werden offline gegen eine Liste kompromittierter Passwörter geprüft, optional ergänzt durch eine lokale Hashdatei des Betreibers.
- Benutzer: Objektzuordnung je Mitglied speicherbar und im CRM unter Einstellungen, Benutzer pflegbar (Migration 0263), Filterung in den Fachlisten folgt.
- Anmeldung: Passkeys (WebAuthn) vorbereitet mit Tabelle und Verwaltungsendpunkten, Registrierung bis zur Freigabe einer Prüfbibliothek gesperrt.
- Portal: Portalrollen Mieter, Eigentümer, Beirat und Dienstleister als benannte Rollen mit Ableitungsregel hinterlegt.
- Barrierefreiheit: CRM mit automatischer axe-Prüfung zentraler Anmelde- und Profilkomponenten und ESLint-Regeln jsx-a11y.
- Sicherheit: Nachweis zu CSRF-Schutz und feldweiser Verschlüsselung dokumentiert.
- Plattform: Lizenzen lassen sich ändern und beenden, Preislisteneinträge ändern und löschen; neue Seite Lizenzen und Preisliste mit Abrechnungsvorschau und Nutzungsverlauf (M27-02, M27-03).
- Plattform: Stufen, Zusatzmodule und Testphase der Preisstruktur fließen in die Abrechnungsvorschau ein, die Preisliste wird per Migration 0264 in die Struktur übernommen (M27-04).
- Plattform: Nutzungszähler speichert täglich einen Stand, der Verlauf ist je Mandant abrufbar (M27-05).
- Plattform: Der vollständige Mandantenexport läuft als Hintergrundjob und enthält Verträge, Buchungen, Rechnungen, Tickets und Dokumentoriginale (M27-01).
- Betrieb: Alarme für fehlgeschlagene Bankabrufe, Bankverbindungen im Fehlerstatus, abgelehnte Zahlungsaufträge und blockierte Mahnschreiben (M9-01).
- Workspace: Gespeicherte Filter in Objekten, Verträgen, Tickets und Dokumenten, Sammelzuweisung von Tickets über die Massenaktion (M9-03, M9-04).
- Infrastruktur: Eigenes Anfragelimit für /api/v1/auth in Traefik, stündliche WAL-Kopie außer Haus mit Statusprüfung, Staging-Vorlage und Staging-Smoketest (M9-05 bis M9-07).
- Dokumentation: ADR zur Jahrespartitionierung und zum Tracing, Leistungsmessung als übersprungene Tests mit Protokoll (S16-06 bis S16-08).
- Kontakte: Parteien lassen sich über die Schnittstelle ändern (Name, Mitglieder, Rollen, Anteile) und ohne Verweise löschen.
- Kontakte: Notizen sind änderbar, anheftbar und löschbar (Schnittstelle und Kontaktseite).
- Kontakte: Tag-Verwaltung je Mandant mit Liste, Umbenennen, Zusammenführen und Löschen (Schnittstelle).
- Kontakte: Immoware24 Kennung und Lexware Office Kundennummer sind im Kontaktformular bearbeitbar.
- Objekte: Bankkonten und Dienstleisterverhältnisse lassen sich ändern und beenden, Bankkonten tragen die Verknüpfung zum Bankzugang.
- Objekte: Historie der Umsatzsteueroptionen je Einheit, Zählerfoto am Zählerstand und Bildverweise am Objekt (Migration 0265).
- Verträge: Zusatzfelder am Vertrag, Ertragskonto je Zahlungszeile und Dokumente an der Kaution (Migration 0265).
- Verträge: Zahlungszeilen und Zahlungspläne sind korrigierbar, nach gebuchter Sollstellung bleiben Betrag, Zeitraum und Art gesperrt.
- Verträge: Kaution mit Statusmodell offen, aktiv, abgerechnet sowie Änderung von Betrag und Raten vor der ersten Bewegung.
- Verträge: SEPA Übersicht unter Verträge mit Filtern und nächtlicher Ablauf von Mandaten nach Gültigkeitsende.
- Datenschutz: Neues Modul mit Löschprofilen je Datenart, Löschantrag nach Art. 17 mit Sperrprüfung und Vier-Augen-Freigabe (Anonymisierung von Kontakten), Register der Auftragsverarbeiter und generiertem Entwurf des Verarbeitungsverzeichnisses (Rechtsprüfung V13 offen), Migration 0266.
- Dokumente: Änderungen an Titel, Kategorie und Verknüpfung werden in die Paperless- und Drive-Spiegel nachgezogen (update_meta), Paperless erhält die Custom Fields entity_type und entity_id und das Kategorie-Tag.
- Objekte: Der Bereich Rechtsträger auf der Objektseite entfällt, der Rechtsträger steht als eine Zeile im Kopfbereich.
- KI: Kostenübersicht zeigt je Aufgabe die Zahl der Läufe und Token im Monat (GET /ai/usage erweitert).
- KI: Vor dem Anbieteraufruf werden Straße mit Hausnummer und PLZ mit Ort maskiert, Namen bleiben erhalten (Regel AI-MASK-02).
- KI: Beim Ablehnen von Kontakt- und Chat-Vorschlägen kann ein Grund eingetragen werden, der im Protokoll gespeichert wird.
- KI: Buchungsvorschläge nutzen vergleichbare Buchungen aus dem Migrationsjournal als lesende Beispiele (Regel AI-HIST-01).
- Migration: Jahresansicht der Ausgaben des Übernahmejahres mit Vorperiode aus dem Migrationsjournal und Nachperiode aus dem aktiven Journal ohne Eröffnungsbuchung (D11).
- Migration: Abnahmeprotokoll je Objekt mit Prüfumfang, verantwortlichen Personen, nicht migrierbaren Daten, Rückfallplan und Archivkonzept, Unterzeichnung durch eine zweite Person (Migration 0268).
- Kommunikation: Im Kontakt zeigt der Reiter Kommunikation jetzt die Kommunikationshistorie (E-Mails, Zustellungen, Tickets) und erlaubt, Zustellungen je Zustellweg vorzubereiten und den Zugang mit Nachweis zu erfassen.
- Kommunikation: Neue Zustellwege SMS, Einschreiben und Bote mit passenden Nachweisarten; beim Kanal Post kann der Postauftrag im selben Schritt angelegt werden.
- Kommunikation: Serienbrief aus Vorlage mit Platzhaltern je Empfänger (POST /dispatches/serial-merge) und Seite Kontakte, Serienversand mit Gruppenanzeige je Zustellweg.
- Kalender: Persönliches Kalender-Abo mit Token für externe Kalender (Erzeugen, Erneuern, Widerrufen) mit ICS-Abruf ohne Anmeldung.
- Vermietung: Mieterhöhungen mit Begründung Index, Modernisierung oder Staffel werden rechnerisch geprüft (Zusatzangaben und Quelldokument), ohne Aussage zur Zulässigkeit.
- Vermietung: Mietspiegelwerte je Gemeinde mit manueller Pflege, CSV-Import mit Vorschau und Abfrage der passenden Spanne.
- Vermietung: Leerstandsmaßnahmen mit Status, Sollmiete, Kosten, Wiedervorlage, entgangener Miete und Leerstandskosten sowie Anzeige aus dem Leerstand anlegen.
- Vermietung: Exposé als PDF auf dem Briefbogen im Dokumentenbereich und Interessentenabgleich je Anzeige mit Suchprofil und Reihung.
- Datenbank: Migration 0269 für Mieterhöhungsbasen, Interessentenprofil, Mietspiegel, Leerstandsmaßnahmen und Kalender-Abo.
- Webhooks: Ereigniskatalog um die tatsächlich erzeugten Ereignistypen erweitert, Abonnements werden gegen den Katalog geprüft und unterstützen Entitäts-Wildcards.
- Webhooks: Jede Zustellung trägt X-MHVP-Event-Id und einen je Zustellung stabilen Idempotency-Key zur sicheren Deduplizierung.
- Automatisierung: Regeln können dauerhaft im Testmodus laufen und protokollieren dann nur Testläufe ohne Aktion.
- Automatisierung: Standardjobs sind je Mandant abschaltbar und mit Uhrzeit konfigurierbar (Schnittstelle /automation/job-schedules), Regelvorlagen als Beispiele abrufbar.
- Übergabeprotokoll: Mängel lassen sich als Tickets anlegen, der verbindliche Abschluss übernimmt Ein- oder Auszugsdatum in den Vertrag, sofern leer.
- Kern: gemeinsames Teilerfolgsformat für Sammelaktionen und Hilfsfunktionen für signierte Datei-URLs vorbereitet.
- Dokumentation: Betriebsanleitung smart-einzug ergänzt.
- Handbuch: Kapitel Fristen (Deadlines) mit Bedienung, Filteroptionen und eigenen Fristen (Regel WS-01).
- Handbuch: Kapitel Vermietung (Rental) mit Leerstandsliste und Mieterhöhungsformular.
- Handbuch: Kapitel Dienstleisterverträge (Service Contracts) mit Verwaltung und Kündigungsfristen.
- Handbuch: Kapitel Rechnungen (Invoices) mit Erfassung, Prüfprozess, Freigabe und Stornovorgängen.
- Handbuch: Kapitel Importe (Imports) mit Verlaufstabelle, Rückgängigmachung und Fehlerbehandlung.
- Handbuch: Kapitel Barrierefreiheit (Accessibility) mit Tastaturkürzel, Bildschirmlesern, Farbkontrast und Responsive Design.
- Runbook: ebics-setup.md als Platzhalterstruktur mit Verweis auf Entscheidung V2 und Befund M11-01 (Implementierung ausstehend).

## 1.47.0 (30.09.2026) Belegkette B05 Sperre, Gmail Latenz, KI Einstellungen, Lückenliste 30.09.2026

- Buchhaltung, Belegkette B05: neuer Klärungsstatus Beleg angefordert (Migration 0248); Bankbewegung durch eine Person als unbelegt melden (POST /banking/transactions/{id}/clarification mit Begründung und optionaler Zuständigkeit, Ticket wird angelegt); Buchung aus der Bankzeile mit offener Klärung ist gesperrt (Fehlercode MHVP-BANK-0027 Beleg fehlt), Freigabe durch verknüpften Beleg oder begründetes Kennzeichen kein Beleg erforderlich; Liste Buchungen ohne Beleg zeigt das Alter in Tagen, Knopf Beleg anfordern im CRM; Regel docs/rules/B05.md, Handbuch Bank.
- Postfach, Gmail Rückkanal: Abruf alle 60 Sekunden statt 300, Redis Sperre verhindert überlappende Läufe; Beruhigungsfrist Standard 180 Sekunden statt 600 (Migration 0249 setzt Mandanten, die noch auf 600 standen, auf 180; abweichend gesetzte Werte bleiben), Empfehlung im CRM; Latenz von der Archivierung in Gmail bis erledigt im CRM sinkt von bis zu 15 auf rund 4 Minuten.
- KI Einstellungen: Seite lädt schneller, der Einbettungsstatus (Zählabfragen über Dokumente und Wissen) lädt nach dem Seitenaufbau nach, die Wissensliste ist je Abruf auf 200 Einträge begrenzt (limit und offset, maximal 500), der doppelte Abruf beim Öffnen entfällt.
- KI Anbieter: Tests für den OpenAI Adapter über gemockten HTTP Transport (Antwort, 429, 503, 400, Zeitüberschreitung) und für das Ausweichen auf den zweiten Anbieter; die Punkte M7-02 und M7-07 waren bereits umgesetzt und sind in docs/OPEN_QUESTIONS.md nachgetragen.
- Planung: Lückenliste Spezifikation gegen Umsetzung, Stand 30.09.2026 (docs/plans/LUECKENLISTE-2026-09-30.md) mit 263 Befunden aus 36 Prüfbereichen, 224 ohne Betreiberentscheidung umsetzbar, 39 mit Entscheidungsbezug.

## 1.46.0 (29.09.2026) G1 Öffnungspaket, Automatik und Belegkette, Datenübernahme, Offline Erfassung, Schreiben und Objektakte

- Buchhaltung, G1 Öffnung: Neue Seite Einstellungen, Buchhaltung, G1 Öffnung mit Checkliste zur Öffnung der Freigabestufe G1 (Kontenrahmen, abgenommene Anhang D Fälle, manuelle Prüfpunkte, Automatikstufen, Freigabestand), Ergebnis je Prüfpunkt mit Datum und Name, Antrag auf G1 über den bestehenden Vier Augen Pfad; die Seite öffnet die Stufe nie selbst (Migration 0242, Tabelle g1_acceptance). Betreiberunterlagen: Kontenrahmen Prüfung nach Anhang A.1 mit offenen Fragen, Abnahmeprotokoll Anhang D mit Rechenweg und Prüfort je Fall, Verfahrensdokumentation Kapitel 7 Automatik der Buchhaltung.
- Buchhaltung, Automatik: Automatikbuchungen ohne abgeschlossene Nachkontrolle werden aus Mahnlauf, Tilgungsvorschlag und Lastschriftlauf ausgenommen (Regel M12-05, Fehlercode MHVP-BANK-0026); Rücklastschriften zu automatisch gebuchten Zahlungen erzeugen ein Nachkontrolle Item der Art Rückläufer und zählen einen Widerspruch an der Bankregel; Fälligkeiten berücksichtigen bundesweite und nordrhein westfälische Feiertage (Migration 0243).
- Buchhaltung, Belegkette B05: Klärungsstatus je unbelegter Bankbewegung mit verantwortlicher Aufgabe, Liste Buchungen ohne Beleg auf der Bankseite, Meldung offener Klärungen bei der Festschreibung, Tabelle belegkette im Prüfexport; die Automatik liest die Entscheidung (Endpunkte GET und POST /banking/clarifications).
- Lernspeicher: Ein nächtlicher Lauf anonymisiert Entscheidungen und Regelvorschläge nach 24 Monaten statt sie zu löschen, das Entscheidungsergebnis bleibt als Prüfspur (Bestätigung des Betreibers unter M12-09).
- Datenübernahme: Migrationsjournal je Objekt mit Stand, Eröffnungssalden mit Freigabe durch eine zweite Person, Abgleich gegen Immoware24 mit Abweichungsbericht und Umschaltung des führenden Systems je Buchungskreis (Regel M8-05, Migration 0244, Seite Importe, Migration).
- Übergabeprotokoll, Offline Erfassung: Am Handy oder Tablet speichert der Editor Änderungen und Fotos ohne Verbindung verschlüsselt auf dem Gerät und überträgt sie in Erfassungsreihenfolge, mit Konfliktfrage bei zwischenzeitlicher Änderung; Mandantenschalter unter Einstellungen (Standard aus), Gerätezeitstempel und Schlüssel je Gerät (Regel M30-10, ADR 0016 angenommen, Migration 0245).
- Schreiben: Nachforderungsschreiben und Mieterhöhungsschreiben auf dem hinterlegten Briefbogen als PDF mit Ablage als Dokument und Versandnachweis (Weg, Datum, Benutzer, Sendungsnummer); Portalzustellung erst mit Freigabestufe G3.
- WEG, Wirtschaftsplan: Übernahme des beschlossenen Wirtschaftsplans in die Zahlungspläne mit Vorschau, Bestätigung und zweiter Person (Regel W02).
- Objektakte: Export der Objektakte für den nachfolgenden Verwalter als ZIP im Hintergrund (Dokumente je Kategorie, Stammdatenblätter, offene Posten, Übergaben) mit Datenschutzhinweis und Abrufprotokoll (Migration 0246).
- Tests auf Handy und Tablet: Playwright Projekte für Handy, Tablet und Tablet Querformat mit Touch Emulation in CRM und Portal, Prüfungen auf Überlauf, 44 Pixel Ziele, einzeilige Kopfzeile und 16 Pixel Eingabefelder; Übergabepfad und Datenseiten gegen die API; Quelltestwächter gegen nackte Tabellen und feste Breiten; Geräte Checkliste für iPad, iPhone und Android; CI prüft zusätzlich das Projekt Handy.
- Portal: Eingabefelder mit 16 Pixel Schrift am Handy und 44 Pixel Höhe auf Touch Geräten.
- Tickets: Abschnitt Lexware Office in der Abschnittsnavigation; Dateien und Seiten der Anwendung öffnen im selben Tab (PDF, DMS Vorschau, Importbericht, Mietrechnung, Objektakte, Kontakt, Offener Posten, Vertrag), externe Links weiter im neuen Tab.
- Vermietung, FLOWFACT: Übergabe von Vermietungsangeboten an FLOWFACT über den Maklerprovider mit Schemanamen je Angebotsart in der Mandantenkonfiguration (Regel M28-02, Migration 0247).

## 1.45.2 (29.09.2026) Korrektur Playbooks, Nutzungszähler und Freigabe

- Playbooks, Zähler: Das Einfügen einer Playbook Antwort im Ticket zählt jetzt als Nutzung (neuer Endpunkt POST /mail/playbooks/{id}/use); zuvor stieg der Zähler nur beim Antwortentwurf aus der Mail, in der Wissensdatenbank und im Ticket stand daher überall 0x verwendet.
- Playbooks, Freigabe: Gelernte Playbooks entstehen als Entwurf und wirken erst nach der Freigabe. Die Schaltfläche Freigeben steht jetzt auch in der Wissensdatenbank; unter Mail, Playbooks zeigt sie einen Fehler statt stumm zu bleiben, und Löschen meldet Fehler ebenfalls.

## 1.45.1 (29.09.2026) Korrektur Gmail Abruf, Volltextindex

- Dokumente, Volltext: Der extrahierte Text eines Dokuments wird nun auch nach UTF-8 Bytes begrenzt (900.000 Bytes), damit der erzeugte Suchvektor unter der PostgreSQL Grenze von 1.048.575 Bytes bleibt. Zuvor scheiterte der Gmail Abruf an einem großen Anhang mit der Meldung string is too long for tsvector, und die betroffene Mail blieb ohne Ablage.

## 1.45.0 (29.09.2026) Handy und Tablet, Bankeinrichtung und Automatik, Lexware Office im Ticket, Verbrauchsinformation

- CRM auf Handy und Tablet, Hülle: Das CRM lässt sich als App auf dem Startbildschirm ablegen (Manifest, Icons, Eintrag Als App installieren im Benutzermenü, Hinweis für iPadOS); der Service Worker hält nur die Offline Seite und die Icons vor, nie Daten, Seiten oder Dokumente (Betreiberentscheidung M30-08, ADR 0017, Annahme A-084).
- CRM auf Handy und Tablet, Datenseiten: Alle Tabellen laufen in einem Scrollrahmen, Einheiten und Dokumente erscheinen unterhalb der Tabletbreite als Kartenliste, Stammdaten als gestapelte Listen; Kalender mit zweizeiliger Werkzeugleiste, Schaltfläche Heute, umbrechenden Monatszeilen und Dialogen als Sheets; Kontaktseite mit Reitern, Anruf und Mail als 44 Pixel Ziele; Ticketdetail mit Abschnittsleiste, Sammelleiste am unteren Rand, Kameraaufnahme und Dokumentöffnung im selben Tab.
- Übergabeprotokoll am Tablet oder Handy, CRM: Schrittleiste mit Zählern und Statuspunkten, Fußzeile Zurück und Weiter, Lesesicht mit Beteiligten, Zählern, Räumen, Mängeln, Schlüsseln, Änderungsverlauf und Unterschriften, Eingabehinweise je Feld, Speichern in der unteren Leiste, Erneut senden nach Verbindungsfehler, Fotoaufnahme mit Kamera oder Galerie samt Verkleinerung auf dem Gerät, Fotogalerie mit Wischen, Liste mit Filtern und Chips Heute und Diese Woche.
- Übergabeprotokoll, Unterschrift: Gemeinsamer Unterschriftskern in packages/ui mit normalisierten Strichen, Rückgängig und Leeren, genutzt im CRM und im Portal; Unterschriftenblatt je Beteiligtem mit Einwilligungstext.
- Übergabeprotokoll, Änderung nach Unterschrift: Sobald eine gültige Unterschrift vorliegt, sind Inhalt, Fotos und Protokollfelder gesperrt; eine Änderung braucht einen Pflichtgrund, wird mit Zeit und Person protokolliert, setzt die vorherigen Unterschriften als überholt und erscheint im PDF (Regel M30-09, Migration 0239).
- Übergabeprotokoll, Schnittstelle: Schritt Mängel, stabile Hinweiscodes, Vorschaubilder mit 320 Pixel als abgeleitete Ansicht ohne Speicherung (Regel M30-08), Filter nach Übergabedatum, HEIF im Upload (Ablage als JPEG); Offline Erfassung als ADR 0016 (Proposed) mit offenen Datenschutzpunkten beschrieben (M30-07).
- Portal auf Handy und Tablet: Menüeintrag Übergabe für Helfer, Beteiligte, Mieter und Eigentümer mit Zugang, Manifest mit Farben und maskierbarem Icon, sichere Bildschirmränder, Abschnittsreiter mit 44 Pixel Zielen, Fotoauswahl mit Kamera und Galerie samt Verkleinerung und Status je Datei, Fotoansicht, PDF im selben Tab, Bestätigungsblatt für Abschluss und Löschen, Lesekarte für Beteiligte im 14 Tage Fenster, Vorschaubilder über den Portalpfad; ein fehlgeschlagener Fotoupload wird wiederholt, ohne den Eintrag doppelt anzulegen.
- Verbrauchsinformation (Regel H03): Monatliche Verbrauchsinformation je Einheit mit Werten, Datenbasis, fehlenden Angaben, eingefrorenem Schnappschuss und abgelegtem PDF; monatlicher Lauf am ersten Werktag, Mandantenschalter unter Einstellungen, Mandant (Standard aus), Objektabschnitt mit erzeugten Monaten, manueller Lauf und Prüfliste des Betreibers; Portalseite Verbrauch nur für die eigene Einheit, gesperrt bis der Betreiber die Vorlage geprüft hat (Migration 0238).
- Bank, Einrichtung in drei Schritten: Auf /bank führt ein Assistent über FinTS oder Umsatzdatei, Konto sowie Objekt und Art mit abgeleitetem Rechtsträger.
- Objekte, Dienstleister und Handwerker: Kreditoren je Objekt mit Gewerk, Verknüpfen und Lösen, Reiter Dienstleister/Handwerker am Objekt, Abschnitt Objekte als Dienstleister am Kontakt; Kreditor anlegen direkt aus dem Buchungsdialog eines Bankumsatzes (Kontakt mit Rolle Dienstleister, Gegenkonto IBAN wartet auf Vier Augen Freigabe); Rückfüllung aus gebuchten Buchungen und Rechnungen (Regel M11-08, Migration 0240).
- Buchhaltung, Automatik in Stufen (Regel M12-05): Fallklassen mit Eignungskennzahlen je Klasse und Rechtsträger, Stufenanträge mit Freigabe durch eine zweite Person, sofortige Herabstufung und nächtlicher Prüfjob; Bestätigung mit einem Klick auf Stufe L1; Verifizierer je Klasse mit Fingerabdruck, Runner nach jedem Import und Abgleich mit Fallgrenzen, Automatikentscheidungen und Ereignissen; Einzahlungen ohne Vertragsnummer oder Mandatsreferenz bleiben manuell (Migration 0241, ADR 0014 Ergänzung, Annahmen A-085 bis A-088).
- Buchhaltung, Nachkontrolle: Warteschlange der Automatikbuchungen unter Bank, Nachkontrolle mit In Ordnung und Korrigieren; die Korrektur storniert mit Grundcode und bucht neu; eine überfällige Nachkontrolle sperrt die Klasse im Runner; neues Recht accounting:review.
- Buchhaltung, gelernte Bankregeln (Regel M12-06): Jede Entscheidung einer Person wird beobachtet; ab der Mandantenschwelle (wiederkehrende Muster niedriger) entsteht ein Regelvorschlag auf der Seite Bankregeln, der nichts bucht und nichts aktiviert; Widerspruch zieht zurück, Annahme legt eine Regel im Zustand vorgeschlagen an, die den bestehenden Vier Augen Weg geht.
- Einstellungen, Buchhaltung, Automatikstufen: Kennzahlen je Klasse, Anträge und Freigabe; Stufenhinweis in der Sammelbestätigung.
- Tickets, Lexware Office: Karte für Rechnungskopieanfragen mit Status, Treffern, Empfängerprüfung, Anfrage, Korrektur, Empfänger verknüpfen, Annehmen und Ablehnen; Hinweischip am Mailvorschlag, wenn eine Rechnungskopieanfrage erkannt wurde; Formular für Rechnungsentwürfe mit Kontrollsummen und Vorschau.
- Kontakte, Lexware Office: Statusabzeichen und Abschnitt mit Verknüpfung, Übertragung und Konfliktauflösung.
- Tickets, Playbooks: Passende Playbooks werden im Antwortpanel nach Ticketkategorie oder Prozesscode angeboten, der Antworttext lässt sich einfügen, Rückmeldung passt oder passt nicht wird gespeichert.
- Handbuch: Abschnitte Lexware Office im Ticket und am Kontakt, Playbooks im Antwortpanel, Kalender und Kontakte am Handy, Übergabe am Tablet oder Handy, Protokoll später einsehen, Hinweise für den Betrieb vor Ort, Verbrauchsinformation, Einrichtung in drei Schritten, Dienstleister/Handwerker, Automatik in Stufen, Buchung korrigieren, Gelernte Regelvorschläge; Hilfeindex neu erstellt.
- Migrationen: Kette 0237, 0238 Verbrauchsinformation, 0239 Änderung nach Unterschrift, 0240 Kreditoren je Objekt, 0241 Automatikstufen; ADR 0016 Offline Erfassung Übergabe (Proposed), ADR 0017 CRM Hülle (Accepted).

## 1.44.1 (29.09.2026) Gmail-Rückkanal freischalten

- Einstellungen, Postfächer: Schaltfläche Testlauf bestätigen mit Vermerk, danach ist die Stufe erledigen des Gmail-Rückkanals wählbar; bisher war die Bestätigung nur über die Schnittstelle möglich.

## 1.44.0 (29.09.2026) Lückenpakete, Gmail-Abgleich, Buchhaltungsgedächtnis, Lexware Office, Prozessflows, Handy und Tablet

- Postfach, Rückkanal Gmail: Was in Gmail archiviert, mit Label versehen, in den Papierkorb verschoben oder wiederhergestellt wird, wird in der Plattform nachvollzogen; das Sammelpostfach entscheidet über die Erledigung, Erledigt gilt für jede Kopie einer Mail, Tickets werden nach Betreibervorgabe geschlossen; Vorschau je Postfach unter Einstellungen, Postfächer, Standard aus (Migration 0224).
- Kontakte, Bankverbindung: An einem bestehenden Kontakt lassen sich Bankverbindungen hinzufügen, als neue Version ändern und beenden, jeweils mit Vier-Augen-Freigabe; neue Systemrolle Freigabe mit dem Recht contacts:approve; ein Überschreiben per Schnittstelle wird abgewiesen, solange eine Änderung zur Freigabe offen ist (Migration 0225).
- Verträge, Eigentümerwechsel: Schaltfläche Eigentümerwechsel auf Vertrags- und Einheitenseite mit Vorschau; die am Übergang gültigen Sollbeträge, der Zahlungsplan und die Umlagewerte werden auf den neuen Vertrag übernommen und lassen sich in der Vorschau abwählen.
- Stammdaten: Gebäude, Einheiten und Umlageschlüsselwerte werden auf der Objektseite angelegt; je Umlageschlüssel eine Sollsumme mit Vergleich zur Summe der Einheitenwerte (nur Hinweis, Migration 0227).
- Stammdaten: Objekteigentümer, Ansprechpartner, Zähler, Wartungen und Zusatzfelder werden auf der Objektseite gepflegt; Wartungen mit Intervall in Monaten und Erledigt-Zyklus, ohne Vorgabe von Prüfpflichten.
- Verträge, Sollbeträge: Miete, Vorauszahlungen und Hausgeld werden je Vertrag in der Oberfläche als neuer Stand ab Datum erfasst, mit Verlauf über alle Versionen.
- Fristen: Katalog der Fristtypen je Mandant unter Einstellungen (Systemtypen Verwalterwechsel, Kautionsabrechnung, Mieterhöhung ohne vorgegebene Dauer, eigene Typen), eigene Fristen je Objekt, Einheit und Vertrag, Checkliste Verwalterwechsel am Objekt, Hinweis zur Kündigungsfrist beim Beenden eines Mietvertrags, Zugangsdatum einer Mieterhöhung beim Erfassen des Zugangs (Migration 0230).
- Wohnungsübergabe und Objektordner: Übergabeprotokoll mit Verknüpfung zum Vertrag, Zählerstände aus dem Protokoll werden nach Bestätigung in die Zählerstände der Einheit übernommen; Standardkategorien Mieterakte und Eigentümerakte mit Ordnerstruktur der Objektakte; Upload mit Kategorie, Vertrag und Kontakt (Migration 0231).
- Bedienung auf Handy und Tablet: Bausteine für Listen als Karten, Bottom Sheets, Bestätigungen und untere Leisten, Navigationsschublade mit Symbolleiste ab Tablet, einzeilige Kopfzeile, Bedienelemente mit 44 Pixel Zielgröße auf Berührungsgeräten, Tabellenköpfe bleiben sichtbar (ADR 0013).
- Buchhaltungsgedächtnis, Stufe 1: Je Bankumsatz merkt sich die Plattform, welche Vorschläge angezeigt wurden und was die Person daraus gemacht hat (übernommen, geändert, abgelehnt mit Grund, ignoriert mit Grund, nach Storno neu gebucht); Mandantenschalter Lernender Buchhalter, Standard aus, Freigabe mit Grund; nichts wird automatisch gebucht (Migration 0232, ADR 0014).
- Buchhaltungsgedächtnis, Verlauf: Ab der zweiten bestätigten Buchung derselben Gegenpartei erscheint das zuletzt gewählte Konto als Vorschlag Verlauf mit Anzahl und Widersprüchen; die Kontierung einer verknüpften Rechnung erscheint als Vorschlag Rechnung; im Belegeingang werden Kostenkonten je Zeile aus dem Verlauf des Kreditors vorgeschlagen, nie vorausgewählt.
- Buchhaltung: Storno mit Grundcode neben dem Freitext; ein Bankumsatz, dessen Buchung storniert wurde, ist einmal neu buchbar; Ereignisverbrauch der Bankseite als Hintergrundjob.
- Bank, Oberfläche: Arbeitsliste der Umsätze mit Filtern nach Konto, Status, Richtung und Zeitraum, Buchungsdialog mit offenen Posten, Teilbeträgen, Aufteilung, Gegenkonto und Übertragspaaren, Ignorieren mit Grund, Dublettenklärung, Regel lernen aus einer gebuchten Zahlung und Massenbestätigung nur eindeutig geprüfter Vorschläge; jede Buchung braucht eine ausdrückliche Bestätigung.
- Bank, Import und Regeln: Upload von CAMT.053, MT940 und CSV mit Spaltenzuordnung, die je Konto gespeichert wird; Seiten Bankregeln (Vorschlag, Freigabe durch zweite Person, Aktivierung mit Betragsgrenze und Testnachweis, Deaktivierung) und Bankabstimmung je Kontoauszug; der Automatikschalter ist nur lesbar, solange die Betreiberentscheidung offen ist.
- Lexware Office: Anbindung je Gesellschaft unter Einstellungen, Schnittstellen mit AVV, Verbindungstest und Rechnungsarten; einseitiger Abgleich freigegebener Kontaktänderungen, Zuordnung von Kontakten mit Prüfentscheidung, Rechnungskopien mit Empfängerprüfung und Ablage, Rechnungsentwürfe je Rechnungsart und Vorbereitung wiederkehrender Rechnungen bei neuen Verwaltervergütungen; ausgehende Warteschlange mit Wiederholungen und Anfragelimit; keine Buchung, kein Versand ohne zweite Freigabe (Migration 0233, ADR 0015).
- Tickets, Prozessflows: Zwölf feste Prozessarten (Kündigung, Vermietung, Versicherungsschaden, Reparaturanfrage, Beschwerde, Buchhaltung, Übergabe, Mieterhöhung, Gericht, Objektübernahme, Objektabgabe, Kaution) als Vorlagen je Mandant mit Checkliste, verantwortlicher Rolle, Pflichtverknüpfungen, Fristvorschlägen und Dokumentarten; Erkennung aus der Mail nach Schlüsselwörtern, Prozessabzeichen in Liste, Detail und Mailvorschlag, Filter nach Prozessart; die Übernahme setzt nie einen Status und bucht nichts (Migration 0235).
- KI-Wissensbasis: Der Chat und die Mailvorbereitung nutzen dieselbe Auswahl freigegebener Wissenseinträge (begrenzt nach Anzahl und Zeichen, verwendete Einträge am Lauf gespeichert); Rückmeldung hilfreich oder nicht hilfreich zu Antworten, Wissenseinträgen und Antwortmustern; Anzeige von Nutzung und Hinweis Lange nicht geprüft nach 180 Tagen; Antwortmuster bevorzugen die Mailkategorie (Migration 0237).
- KI-Assistent: Der Chat kennt jede Seite und Unterseite des CRM und schlägt je Bereich passende Fragen vor; ohne Suchbegriff liefert er Kalendereinträge, Fristen, Dokumente, Beschlüsse, Versammlungen, Rücklage, Mieterhöhungen, Aufträge, offene Bankumsätze und offene Posten des Bereichs, jeweils im Rahmen der Berechtigung; Vorschläge für Kalendereintrag und Frist werden erst nach Bestätigung als interne Einträge angelegt, nie als Einladung.
- KI-Assistent, Eingabebudget: Die Eingabe des Chats wird auf das Kontextfenster des Anbieters zugeschnitten (gefundene Dokumente, Auszüge, Treffer, Verlauf); Frage und Seitenkontext werden nie gekürzt; bei einer Anbieterabweisung wegen Tokenlimit ein Wiederholungsversuch mit halbem Budget, danach Trefferliste mit Hinweis.
- Handbuch: Anleitungen Stammdaten, Eigentümerwechsel, Mieterwechsel, Mieterhöhung, Verwalterwechsel, Bankverbindung und Objektordner auf die neuen Bedienwege umgestellt, Tabelle Lücken in der Software bereinigt; neue Seiten Bank, Lexware Office, Fristtypen und Prozessflows; Regeln M20-08, M5-03, C2-01, WS-01, M30-07, M12-04, UI-BANK-01, INT-LEXO-01, M19-11 und AI-LOOKUP-01 registriert.
- Technik: Migrationen 0224 bis 0237 zu einer Kette zusammengeführt, ORM-Modelle an die Migrationen angeglichen; ADR 0014 (lernender Buchhalter) und ADR 0015 (Lexware Office) nummeriert; OpenAPI, Client und Hilfeindex neu erzeugt.

## 1.43.0 (29.09.2026) KI-Assistent mit Datenzugriff

- KI-Assistent beantwortet Fragen zu Kontakten, Objekten, Einheiten, Verträgen und Tickets aus den eigenen Daten, jeweils nur im Rahmen der eigenen Berechtigungen und des Mandanten; Antworten enthalten Links zu den gefundenen Datensätzen, findet die Plattform nichts, sagt der Assistent das ausdrücklich.
- Fragen wie "Wo finde ich ..." verweisen auf die passende Seite und den Handbuchabschnitt.
- Vorschläge im Chat passend zur Seite und zum geöffneten Datensatz (Kontakt, Objekt, WEG, Einheit, Vertrag, Ticket, Übergabeprotokoll, Postfach); der Chat führt ein Gespräch mit Rückfragen und bezieht Seite, Datensatz und bisherigen Verlauf ein.
- Ohne freigegebenen KI-Anbieter oder bei erreichtem Budget zeigt der Chat die Treffer der Plattformsuche mit Hinweis.
- Änderungen über den Chat (Kontaktdaten, Notiz, Ticket) entstehen nur als Vorschlag mit Bestätigung; Bankverbindungen nie über den Chat. Telefonnummern, E-Mail-Adressen und Bankverbindungen verlassen die Plattform nur maskiert (Migration 0223).
- Korrekturen aus der Gegenprüfung des Assistenten: Datensatzinhalte können keine Aktionen oder Links auslösen, jede Aktion wird gegen die Berechtigung des Zielendpunkts geprüft.
- Neues Handbuchkapitel KI-Assistent im Chat; Lückenanalyse und Fahrplan lernende Buchhaltung sowie Plan Bedienung auf Handy und Tablet unter docs/plans.
- Bank, FinTS: Institutsliste der Deutschen Kreditwirtschaft (Stand 20.08.2026) übernommen; der Fehler beim Abruf der Bankparameter erklärt die möglichen Ursachen (Adresse, noch nicht freigeschaltete Produktregistrierung).

## 1.42.1 (28.09.2026) Release-Skript mit Compose v5

- Release-Skript: die Prüfung der Images vor dem Einspielen berücksichtigt nur noch die eigenen Images für API, CRM und Portal; Compose v5 nennt zusätzlich die Images der abhängigen Dienste (Postgres, Redis, Objektspeicher, Virenscanner), was bisher zum Abbruch vor jeder Änderung führte. Fehlt eines der drei eigenen Images, bricht das Skript weiterhin vor jeder Änderung ab.

## 1.42.0 (28.09.2026) Rückmeldungen aus dem Team

- Handbuch: Handlungsanweisungen für Verwalterwechsel, Stammdaten, Eigentümerwechsel, Mieterwechsel und Wohnungsübergabe, Mieterhöhung, Bankverbindung mit Vier-Augen-Freigabe und Objektordner sowie ein Vorschlag zur Aufgabenverteilung für Mail und Tickets ergänzt; Lücken in der Software im Handbuch gesammelt.
- Erfassungsstandards für Objekte, Kontakte und Fristen an einer Stelle festgelegt (Handbuch Erfassungsstandards, Regeln ES-01 bis ES-11).
- Objektformulare: Hinweise zu Straße, Hausnummer, PLZ, Ort und Objektname nach dem Muster Straße Hausnummer, PLZ Ort, mit Namensvorschlag zum Übernehmen; eine deutsche Postleitzahl muss aus genau fünf Ziffern bestehen, geprüft im Formular und über die API.
- Kontaktformulare: Hinweise bei vertauschten Namen, Komma im Namensfeld und Firmenbestandteilen in Personennamen.
- Ticketfälligkeit: ein Datum in der Vergangenheit wird erst nach ausdrücklicher Bestätigung gespeichert, dazu ein Hinweis auf die fehlende verantwortliche Person.
- Neue Seite Einstellungen, Datenqualität mit Links zur Korrektur; bestehende Daten werden nicht automatisch geändert.
- Vertragsliste zeigt je Vertrag Objekt, Einheit sowie Mieter oder Eigentümer, jeweils verlinkt, und hat eine Freitextsuche nach Name, Objekt, Anschrift, Einheit und Vertragsnummer.
- Postfach: Threadansicht, Mailverlauf im Ticket, Nachrichtenzahl und Kontakthistorie zeigen Kopien derselben Mail nur noch einmal; eigene gesendete Mails mit Kopie an ein eigenes Postfach erscheinen nicht mehr als neue Eingangsmail; eine mehrfach abgerufene Gmail-Mail ohne Message-ID und Datum wird nur einmal gespeichert. Kopien bleiben als Nachweis erhalten.

## 1.41.0 (28.09.2026) Anbindung Schadenbearbeiter

- Neue Anbindung an den Schadenbearbeiter (Schadenstool) unter Einstellungen, Schnittstellen, Schadenbearbeiter: Basisadresse, Integrationstoken, HMAC- und Webhook-Geheimnis verschlüsselt, Aktivierung erst nach eingetragenem AVV, Verbindungstest; standardmäßig ausgeschaltet.
- Ticketdetail: Ticket an den Schadenbearbeiter übergeben, ausgewählte Kommentare und Dokumente senden, Status des Schadenbearbeiters anzeigen; interne Notizen werden nie gesendet.
- Statuswechsel verknüpfter Tickets werden an den Schadenbearbeiter übermittelt, Kommentare und Anhänge des Schadenbearbeiters kommen per Webhook und Abgleich alle 15 Minuten ins Ticket.
- Vorhandene Schadentickets übernehmen: Liste mit Vorschlag für Objekt und Ticket, Übernahme nur nach Bestätigung.
- Ausgehende Warteschlange mit Wiederholungen, Beachtung des Anfragelimits und Hinweis Token ungültig; Webhook mit Signaturprüfung, Zeitfenster fünf Minuten und Schutz gegen doppelte Ereignisse (Migration 0222).

## 1.40.4 (28.09.2026) Lernregeln respektieren Entscheidungen der Mitglieder

- Angenommene Lernregeln für Thema und Bearbeiter füllen nur noch leere Felder und überschreiben keine Entscheidung eines Mitglieds mehr, auch wenn der Regellauf erst später stattfindet; es entsteht dann keine Benachrichtigung. Von Hand angelegte Regeln der Verwaltung setzen Ticketfelder weiterhin wie bisher.
- Die Annahme eines Regelvorschlags deaktiviert ältere Lernregeln derselben Mustergruppe, protokolliert dies mit Mitglied und Zeitpunkt und nennt die abgelösten Regeln in der Antwort.
- Eine von einer Lernregel gesetzte Zuordnung lässt sich direkt mit Ja bestätigen oder auf einen anderen Vorschlag korrigieren.

## 1.40.3 (28.09.2026) Korrekturen aus der Prüfung vom 28.09.2026

- Folgevorgänge, die in ihren abgeschlossenen Vorgänger zurückgeführt wurden, blockieren keine weiteren Mails mehr; jede weitere Mail des Vorgangs wird eingelesen, statt den Mailabruf mit einem Fehler anzuhalten. Beim Zusammenführen eines Folgetickets in seinen Vorgänger wird die Folgeverknüpfung gelöst und im Verlauf festgehalten.
- Vor dem Anlegen eines Folgetickets wird ein vorhandenes Folgeticket berücksichtigt: es erhält die Mail, wird innerhalb seiner Frist wieder geöffnet oder führt entlang der Kette weiter.
- Antwort aus dem Ticket: eine abweichende Reply-To-Adresse wird nur dann Empfänger, wenn sie am Ticket beteiligt ist; sonst bleibt der geprüfte Absender Empfänger, und die Adresse wird nur zur ausdrücklichen Auswahl angeboten.
- Antworten an alle setzt nie eine eigene Postfachadresse als Empfänger; bei eigener Reply-To-Adresse gilt der Absender, bei eigenem Absender der erste fremde ursprüngliche Empfänger.
- Umbuchungen (Regel B08, D04): Wurde eine Hälfte vor dem Import des zweiten Auszugs gegen Geldtransit gebucht, ist die zweite Hälfte gegen Geldtransit buchbar und gleicht es aus; eine Buchung gegen das Partnerbankkonto wird mit MHVP-BANK-0020 abgelehnt, die Meldung nennt das Konto der Partnerbuchung und den Weg über das Storno.
- Migration 0221 korrigiert den Namen der Prüfbedingung für die Wiedereröffnungsfrist.

## 1.40.2 (28.09.2026) Übersetzungen korrigiert

- Übersetzungen korrigiert: Auswahllisten im Vertragsformular (Zahlweise, Zeitanteilsregel, Betragsbasis), Felder und Zustellstatus der Automationen, SLA-Reiter, Signaturvorlage, Lernphase und Kostenübersicht der KI zeigen jetzt deutsche Bezeichnungen statt technischer Schlüssel.
- Der Hilfetext zur Zahlweise im Vertragsformular beschreibt jetzt Vorschüssig und Nachschüssig statt der Zahlungsintervalle.
- Umlaute in den Immoware24-Ansichten korrigiert (zum Beispiel Zurück, Läufe, übernehmen).
- Fehlende oder falsche Übersetzungen lassen die Tests jetzt fehlschlagen und werden zusätzlich statisch geprüft (scripts/check_i18n_usage.py im Lint).

## 1.40.1 (28.09.2026) Gespeicherte Darstellung, stabile Tests

- Darstellung im CRM: Die Wahl Tag, Abend oder Automatisch sowie die aufgeklappten Menügruppen werden jetzt tatsächlich im Benutzerkonto gespeichert und gelten auf allen Geräten; bisher galt nur die Kopie im jeweiligen Browser.
- Kontaktformular und Kontaktansicht: die Beschriftung Kontotyp wird wieder korrekt angezeigt statt eines internen Schlüssels.
- Tests stabilisiert: Umgebungsvariablen beeinflussen die Einstellungsprüfung nicht mehr, Testmandanten und Testnutzer sind je Modul eindeutig, der Immoware Sammellauf wird im Test auf den eigenen Mandanten begrenzt, Kontaktformular und Objektkündigung laufen auch unter Last stabil.
- Neue Playwright-Tests für Darstellung, Antworten an alle mit zweitem Faktor, Regelvorschläge, Folgevorgänge, Kontaktverweise im Reiter Einheiten und den Hell und Dunkelmodus im Kundenportal.

## 1.40.0 (28.09.2026) Kundenportal Hell und Dunkel, Lernregeln mit Zuordnungskette

- Kundenportal mit Tag und Abendmodus: Standard folgt der Einstellung des Betriebssystems, Umschalter Hell, Dunkel und Automatisch in der Kopfzeile, Wahl nur im Browser gespeichert, kein Aufblitzen beim Laden, fest codierte Farben durch Design Tokens ersetzt und Kontrast in beiden Modi nach WCAG AA geprüft.
- Anmeldeseite des Portals: die beiden Links haben jetzt ausreichenden Kontrast im Tagmodus.
- Der Umschalter Tag, Abend und Automatisch im CRM ist mit den Pfeiltasten bedienbar.
- Setzt eine angenommene Lernregel den Kontakt einer Mail oder eines Tickets, ergänzt das System Objekt und Einheit über die sichere Zuordnungskette (genau ein aktiver Mietvertrag oder genau eine aktive Eigentümerschaft), nur in leere und nicht entschiedene Felder, mit Grund und Protokolleintrag; bei mehreren Verträgen bleibt die Rückfrage bestehen.
- Die Nachweissuche des Lern-Workflows je Absenderadresse nutzt einen neuen Index (Migration 0220, normalisierte Absenderspalte); die Migration schreibt die Mailtabelle einmal neu und läuft bei gestoppter API.

## 1.39.0 (28.09.2026) Umbuchungen, Portalformulare, Kalenderfehler und Release-Skript

- Umbuchungen zwischen eigenen Bankkonten werden nur einmal gebucht: Nach der Buchung einer Seite gilt die Partnerseite als erledigt, ein weiterer Buchungsversuch wird mit MHVP-BANK-0019 abgelehnt; nach einem Storno ist das Paar genau einmal neu buchbar (Abnahmefall D04, Regel B08). Ein Umbuchungspaar kann nur noch gegen das Bankkonto der Partnerseite gebucht werden.
- Kalender: Fehler des Google Kalenders führen nicht mehr zu "Interner Fehler"; eine abgelaufene oder widerrufene Google-Verbindung meldet MHVP-COMM-0004 mit dem Hinweis, das Postfach unter Einstellungen, Postfächer neu zu verbinden, eine vorübergehende Störung meldet MHVP-COMM-0005 mit der Bitte um einen erneuten Versuch; interne Termine und Fristen werden weiter angezeigt.
- Anmeldeseite: Logo, Favicon und die übrigen Dateien aus dem öffentlichen Verzeichnis werden ohne Sitzung ausgeliefert und nicht mehr auf die Anmeldung umgeleitet; Seiten und Schnittstellen bleiben geschützt.
- Portalformulare: Die Einreichungen lassen sich im CRM nach dem Status des zugehörigen Tickets filtern (Alle, Offen oder ein einzelner Status).
- Dokumente: Hochgeladene HEIC- und HEIF-Dateien werden nur noch mit gültiger Dateisignatur angenommen, umbenannte Programme oder Videos werden abgelehnt.
- Der Einladungsbrief zum Kundenportal ist durch einen API-Test abgesichert (Codewechsel, 90 Tage Gültigkeit, QR-Code nur mit öffentlicher Portaladresse, Berechtigung und Mandantentrennung).
- Neues Skript infra/scripts/release.sh für den Release auf dem Produktionsserver: Pull, geprüfte Datenbanksicherung, Build der drei Images, Umstellung von .env.prod mit Sicherungskopie, Migration, Start mit Gesundheitsprüfung, Logprüfung und Rollback-Hinweise ohne automatisches Zurücksetzen; Probelauf mit --dry-run; Runbook docs/runbooks/release.md.
- Lückenliste vom 26.09.2026 geprüft: Teil A ist vollständig umgesetzt, offene Restpunkte warten auf Betreiberentscheidungen.

## 1.38.0 (28.09.2026) Lern-Workflow, Folgevorgänge und durchgängiges Design

- Abnahmefälle Anhang D: Rückverfolgbarkeit aller 58 Fälle in docs/acceptance/D-cases.md mit zugeordnetem Test und Stand der Automatisierung; neue Tests für D04, D05, D07 und D24 über den Bankimport mit geschlossenen Freigabestufen; keine Abnahme erteilt, die Abnahme durch den Betreiber steht für alle Fälle aus.
- Postfach: "Antworten" und "Vorschlag übernehmen" zeigen bei Nutzern mit eingeschaltetem zweiten Faktor (TOTP) keinen "Interner Fehler" mehr; die Signatur liest nur noch den Anzeigenamen des Nutzers. Dasselbe gilt für Einreichen, Ticketantwort und Signaturvorschau.
- Leere Einträge in gespeicherten Empfängerlisten führen nicht mehr zum Abbruch beim Antworten, und Kopien im Sammelpostfach antworten an die Reply-To-Adresse.
- Lern-Workflow: Nach fünf gleichen manuellen Zuordnungen für denselben Absender ohne Widerspruch schlägt die Plattform eine Regel vor; aktiv wird sie erst nach ausdrücklicher Annahme.
- Neue Seite Regelvorschläge unter Einstellungen mit Annehmen, Ablehnen mit Grund und einstellbarer Schwelle sowie Hinweis im Mailbereich.
- Angenommene Vorschläge werden normale Automatisierungsregeln, die leere Zuordnungen, Ticketthema oder Bearbeiter setzen; Zahlungsempfänger, IBAN, Beschlüsse, Gebühren und Steuer werden nie gelernt.
- Neue E-Mails zu abgeschlossenen Tickets öffnen das Ticket nur noch innerhalb von 30 Kalendertagen nach dem Abschluss wieder (je Mandant einstellbar unter Einstellungen, Mandant); danach entsteht ein Folgevorgang mit Verweis auf das alte Ticket und übernommenem Objekt, Einheit und Kontakt.
- Automatische Antworten wie Abwesenheitsnotizen öffnen keine Tickets mehr wieder und legen keinen Folgevorgang an; im Ticketdetail ist der Vorgänger oder Folgevorgang verlinkt.
- Oberfläche: Tag und Abendmodus durchgängig im neuen Design; Karten, Tabellen, Eingabefelder, Schaltflächen, Statusanzeigen und Navigation nutzen einheitliche Farbrollen statt fester Farbwerte. Seitenhintergrund und Karten waren seit 1.37.0 vertauscht und sind korrigiert.
- Barrierefreiheit: Kontraste in beiden Modi nach WCAG AA geprüft, deutlicherer Fokusrahmen, sichtbare Feldrahmen und lesbare Ampelfarben auch im Abendmodus.

## 1.37.0 (27.09.2026) Darstellung Tag und Abend

- Objekt, Reiter Einheiten: Eigentümer und Mieter sind jetzt anklickbar und führen direkt zum Kontakt; bei mehreren Personen ist jede einzeln verlinkt, ohne hinterlegte Person führt der Name zum Vertrag.
- Darstellung (Betreiberentscheidung 27.09.2026): Tagmodus "Klar und ruhig" (helles, ruhiges Layout, Orange nur für Handlungsbedarf und aktive Navigation) und Abendmodus "Dunkel und präzise" (dunkle Oberfläche, feine Linien statt Schatten, Gold als Akzent); Umschalter "Tag", "Abend" und "Automatisch" im Benutzermenü und unter Einstellungen, Profil; automatisch wechselt von 19 bis 7 Uhr in den Abendmodus und wird jede Minute neu geprüft.
- Die Wahl wird je Benutzerkonto gespeichert (PATCH /api/v1/auth/me/preferences, Feld theme: day, evening oder auto, serverseitig geprüft) und zusätzlich lokal im Browser gehalten, damit die Seite ohne Aufblitzen der falschen Darstellung startet; ein unerwarteter oder veralteter gespeicherter Wert wird verworfen statt die Seite abstürzen zu lassen (Lehre aus 1.35.1).
- Farb- und Gestaltungswerte beider Modi zentral in den Darstellungsbausteinen hinterlegt (weiche Karten mit 10 bis 14 px Radius und sehr weichem Schatten am Tag, 6 px Radius ohne Schatten am Abend); die Bearbeitungsmarkierung im Postfach nutzt jetzt eine eigene Farbe je Modus statt der Mittel-Priorität-Farbe.
- Kontrast in beiden Modi nach WCAG AA geprüft, Fokusringe in beiden Modi sichtbar.
- Mailansicht und Ticket-Mailverlauf zeigen Von, An und Kopie je auf einer eigenen Zeile und kennzeichnen das eigene Postfach dezent.
- Antworten aus Mail und Ticket geht jetzt standardmäßig an alle: an den Absender oder die Reply-To-Adresse, alle übrigen ursprünglichen Empfänger in Kopie, ohne eigene Postfachadressen und ohne Dubletten (Migration 0217).
- Zuordnungsprüfung: ist der Kontakt einer Mail oder eines Tickets sicher (automatisch oder durch ein Ja bestätigt) und hat er genau einen aktiven Mietvertrag oder genau eine aktive Eigentümerschaft einer Einheit, werden Einheit und Objekt jetzt automatisch mit übernommen, begründet mit "eindeutiger Vertrag" beziehungsweise "eindeutiges Eigentum", nur in ein noch leeres Feld; mehrere Verträge oder Einheiten bleiben wie gewohnt eine Rückfrage mit diesen Kandidaten, Hinweise im Text ordnen sie dort nur um; ein unsicherer Kontakt leitet weiterhin nichts ab (Betreiberauftrag 27.09.2026, Regel A80-01, Annahme A-068).
- Mail- und Ticketansicht zeigen jetzt die Rolle des zugeordneten Kontakts (Mieter, Eigentümer, Beirat, Dienstleister, auch mehrere zugleich) mit Verweis auf Kontakt, Einheit und Objekt.

## 1.36.0 (27.09.2026) Postfach: Antworten mit Anhängen, Bearbeitungsmarkierung, Duplikate, Signatur je Nutzer, Zuordnungsrückfrage

- Mail: "Antworten" öffnet den Antwortentwurf direkt unter der Nachricht (ein Entwurf je Eingangsmail, Vorbereiten und Antworten nutzen denselben); Empfänger, Kopie, Betreff und Text frei bearbeitbar; Anhänge am Entwurf aus dem DMS verknüpfen, vom lokalen Rechner hochladen oder entfernen, Versand mit allen Anhängen; verständliche Fehlermeldungen zu Postfach, Empfängern und Freigabe (Betreibermeldung 27.09.2026, Ursache: der neue Entwurf wurde still im Reiter Entwürfe abgelegt, Migration 0214 No-op).
- E-Mail-Signatur je angemeldetem Nutzer: Position (Dropdown mit Standardkatalog Geschäftsführer, Prokurist, Assistenz, Objektbetreuung, Immobilienkaufmann, Buchhaltung, Leitung Buchhaltung, Asset Management, sowie manuell anlegen) und Durchwahl im Profil und in der Benutzerverwaltung, Signaturvorlage je Mandant mit Platzhaltern unter Einstellungen, Vorschau Text und HTML nach HVM-CI bzw. als Wortmarke für das Einzelunternehmen; die Signatur wird in den gespeicherten Entwurfstext eingefügt, bei Antworten, übernommenem Vorschlag, Playbook und Ticketantwort sofort, sonst spätestens beim Einreichen, sodass die Freigabe genau den versendeten Text zeigt; der Versand hängt nichts mehr an (Migration 0215).
- Postfach: neueste Nachrichten oben in allen Ansichten; Mails in Bearbeitung (Antwort eingereicht, interner Kommentar oder Bearbeiter) werden gelb hinterlegt und tragen den Namen des Bearbeiters unter Datum und Uhrzeit; dieselbe Mail an Sammel- und persönliches Postfach erscheint nur einmal beim persönlichen Postfach, die Kopie wird verknüpft und teilt das Ticket (Kennzeichen Sammelpostfach je Postfach, Wartungsendpunkt für vorhandene Mails, Migration 0213).
- Zuordnungsprüfung mit Rückfrage: jede eingehende Mail und jedes Ticket wird auf Kontakt, Verwaltungsobjekt und Einheit geprüft; sichere Treffer werden begründet übernommen, unsichere als Frage "Handelt es sich um ...?" mit Ja und Nein (und Suche bei Nein) in Mail- und Ticketansicht angezeigt, Entscheidungen werden protokolliert (Migration 0216, Annahme A-068 zu Schwellenwerten).
- Energieausweis am Gebäude: nach einer Inline-Änderung des Gebäudes speicherte das Formular mit veralteter Version und scheiterte (412); die Version wird jetzt nachgeführt.
- Bank: ohne FinTS-Produktregistrierung zeigt die Bankseite einen klaren Hinweis statt des Verbindungsknopfs (neuer Endpunkt GET /banking/fints/config), Einstellungen, Bank verlinkt auf die Einrichtung; Menüknöpfe eindeutig benannt ("Menü einklappen", "Alle Bereiche einklappen"); Rechnungsprüfung und Abrechnungswerkbank sperren Knöpfe bis zum Abschluss der Aktualisierung.
- Einstellungen: Suchfeld über der Kartenübersicht ergänzt, findet Seiten sowie einzelne Abschnitte bis zur dritten Ebene (z. B. Buchhaltung, Steuern, Reverse Charge), unscharf gegenüber Umlauten und Groß-/Kleinschreibung, rechtegefiltert; zusätzlich in der Befehlspalette (Strg+K) verfügbar.
- Duplikate: Migration 0213 kennzeichnet auch bestehende Postfächer wie info@ als Sammelpostfach (die Nachbefüllung blieb wegen der Zeilensicherheit wirkungslos); gleichzeitige Abrufe zweier eigener Postfächer legen dieselbe Mail nur einmal als führende Mail an; eine Mail mit bekannter Message-ID, aber anderem Absender, Betreff, Text oder Anhang wird als eigene Mail gespeichert; die Wartung "Duplikate verknüpfen" lässt Kopien mit einem anderen Ticket unverändert und zählt sie als Ticketkonflikt.
- Rechnungsweiterleitung: eine Rechnung mit gleicher Message-ID wird weder automatisch noch über "Weiterleiten" ein zweites Mal an die Buchhaltung gegeben (Status "duplicate" bzw. Meldung mit Betreff, Datum und Postfach der bereits weitergeleiteten Mail), auch bei gleichzeitigem Klick und Abruf; ohne verbundenes Gmail-Postfach wird die Weiterleitung als "nicht gesendet" mit Grund markiert statt als gesendet und sperrt eine spätere Weiterleitung nicht.
- Signatur: keine doppelte Signatur mehr bei bearbeitetem Signaturblock, gelöschter Trennzeile oder seit dem Anlegen geänderter Position, Durchwahl, Vorlage oder Postfach; die Platzhalterzeilen [Name] und [Firma] der Antwortvorlagen entfallen; die E-Mail-Zeile zeigt die Adresse des sendenden Postfachs; die Mobilnummer der SMS-Bereitschaft erscheint nicht mehr; eine geänderte Durchwahl wird gespeichert.
- Signaturvorlage: unbekannte Platzhalter werden beim Speichern mit Namen abgelehnt und blockieren in bestehenden Vorlagen weder Entwurf noch Versand; Vorschau und Vorlage weisen darauf hin, dass Mails derzeit als Klartext mit Textsignatur versendet werden, HTML-Vorlage und Logo dienen nur der Vorschau.
- Antworten öffnet nur noch den eigenen offenen Entwurf zu genau dieser Mail im freigegebenen Postfach, nie den Entwurf von Kollegen oder zu älteren Mails des Verlaufs; Vorschlag übernehmen und Vorbereiten zeigen den neuen Text sofort, bei ungespeicherten Änderungen fragt der Editor, welcher Text gelten soll.
- Zuordnung: Kontakte werden nur automatisch zugeordnet, wenn die Absenderadresse genau einem aktiven Kontakt gehört, sonst Rückfrage (auch bei geteilten Adressen und gelöschten Dubletten); eine Einheit wird nur zusammen mit einem Vertrag des Kontakts automatisch zugeordnet; "Nr." allein gilt nicht mehr als Einheitenangabe; Anreden, Anredewörter, Nachnamen eigener Mitarbeiter und zitierte frühere Mails zählen nicht als Absendername.
- Zuordnung: das Öffnen einer Mail oder eines Tickets ändert nichts mehr; eine Entscheidung sendet den gesehenen Feldwert und bei Ja den bestätigten Kandidaten, wurde das Feld inzwischen anders gesetzt oder hat ein anderes Mitglied bereits mit Ja entschieden, antwortet die API mit Konflikt (409, neuer Fehlercode MHVP-COMM-0003) und speichert nichts, die Rückfragekarte lädt dann neu; jede automatische Zuordnung wird protokolliert und erscheint im Ticketverlauf; die Liste offener Rückfragen zeigt nur Mails aus sichtbaren Postfächern (Migration 0216 um die Spalte basis_id ergänzt).
- Rechnungsprüfung und Betriebskostenabrechnung: nach dem Erfassen eines Prüfschritts, einer Kostenposition oder dem Berechnen blieb die Seite gelegentlich mit gesperrten Knöpfen auf dem alten Stand; die Ansicht wird jetzt zuverlässig aktualisiert und die Knöpfe werden freigegeben, sobald der neue Stand angezeigt wird.
- CI und Tests: Formatierung der Migration 0195, eindeutige Schemanamen (AssignmentDecideIn), Dublettenerkennung ohne Message-ID nur noch für Mails ohne Kopfzeile, damit getrennte Anrufnotizen nicht zusammengeführt werden; neue Tests zu Migration 0213, parallelen Abrufen, Deadlock im Abruf, Signaturversand und Zuordnungskonflikten.

## 1.35.2 (27.09.2026) Tickets, Kalender und gesperrte Funktionen im CRM wieder erreichbar

- Tickets: Beim Setzen von Erledigt, Geschlossen oder Abgelehnt, auch für mehrere Tickets gleichzeitig, erschien "Erledigungsarten konnten nicht geladen werden", weil der CRM-Proxy den Abruf der Erledigungsarten nicht weiterleitete (Betreibermeldung 27.09.2026); die Einstellungsseite der Erledigungsarten war ebenso betroffen.
- CRM-Proxy: 73 weitere Aufrufe freigeschaltet, die vorhandene Oberflächen nutzen, bisher aber mit "Nicht gefunden" scheiterten, u. a. Beiratsbeteiligung an Tickets, SLA-Freigabe, Übermittlungen im Messwesen, Vermögensbericht und Belegprüfung der WEG, Absage und Selbstauskunft für Interessenten, Kontenrahmen-Freigabe, DATEV-Selbstprüfung mit Download und Testdatei, Steuereinstellungen, Vertreterbeziehungen bei Kontakten sowie Preisliste, G5-Nachweise, Onboarding und Mandantenexport für Plattformadministratoren; die Berechtigungen prüft weiterhin die API.
- Postfach: Vertretungen im Vier-Augen-Verfahren riefen einen falschen Pfad auf und ließen sich weder anlegen noch löschen; korrigiert.
- Kalender: Scheitert der Google-Abruf eines Postfachs, etwa bei abgelaufener oder widerrufener Freigabe, zeigt der Kalender die übrigen Termine und Fristen weiter an und nennt den Grund mit Link zu den Postfach-Einstellungen, statt mit einem Serverfehler abzubrechen; Anlegen, Ändern und Löschen von Google-Terminen melden den Grund ebenfalls.
- Sicherheit: Falsche Passwörter oder TOTP-Codes bei der Re-Authentifizierung vor einer Mailfreigabe zählen jetzt wie beim Login zur Kontosperre, ein gesperrtes Konto kann sich nicht erneut bestätigen (Regel M20-04).
- Steuerberaterzugang: Die Liste der DATEV-Exportläufe zeigt einer auf einzelne Rechtsträger beschränkten Mitgliedschaft nur noch deren Läufe (Regel M18-05).
- Steuern: Eine Freistellungsbescheinigung zählt nur noch mit einem Dokument des eigenen Mandanten; eine fremde oder unbekannte Dokumentnummer wird abgelehnt und hebt die Einbehaltssperre nicht mehr auf (Regel M14-04).
- Beiratsprüfung: Prüfaufträge und Prüfpositionen übernehmen nur noch die Abrechnung, gebuchte Buchungen im Prüfzeitraum und Belege der eigenen Gemeinschaft, der Betrag einer Position folgt dem gebuchten Betrag; eine auf einzelne Rechtsträger beschränkte Mitgliedschaft sieht nur deren Prüfaufträge.
- Betrieb: FinTS-Registrierungsnummer, Google-OAuth- und Gmail-Push-Einstellungen sowie der Objektakte-Importpfad aus .env.prod werden jetzt an die Container weitergegeben; bisher blieben diese Einträge wirkungslos, deshalb erschien der FinTS-Hinweis trotz gesetzter Nummer.
- Qualität: Neuer Prüftest gleicht alle Proxy-Aufrufe der Oberfläche mit der Freigabeliste ab, damit fehlende Freigaben nicht mehr unbemerkt ausgeliefert werden.

## 1.35.1 (27.09.2026) Startfehler nach dem Update behoben

- Startfehler behoben (Betreibermeldung 27.09.2026): Nach dem Update auf 1.35.0 zeigte jeder Browser, der das CRM vorher genutzt hatte, nur "Application error", weil der Menüzustand aus 1.34.x in einem anderen Format im Browser gespeichert war; das Hauptmenü liest den alten Wert jetzt fehlertolerant und startet dann eingeklappt.

## 1.35.0 (27.09.2026) Bankanbindung FinTS, Heizkosten, Steuern, Aufbewahrung, WEG-Einladung, Vollimport Verträge und 40 weitere Module

- Betrieb: Restore-Übung (infra/scripts/restore-drill.sh) mit Protokoll unter docs/reviews, SSH-Härtungsvorschlag (infra/hardening), GoBD-Verfahrensdokumentation als Entwurf und Parallelbetriebsplan Immoware24 (Migration 0179 No-op).
- Dashboard: Ticketstatistik und Diagramme wieder auf der Startseite (nur Administratoren), Spalte Meine Tickets auf vier Einträge begrenzt mit Fallback auf die dringendsten offenen Tickets des Mandanten.
- Vier Anhang-B-Dossiers (FLOW, Übergabeprotokoll, smart-einzug, objektakte) und sechs neue Playwright-Kernpfade gegen das Backend (Dashboard, Ticketfilter, Objektreaktivierung, Kontaktrollenfilter, Postfachfilter, Auswertungssperre).
- Bank: CSV-Umsatzimport mit automatischer Formaterkennung (Sparkasse, Volksbank/Raiffeisen, DKB, ING, N26, comdirect) und generischem Spalten-Mapping je Konto, Vorschau vor dem Import, gleicher Dublettenschutz wie CAMT/MT940 (M11-02, Migration 0168).
- WEG: Umlaufbeschluss mit einfacher Mehrheit bei verknüpftem Zulassungsbeschluss (Schalter je Mandant, Standard aus), Auszählung nach Köpfen, Miteigentumsanteilen oder Einheiten, Fristende, Textform-Nachweis je Stimme, Ergebnisfeststellung mit Protokoll; Rechtsgrundlage zu prüfen (M25-02, Migration 0166).
- Mandantenübersicht für Plattformadministratoren (M2-05): lesende Kennzahlen und Listen über alle eigenen Mandanten, je Mandant getrennt gelesen (RLS unverändert), Mandantenkennzeichen, Umschalter und Link Im Mandanten öffnen, Aufruf je Mandant protokolliert (Migration 0167).
- Tickets: Seitenwechsel zeigte weiterhin die erste Seite, weil die Liste ihren Zustand nicht mit der neu geladenen Seite abgeglichen hat (Betreibermeldung 27.09.2026), behoben.
- lexoffice-Anbindung (13.3): Einstellungen und Verbindungstest, protokollierter Export von Belegen und Kontakten hinter Gate G1 und Mandantenschalter, Import von Belegen als Belegentwurf mit Dublettenschutz (Migration 0164); smart-einzug ohne öffentliche API, als Entscheidung M13-smart-einzug-01 vermerkt.
- Regel-Engine: Webhooks werden nach Plan (1, 5, 15, 60 Minuten, höchstens 5 Versuche) wiederholt, danach Status aufgegeben mit Benachrichtigung an den Regelbesitzer, Idempotenzschlüssel je Zustellung, erneutes Senden aus dem Zustellprotokoll; neue Bedingungen Ticketalter und Fristbezug, Aktion Aufgabe anlegen (M9-08, Migration 0169).
- Heizkostenabrechnung als Entwurf (M17-02): Verteilung nach Verbrauch und Fläche (50 bis 70 Prozent), Warmwassertrennung, CO2-Stufenmodell und Gradtagstabelle als Regeltabellen mit Quellenstatus, Nutzerwechsel nach Gradtagen, Verbrauchsinformation je Einheit, Import aus dem Messdienst, Übernahme als Position in die Betriebskostenabrechnung; Ausgabe weiterhin hinter G3 (Migration 0162).
- Betreiber-Runbook für die Einrichtung des Gmail-Push über Google Cloud Pub/Sub (docs/integrations/gmail-push.md).
- KI-Wissensbasis: Freigabeworkflow (Entwurf, zur Prüfung, freigegeben, zurückgezogen) mit Vier-Augen-Prinzip, Versionierung, Gültigkeitszeitraum und Quellenbeleg; nur freigegebene, gültige Einträge fließen in KI-Läufe, der Nachweis nennt die verwendeten Einträge (M34-01, Migration 0178).
- WEG: Vermögensbericht je Gemeinschaft zum Stichtag (Rücklage Soll und Ist, Bankbestände, Forderungen, Verbindlichkeiten, Darlehen mit Restschuld, manuelle Positionen, Abstimmung gegen die Buchhaltung mit sichtbarer Differenz, PDF-Entwurf) und Darlehensausweis in der Jahresabrechnung (Zins und Tilgung je Jahr, Verteilung nach Schlüssel ohne Ergebniswirkung), alles hinter G4 (M24-02, M24-03, Migration 0171).
- Hauptmenü: Menügruppen starten eingeklappt, die Gruppe der aktuellen Seite klappt automatisch auf, der Zustand wird je Nutzer geräteübergreifend gespeichert, Knopf Alle einklappen (Migration 0182).
- Portal: Barrierefreiheit geprüft und ergänzt (Skip-Link, aria-live bei Benachrichtigungen, Erklärung zur Barrierefreiheit unter /barrierefreiheit als Entwurf, axe-core-Tests der Kernseiten; Migration 0188 No-op).
- Bank: Bankanbindung per FinTS/HBCI direkt (PIN/TAN) zusätzlich zu finAPI: Institut über BLZ, BIC, IBAN oder Namen erkennen (2721 FinTS-fähige Institute), Anmeldename und PIN, TAN-Freigabe (pushTAN, chipTAN, photoTAN), Konten laden und Objekt oder Rechtsträger zuordnen, Salden und Umsätze per Klick; erneute Freigabe nach spätestens 90 Tagen, Zugangsdaten verschlüsselt, PIN nie sichtbar, nur lesend (G2 geschlossen); Registrierungsnummer der Deutschen Kreditwirtschaft als MHVP_FINTS_PRODUCT_ID nötig (Migration 0161).
- Postfach: echte Seitensteuerung (Seite 2, 3 usw. laden andere Nachrichten, Filterwechsel setzt auf Seite 1), API GET /mail/messages mit page, page_size und X-Total-Count (Betreibermeldung 27.09.2026).
- Sicherheit: Sicherheitsheader (CSP, Permissions-Policy, Referrer-Policy) in API und beiden Web-Apps, interne Sicherheitsprüfung mit Abhängigkeits- und Secrets-Scan dokumentiert (docs/reviews/2026-09-27-sicherheitspruefung.md, Migration 0192 No-op).
- objektakte-Übernahme: Vorschaubild-Übernahme mit Wiederaufnahme, Umschlüsselungswerkzeug (Dry-Run, Protokoll ohne Klartext), Adapter für das lokale Klassifikationsmodell hinter Mandantenschalter (nur Vorschlag), Abgleichbericht objektakte gegen CRM, Ratenbegrenzung und Backoff für Google Drive, Runbook-Entwurf Archivierung (M35-01 bis 07, Migration 0176).
- Mahnwesen: Mahnschreiben nennen das Standardkonto des Rechtsträgers der Forderung (Kontoinhaber und vollständige IBAN, Kennzeichen je Bankkonto, ohne Standardkonto Warnung und kein Schreiben); Fälligkeit und Verzugsbeginn getrennt mit Verzugsmodus je Mandant und erfassbaren Zugangsdaten; Verbrauchereigenschaft am Kontakt (M16-03, M16-13, zu prüfen durch Rechtsanwalt, Migration 0172).
- Portal: Magic-Link-Anmeldung (E-Mail, 15 Minuten, einmal nutzbar, optionaler Bestätigungscode) und Einladungsbrief mit QR-Code (90 Tage), Passwortanmeldung bleibt (M21-01, Migration 0165).
- Betriebskostenabrechnung: Systemkatalog der Betriebskostenarten nach BetrKV mit Kontenzuordnung und Prüfhinweisen (M17-01), Vorschussregel mit Sicherheitsaufschlag, Bestätigung und Textbaustein (M17-03), Eigentümerabrechnung Miete und SEV als PDF-Entwurf mit Auszahlungsbetrag (M17-05); alles Entwurf hinter G3 (Migration 0170).
- Playwright: Specs contacts.backend und inline-edit an die UI 1.34.x angepasst (Befehlspalette, exakter Treffer auf den Bearbeiten-Umschalter).
- Kautionsabrechnung als PDF-Entwurf mit Zinsverlauf je Jahr, Einbehalten und maskierter Bankverbindung (Migration 0184); Postfach-Reiter per URL wählbar; Anker Ticket anlegen oben auf der Ticketseite.
- Mail: Vier-Augen-Prinzip beim Versand mit Re-Authentifizierung (Passwort oder TOTP, 5 Minuten), Mandantenmodus (alle Mails, nur extern, aus), Vertretung bei Abwesenheit und Superadmin-Bypass nach ADR 0011 (M20-04, Migration 0173).
- Uploads: Dateinamen werden beim Speichern bereinigt (Pfade, Steuerzeichen, Unicode NFC, Länge, Doppelendungen), Downloads mit Content-Disposition nach RFC 6266; gitleaks in CI und make lint (M27-02-02, M27-02-03, Migration 0196 No-op).
- Vollimport Immoware24 mit Stichtag: Vorprüfung aller Exporttypen (Zeichensatz, Spalten, Zeilenzahl, Dubletten, Pflichtfelder, Prüfsumme), Trockenlauf mit Vorschau, idempotente Übernahme, Abgleichbericht Soll gegen Ist je Entität als JSON und PDF, Eröffnungssalden-Vorschlag als Entwurf hinter G1; Seite /importe/vollimport; synthetischer Bestand 67 Objekte und 869 Einheiten im Test mit Differenzen 0 (M8-01, M8-02, V9, Migration 0191).
- Playwright-Kernpfade für Hauptmenü, Postfach- und Ticketseiten, Bankanbindung, Mandantenübersicht, WEG-Umlaufbeschluss, Abrechnungs- und Kautionsanzeigen sowie Einstellungen (Migration 0200 No-op).
- Brief- und Postversand mit Statusrückmeldung (M23-01): anbieterneutrale Postdienst-Schnittstelle, Postausgang im CRM mit manueller Erfassung von Druck, Versand und Zugang, LetterXpress-Adapter mit verschlüsselten Zugangsdaten (Standard aus, Modus Test), Statusabruf als Hintergrundjob, Mahnschreiben über den Postdienst mit Zugangsnachweis am Mahnfall (Migration 0163); Anbieterwahl bleibt Betreiberentscheidung M23-08.
- CRM-Restpunkte: Verbraucherkennzeichen im Kontakt inline bearbeitbar, Standardkonto des Rechtsträgers an den Objekt-Bankkonten setzbar, Zugang des Mahnschreibens an offenen Posten erfassbar, Schalter Umlaufbeschluss einfache Mehrheit in den Mandanteneinstellungen (Migration 0198 No-op).
- Bankabgleich: Kontierung in zwei Stufen, Stufe 1 deterministisch (Bankregel, Mandat, Vertrags- oder Rechnungsnummer, IBAN, Betrag) immer aktiv mit Quelle, Konfidenz und Begründung je Vorschlag, Stufe 2 KI nur mit Mandantenschalter und freigegebenem Anbieter, nie automatische Buchung; Testbestand mit 200 synthetischen Umsätzen und Trefferquote je Fallklasse in make ai-eval (M12-01, M12-02, M7-05, Migration 0194 No-op).
- Messdienstleister: Dateiadapter nach bved 3.10 (ARGE HeiWaKo) für Techem, Brunata Minol und BRUNATA-METRONA mit Prüfvorschau der Austauschdateien (A, L/M, D, E898), keine Speicherung bis zur Bestätigung an echten Dateien (M40-02, Migration 0193 No-op).
- Einstellungen: Mandantenmodus für die Mail-Freigabe und Sollstellungsregeln (Zeitanteil, USt-Option) bedienbar, Handbuch um die Neuerungen der Welle ergänzt (Migration 0202 No-op).
- DATEV: formale Selbstprüfung je Buchungsstapel mit Prüfbericht und Testdatei mit 20 fiktiven Buchungen für den Importtest beim Steuerberater; Kontenrahmen je Mandant mit Freigabeworkflow (Entwurf, zur Prüfung, freigegeben), Versionsverlauf und CSV/PDF-Export; Freigabestufe G1 nur mit freigegebenem Kontenrahmen (M18-01, V8, M10-01, Migration 0190).
- Sollstellung: zeitanteilige Berechnung je Vertragsregel (Kalendertage, 30/360, voller Monat), nicht monatliche Zahlweisen mit Fälligkeit und Umsatzsteuer bei gewerblicher Option als Entwurf hinter Mandantenschalter und G1, Rechenweg am Lauf, Vertragsformular um Zeitanteilsregel, Zahlweise und Betragsbasis ergänzt (M13-01 bis M13-03, Migration 0177).
- Zahlläufe: pain.001 in Version 03 oder 09 je Bankkonto konfigurierbar und gegen die ISO-20022-XSDs validiert (bisherige Datei verletzte das Schema, behoben); Sammler mit Anzahl, Kontrollsumme und Prüfsumme; protokollierter Download und manuelle Einreichungsbestätigung hinter G2; Einreichungsschnittstelle mit FinTS- und EBICS-Gerüst (nicht aktiv); Runbook Zahllauf-Test und EBICS-Dokumentation (M15-01, M15-03, V2, Migration 0197).
- Tests: Regressionstest Lesen nach Schreiben bei Objekt-PATCH/GET unter 20 parallelen Anfragen; Ursache des CI-Befunds im API-Code ausgeschlossen (Migration 0201 No-op).
- DATEV-Buchungsstapel bildet Konto/Gegenkonto-Paare je Buchung (Zweizeiler direkt, Splitbuchungen über die Summenseite), nicht abbildbare Splitbuchungen werden mit Beleg-ID gemeldet statt still ausgelassen (M18-01, Entwurf, Migration 0209 No-op).
- Plattform Marktreife (M27): Preisstruktur mit Stufen, Zusatzmodulen und Testphase ohne vorbelegte Beträge und Angebot als PDF-Entwurf, Nachweisliste Freigabe G5 mit Dokumentverknüpfung (G5 nur bei vollständigen Nachweisen durch den Superadmin), Onboarding-Assistent für Drittmandanten mit Rechtsträgern, Administrator, CI und Willkommens-E-Mail als Entwurf, Mandanten-Export als ZIP im Vier-Augen-Prinzip (Migration 0199).
- Mahnwesen: Mahnlauf-Details verlinken bei fehlendem Standardkonto direkt auf die Bankkonten des betroffenen Objekts, sonst auf die Objektnummer (M16-15, Migration 0206 No-op).
- Tickets: SLA-Regeln je Kategorie mit Freigabe (nur freigegebene Werte steuern Uhren und Eskalation, bestehende Regeln stehen nach der Migration auf Entwurf und müssen einmal freigegeben werden) und Beiratsbeteiligung bei WEG-Objekten mit Vorlage, Frist, Abstimmung im Eigentümerportal und Protokoll am Ticket, kein Geldbezug (M19-01, M19-02, Migration 0203).
- Portal: digitales SEPA-Lastschriftmandat als Vorschlag mit Mandatstext, IBAN-Prüfung, Bestätigung mit Zeitstempel, IP und PDF-Nachweis, Freigabe in der Kontaktakte (kein aktives Einzugsmandat, G2); Adressänderung mit Gültigkeitsdatum und Nachweis als Vorschlag mit Übernahme in den Kontakt; Freigabeflag je Dokument (intern, Eigentümer, Mieter, Dienstleister, Beirat) (M3-02, M21-02, M21-03, Migration 0174).
- Mail-Vertretungen über eigene Endpunkte und CRM-Formular pflegbar; Mandanten-Standard für die Zahlweise, den ein neuer Vertrag ohne eigene Angabe übernimmt (M20-04a, M13-01a, Migration 0208 No-op).
- Rechnungseingang Steuern (M14-02/03/04): Steuersatz und Vorsteuer getrennt erfasst, Vorsteuerabzug nur als Vorschlag bei optierten Objekten nach Umsatzschlüssel, Kennzeichen Reverse Charge und Bauleistung mit Freistellungsbescheinigung und Einbehaltsvorschlag (15 Prozent Entwurfswert, keine automatische Kürzung), Paragraf 35a Lohn- und Materialanteil je Position mit Ausweis je Mietvertrag als PDF-Entwurf, Freigabegrenzen je Rolle mit zweiter Freigabe durch dritte Person; Einstellungen unter Buchhaltung, Steuern, alle Schalter Standard aus (Migration 0185).
- WEG-Versammlung (M25-03, V13): Einladungsfrist je Mandant in Wochen mit spätestem Versanddatum, Kalendereintrag "Einladung spätestens", Warnung und Pflichtgrund bei Unterschreitung mit Protokollvermerk; virtuelle Versammlung nur mit Schalter je Mandant (Standard aus) und zulassendem Beschluss mit Gültigkeitsende; Einwahldaten verschlüsselt und nur für Eigentümer der Gemeinschaft im Portal; Teilnahmenachweis mit Kanal Präsenz, online, Vollmacht (Migration 0187).
- Aufbewahrungsmatrix (M6-04, V17): Zuordnung Dokumentkategorie zu Aufbewahrungsprofil mit automatischer Fristberechnung nach Startregel, Löschungssperre je Vorgang, monatlicher Löschvorschlagslauf mit Vier-Augen-Freigabe, getrennter Ausführung, Löschprotokoll und Spiegellöschung; CRM-Seiten Einstellungen Aufbewahrung und Dokumente Löschvorschläge (Migration 0175).
- Makler-Bereich (M28-01, M26-02): BrokerProvider-Adapterinterface für FLOWFACT, Propstack und onOffice (mangels belegter Dokumentation vorerst gesperrt, 501 MHVP-BRKR-0002), OpenImmo-Datei-Import mit Vorschau, Freigabe und Dublettenschutz, Interessentenverwaltung mit Besichtigungsterminen, Absage-Textbausteinen und Selbstauskunft-Link (Migration 0195).
- Mietrechnung und Dauermietrechnung mit Umsatzsteuerausweis für Gewerbemietverträge mit Option (M13-04a): PDF-Entwurf aus den Sollstellungsposten auf dem Briefbogen des Mandanten, Nummernkreis je Rechtsträger und Jahr, Ablage am Vertrag und Kontakt, Storno nur durch Gutschrift, Sperre ohne Steuernummer oder USt-IdNr., Wasserzeichen solange G1 geschlossen (Migration 0210, CRM Vertragsseite).
- SEPA-Lastschrift (M15-01): pain.008-Version je Bankkonto (.02 oder .08), Download-Protokoll mit Prüfsumme und Einreichungsbestätigung analog zur Überweisungsdatei, konfigurierbare Vorabinformationsfrist (Entwurfswert 14 Tage, Migration 0211 No-op).
- KI (M34): Prompt-Kontext für Antworten, Zusammenfassungen, Klassifikation und Entwürfe wird vor dem Versand an den Anbieter maskiert (IBAN, E-Mail, Telefon), Ablehnung eines Vorschlags mit optionalem Grund als Lernbeispiel (Migration 0212); offene Punkte M34-04 bis M34-06 dokumentiert.
- Kleinbefunde behoben: objektakte-Kontaktimport unterscheidet Eigentümer- und Mieter-Quell-IDs (kein Verschmelzungsrisiko mehr, Bestandsdaten per Migration 0205 präfigiert), Wissenseinträge können mit Begründung zurückgewiesen werden, Automatisierungsregeln haben einen optionalen Regelbesitzer für Fehlerbenachrichtigungen.
- Messdienstleister und Bankabgleich (M40-02, M12-01): HeiWaKo-Austauschdateien lassen sich in den Messdienstleister-Einstellungen prüfen (Vorschau, keine Speicherung), Kontierungsvorschläge erkennen Kautionsforderungen über die Vertragskaution (Annahme A-066), die Bankabgleich-Seite verlinkt Vorschläge zum offenen Posten und zum Vertrag (Migration 0207 No-op).
- Vollimport Immoware24 (M8-01, M8-02) um die Exporttypen Mietverträge und Eigentümerverträge erweitert: Vorprüfung, Trockenlauf und idempotente Übernahme über Vertragsnummer oder Objekt, Einheit und Beginn, Zuordnung der Partei über Kontakt-ID, Miete und Hausgeld als Vertragsbeträge ohne Buchung (Verträge warten auf Freigabe), Abgleich je Objekt mit Anzahl und Sollsummen, Eröffnungssalden den Verträgen zugeordnet, Importseite und Handbuch nachgezogen (Migration 0204).

## 1.34.3 (27.09.2026) Gmail-Abruf NUL-Bytes, Immoware-Abholung ohne offene Transaktion, Ticketfilter eingeklappt

- Gmail-Abruf (Betreibermeldung 27.09.2026, mailbox.last_error "PostgreSQL text fields cannot contain NUL (0x00) bytes"): eine Nachricht mit einem 0x00-Byte in Betreff, Text, Anhangname oder MIME-Typ blieb dauerhaft unimportiert und der Fehler stand am Postfach; Betreff, Text, HTML-Text, Kopfzeilen, Adressen, Anhangnamen und -typen sowie die JSONB-Felder Klassifikation und KI-Vorschlag werden jetzt über die neue zentrale Hilfsfunktion mhvp.core.text.strip_nul/clean_json bereinigt (ebenso der aus dem Rohtext gewonnene Volltext des .eml-Dokuments); der Postfachabruf lief schon vorher fehlertolerant je Nachricht weiter.
- Tickets: Filter sind standardmäßig eingeklappt, sichtbar bleibt nur die Suchleiste; "Weitere Filter" (mit Anzahl aktiver Filter) klappt alle Filter aus (Betreiberwunsch 27.09.2026).
- Immoware24: Abholung (WebDAV, CardDAV, CalDAV) hält während der HTTP-Aufrufe keine Datenbanktransaktion mehr offen, Laufzeile wird sofort gespeichert, Ergebnisse in Batches zu 50 übernommen, Fehler setzen den Lauf auf fehlgeschlagen; Doppelläufe je Mandant und Art sind gesperrt (409 MHVP-IMW-0005), verwaiste Läufe werden nach 2 Stunden geschlossen (Produktionsbefund 27.09.2026, blockierte Migration 0156).

## 1.34.2 (27.09.2026) Betrieb: Beszel-Variablen optional

- Betrieb: Beszel-Agent-Variablen (BESZEL_AGENT_KEY, BESZEL_AGENT_TOKEN) sind optional, ein leerer Wert blockiert den Stack nicht mehr (Deploy 1.34.1 scheiterte daran).

## 1.34.1 (27.09.2026) Auswertung Tickets nur für Administratoren, Ladefehler behoben

- Auswertung Tickets (Betreibermeldung 27.09.2026): Seite zeigte "Die Auswertung ist derzeit nicht verfügbar.", weil der Pfad workspace/ticket-analytics in der BFF-Allowlist fehlte; behoben. Menüpunkt, Startseitenlink, Befehlspalette, Seite und API nur noch für Mandantenadministratoren und Plattformadministratoren; Fehlerhinweise der Auswertung zeigen Titel, Detail, Fehlercode und HTTP-Status; Mails gelöschter Postfächer zählen in der Postfachart Sonstige.

## 1.34.0 (27.09.2026) Betreiberentscheidungen vom 27.09.2026: Gmail-Archivierung repariert, Objektdeaktivierung, Kalender, Messdienstleister Abgleich, Design, Statusseite, Virenscan

- Tickets und Objekte: Serverfehler auf /tickets behoben (Helfer asAttention lag in einem Client-Modul und wurde auf dem Server aufgerufen), API-Ausfälle erscheinen auf der Ticketliste als Hinweis statt als Absturz, Übersetzungskonflikt in der Objektliste bereinigt, neue Prüfung gegen Aufrufe von Client-Exporten aus Server-Komponenten in make lint (Betreibermeldung 27.09.2026).
- Kontakte: Rollenfilter (Eigentümer, Mieter, Verwalter usw.) lieferte einen internen Fehler und keine Kontakte, Abfrage korrigiert (Betreibermeldung 27.09.2026).
- Erledigt schreibt wieder nach Gmail zurück (Betreibermeldung 27.09.2026): Mail erledigt (einzeln, Sammelaktion), Ticket erledigt, geschlossen oder abgelehnt (Ticketdetail, Ticketliste, Sammelstatus, Lösungsarten, automatischer Abschluss per Mail) und Zusammenführen archivieren alle verknüpften Gmail-Nachrichten (Labels INBOX und UNREAD entfernt, auch später zugeordnete Mails und Mails desselben Threads); Ursache im Worker behoben (Schlüssel für die Postfach-Token wurde in den Ticket- und Sammeljobs nicht gesetzt); Stand je Mail sichtbar (archive_status, Fehler, Zeitpunkt, Migration 0158) mit Knopf Archivierung jetzt nachholen; fehlende Berechtigung gmail.modify wird im Postfach und unter Einstellungen, Postfächer mit Knopf Erneut mit Google verbinden angezeigt, die Consent-URL erzwingt die Zustimmung, nach der Neuverbindung werden offene Archivierungen automatisch nachgeholt; Nachholjob alle 15 Minuten für die letzten 30 Tage, Endpunkt POST /mail/messages/{id}/archive, Diagnosebefehle in docs/integrations/gmail.md
- Virenscan vor der Dokumentablage (Betreiberentscheidung 27.09.2026): jede Datei aus CRM, Portalen, Postfach, Messdienstleistern und Importen wird vor dem Speichern per ClamAV (INSTREAM über TCP) geprüft; ein Fund weist die Datei mit MHVP-DOC-0008 ab und wird mit Signaturname im Ereignisprotokoll festgehalten, ohne dass der Inhalt gespeichert wird; Modi off, warn, enforce (Produktion nur enforce), bei nicht erreichbarem Scanner im Modus enforce Abweisung mit MHVP-DOC-0009; Dienst clamav im Compose-Stack, Bereitschaftsprüfung clamav, Runbook docs/runbooks/virenscan.md
- Befehlspalette (Strg+K, Cmd+K, Schaltfläche in der Kopfzeile) ersetzt die globale Suche: Datensätze, Aktionen und Navigation in einem Eingabefeld, gefiltert nach Berechtigungen, mit zuletzt geöffneten Datensätzen je Benutzer; neuer Statuschip mit Symbol, Klartext und Erklärung in Ticketliste, Postfach, Mahn- und Lastschriftläufen, Freigabestufen und Zählerzuordnungen.
- Startseite als persönlicher Arbeitsplatz (Designvorschlag 2): Spalten Heute, Meine Tickets und Freigaben, Kennzahlen des Mandanten als kompakte Leiste; Benachrichtigungen springen direkt ins Ticket oder in den Kalender.
- Anmeldung: Ziel nach der Anmeldung bleibt erhalten (auch über Zwei-Faktor-Schritt und Mandantenwahl).
- KI: HNSW-Index für Einbettungen, Einbettungsstand im CRM sichtbar, Aufbewahrung der Lernbeispiele 24 Monate mit Mandantenschalter (Migration 0156).
- Betrieb: WAL-Archivierung und Basissicherung nach Hetzner S3 mit age-Verschlüsselung, Playwright-Kernpfade gegen das Backend erweitert.
- Stammdaten: Objektart als Katalog-Auswahl (aktive Einträge, inaktiver Bestandswert bleibt sichtbar); Zusatzfelder werden beim Speichern geprüft (Gültigkeit je Verwaltungsart, Pflicht, Standardwert bei Anlage, Min/Max, Auswahl, Eindeutigkeit je Mandant) mit Feldfehlern; Vertragsliste filtert per URL nach Objekt und Einheit, Ticketliste nach Vertrag.
- Zustellregel für Bevollmächtigte gilt jetzt auch für Mahnschreiben, Betriebskostenabrechnungsschreiben, Einzelbriefe und Einzelzustellungen (Vorgabe beide Empfänger, Zeile "für <Vollmachtgeber>" beim Bevollmächtigten); Mahnlauf-Vorschau warnt, wenn eine Mahnung nur den Bevollmächtigten erreicht (M23-07, mit Rechtsvorbehalt).
- Kalender: Versammlungstermine verlinken auf die Versammlung im WEG-Bereich, Erinnerungscodes erzeugen je Code und Termin genau eine Benachrichtigung mit Sprung zur Quelle, manuelle Termine können sich wöchentlich, monatlich oder jährlich bis zu einem Enddatum wiederholen (Anzeige in Kalender und Fristenliste ohne Speicherung der Einzeltermine), Tickets erhalten eine optionale Fälligkeit im Formular, im Detail und in der Liste (Migration 0159).
- Messdienstleister: Ordnungsbegriffsabgleich als eigener Ablauf (Vorschau intern/extern, bewusste Übermittlung, Bearbeitungsstatus beim Anbieter, Ergebnisabruf als Verifikationsbasis der Zuordnung; ista sendSetup, Migration 0158); Audit-Änderungsprotokoll für Vertragsversionen und Gebäude.
- Startseite leitet direkt weiter (angemeldet zum Dashboard, sonst zur Anmeldung), Loginseite optisch überarbeitet mit Claim und Hilfetext, Dashboard begrüßt persönlich mit Vornamen und tageszeitabhängigem, täglich wechselndem Text.
- Ruhiges Typografie- und Farbsystem (Designvorschlag 4): Schrift Inter über next/font, feste Schriftskala, 8-Punkt-Abstandsraster, Karten mit Haarlinien statt Schatten, Farbe nur als Bedeutung mit kalibriertem Dunkelmodus, einheitlicher Fokusring, Tabellenziffern; gemeinsame Tokens in packages/ui, Dokumentation mit Kontrasttabelle in docs/design/tokens.md (neutrale Werte bis zur Freigabe der Unternehmensfarben M1-08).
- Postfach: Reiter und Filterleiste (Status, Erledigte, Postfach, Suche, Aktualisieren) sauber in zwei Zeilen angeordnet, Filterfelder mit fester Breite.
- CRM lädt die Schrift Inter über next/font im Grundlayout.
- Objekte: Verwaltung beenden mit Kündigendem, Kündigungsdatum, Verwaltungsende, Nachfolgern und Kündigungsschreiben; deaktivierte Objekte verschwinden aus der Objektliste, der Superadmin kann sie einblenden und wieder aktivieren (Regel M4-05, Migration 0159).
- Überwachung: Uptime Kuma mit Embedded MariaDB, neuer Dienst Beszel (Hub und Agent) zeigt Auslastung von Server und Containern (CPU, RAM, Platte, Netzwerk), Statusseite und Runbook verknüpft.
## 1.33.1 (27.09.2026) Bildpipeline für alle Uploads, Entscheidungen zu den Übergabeprotokollen

- Dokumente: Jeder Upload über POST /documents läuft durch die Bildpipeline der Übergabeprotokolle (Metadaten wie EXIF und GPS entfernt, Ausrichtung angewendet, höchstens 2.000 Pixel Kantenlänge); bisher galt sie nur für Übergabe- und Portal-Uploads. Nicht dekodierbare Bilder werden unverändert gespeichert
- Übergabeprotokolle: offene Fragen M30-02 bis M30-05 entschieden (Rechtsprüfung der Unterschriften angestoßen, keine Übernahme der U-Protokoll-Altdaten, Altanwendung bis 31.12.2026 lesend, zweiter Faktor freiwillig nach M2-01)
## 1.33.0 (27.09.2026) Eigentümer und Mieter an die Objektübernahme übergeben

- DMS und Objektübernahme: Knopf "Liste übergeben" auf der DMS-Seite eines Objekts überträgt die Einheiten mit den Namen der laufenden Eigentums- und Mietverträge als Importvorschlag an objektakte (Format Immoware24-Einheitenliste, keine Kontaktdaten, keine Beträge). Übernommen wird erst nach Prüfung im Importassistenten von objektakte; danach tragen die Eigentümer- und Mieterakten dort die Namen und Uploads aus dem CRM landen in der richtigen Akte. Neuer Endpunkt POST /integrations/objektakte/objects/{nummer}/persons-export.

## 1.32.0 (27.09.2026) Upload im CRM mit Ablage über objektakte in Drive und Paperless

- Dokumente: Ein im CRM hochgeladenes oder gescanntes Dokument, das genau einem Objekt zugeordnet ist (direkt, über eine Einheit oder über ein Ticket), geht an objektakte und wird dort verarbeitet und abgelegt: Drive-Struktur des Objekts mit Eigentümer- und Mieterakten und Paperless. Das CRM spiegelt solche Dokumente nicht mehr selbst nach Paperless oder Drive, damit jedes System das Dokument genau einmal hält; Original und Index bleiben im CRM. Schalter OBJEKTAKTE_UPLOAD_ENABLED (Vorgabe aus), in objektakte zusätzlich Token mit documents:write und Schalter sync.crm_uploads_enabled.
- Dokumente: Job mhvp.objektakte.upload (jede Minute) mit den Zuständen pending, submitted, done und failed, Abfrage des Ablagestands alle 5 Minuten, Dublette in objektakte wird mit der Ablage des Originals verknüpft, 503 verschiebt ohne Fehlerzählung, "Spiegelung erneut anstoßen" setzt einen fehlgeschlagenen Upload zurück (Migration 0159).
- DMS und Objektübernahme: Webhook document.filed mit crm_document_id verknüpft das vorhandene CRM-Dokument statt ein neues anzulegen; Drive-Datei und Paperless-ID stehen im Vermerk objektakte des Dokuments. Neuer Endpunkt GET /integrations/objektakte/documents/{id}/filing, Status meldet upload_enabled.
- DMS: neue Seite Dokumentsuche (/dms/suche) mit Suche im Paperless-Archiv nach Volltext, Objekt und Gesellschaft, Vorschaubildern, Vorschau und Download über den Proxy der API sowie Upload mit Objekt und Einheit; die Dokumentansicht zeigt den Ablagestand über objektakte mit Sprung nach Drive und in die Paperless-Vorschau. Die Oberfläche von Paperless (dms.muellerhv.de) wird damit nur noch für die Administration gebraucht.
- Hinweise an objektakte tragen nur Kennungen und Bezeichnungen (Titel, Einheit, Kontakt-ID, Ticketnummer, Kategorie), keine Namen und keine Kontaktdaten.

## 1.31.0 (27.09.2026) DMS-Seite mit Daten der Objektübernahme, Paperless-Objektsuche und Gesellschaftsfilter

- DMS und Objektübernahme (M29 Stufe 4): Anbindung an die Lese-API von objektakte über die neuen Einstellungen OBJEKTAKTE_API_URL, OBJEKTAKTE_API_TOKEN, OBJEKTAKTE_WEBHOOK_SECRET und OBJEKTAKTE_TENANT (auch mit Präfix MHVP_, leer bedeutet aus). Die Seite /dms zeigt je Objekt eine Kachel mit Übernahmestatus, offenen Prüffällen, Vollständigkeit und fehlenden Dokumenten; /dms/{Nummer} zeigt fehlende Dokumente, die Dokumentliste mit Sprung nach Google Drive und in das CRM sowie das Nachholen der Dokumentverknüpfung. Neue Endpunkte unter /integrations/objektakte.
- DMS und Objektübernahme: Webhook POST /integrations/objektakte/webhook mit HMAC-Prüfung und Idempotenz; abgelegte Dokumente werden als Dokument am Objekt angelegt und über objektakte-Kennung, Drive-Datei und Prüfsumme abgeglichen.
- DMS und Objektübernahme: Eigentümer- und Mieterlisten aus objektakte werden als Importvorschlag mit Testlauf, Abgleich und Freigabe geführt und nie ungeprüft in die Stammdaten geschrieben (Migration 0156).
- Dokumente (Übernahme aus dem Immoware Hub, 7.2): Paperless-Suche nach Objektnummer (genau die Nummer oder "Nummer, Zusatz", nie Teiltreffer), Gesellschaftsfilter über ein konfigurierbares Auswahlfeld in Paperless, neue Endpunkte GET /dms-documents und GET /dms-documents/companies, Filter company an den Dokumentlisten von Objekt und Ticket. Im CRM Auswahl und Spalte Gesellschaft im Dokumentbereich sowie Zuordnung der Gesellschaftsoptionen in den DMS-Einstellungen. Nur lesend, Annahme A-048.
- Dokumente: vertauschte Fehlertexte für 502 und 503 im Dokumentbereich korrigiert.
- Technik: Zusammenführung der Zweige claude/m29-dms-daten und claude/hub-paperless-suche auf den Stand 1.30.0, Migration der DMS-Anbindung als 0154_objektakte_dms hinter 0153 (überspringt bereits vorhandene Tabellen) eingereiht (Migrationskette linear), fehlende Typangabe in einem Gmail-Unit-Test ergänzt (mypy strict).

## 1.30.1 (27.09.2026) Betrieb: Migrationssperre, Objektspeicher lokal als Standard

- CI-Prüfung und Skript `scripts/check-migrations.sh`: bereits gemergte Alembic-Migrationen dürfen nicht mehr umbenannt, gelöscht oder in Revision und down_revision geändert werden. Neue Migrationen fortlaufend ab dem bisherigen Head. Runbook `docs/runbooks/migrationen.md`.
- Objektspeicher: SeaweedFS-Container ohne Profil dauerhaft aktiv, Migrationsjob wartet auf den Dienst, S3-Variablen standardmäßig lokal. Backup des Volumes `mhvp_objectstore-data` als Vorgabe in `env.backup.example`. Runbooks und ADR 0005 ergänzt (Entscheidung 27.09.2026).

## 1.30.0 (27.09.2026) Masterprompt-Ergänzung Welle B: Inline-Bearbeitung, Objekt- und Gebäudeseiten, Kataloge, Messdienstleister Stufe 3

- Stammdaten direkt bearbeiten (ADR 0012): Objekt, Gebäude, Einheit und Kontakt werden an Ort und Stelle mit Stift oder Bearbeiten je Abschnitt geändert, Speichern je Feld beim Verlassen mit sichtbarem Speicherstatus, Feldfehlern, Versionsprüfung und Konflikthinweis; beim Vertrag Bemerkungen und Mahnsperre mit Begründungspflicht, alles Übrige bleibt versioniert über das Vertragsformular; PATCH-Endpunkte für Objekt, Gebäude, Einheit, Kontakt und Vertragsbemerkungen mit Ereignisprotokoll und Änderungsdiff
- Objekt-, Gebäude- und Einheitenseiten: neue Gebäudeseite mit Energieausweis, Anzeige von Eigentümerdetails (Verrechnungskonto, Vollmacht, Steuerberater), Abrechnungszeiträumen, Untergemeinschaften, Objektmappe, Dienstleistern mit Freistellungsbescheinigung, Leerstandswerten und Zählerwechseln; Verknüpfungsleiste und Ereignisprotokoll auf Objekt, Gebäude, Einheit, Kontakt und Vertrag
- Kataloge und benutzerdefinierte Felder (4.11, Anhang B): alle Auswahllisten je Mandant als Systemeinträge mit Erweiterung und Deaktivierung, Zusatzfelder mit Gruppe, Gültigkeit, Eindeutigkeit, Min und Max, Standardwert und Feldtypen, neue Einstellungsseiten Kataloge und Felder (Migration 0152)
- Messdienstleister Stufe 3: kontrollierte schreibende Vorgänge mit getrennten Schritten Daten prüfen, Freigeben und Abrechnung verbindlich beauftragen beziehungsweise Nutzer und Rollen verbindlich übermitteln (On-Site Roles 2.0 mit vollständigem Datensatz je Nutzeinheit, Billing Input mit Anbietervorlage und Anbieterprüfung), Datenversion entwertet Freigaben bei jeder Änderung, Protokoll je Schritt, Zeitüberschreitung ohne Wiederholung; Freigabe je Verbindung, Modulschalter in den Mandanteneinstellungen, Anbieterwechsel und Einheitenbearbeitung im Objektreiter (Migration 0153)

## 1.29.0 (27.09.2026) Masterprompt-Ergänzung Welle A: Kontakt, Objekt und Einheit, Vertrag, Suche und Verknüpfungen, Kalender aus Datumsfeldern, Messdienstleister Stufe 2

- Kontakt nach Abschnitt 4.1 erweitert: Briefanrede, Bundesland, Landesvorwahl, Vorwahl und Notiz je Telefon, Datumsfelder, Kontotyp und Standardkonto je Bankverbindung, Sperrdatum, Löschprofil mit vorgemerktem Löschdatum (Löschung weiterhin manuell im Vier-Augen-Prinzip), Sperrliste, Notizen mit Titel und Wiedervorlage sowie die Reiter Beziehungen, Dokumente, Portal-Freigaben und Ereignisprotokoll (Migration 0147)
- Objekte, Gebäude und Einheiten nach Abschnitt 4.2 bis 4.4 erweitert: Energieausweis vollständig und ausschließlich am Gebäude (Migration übernimmt Objektwerte), Gebäude und Einheit mit Versionsprüfung (ETag), Abrechnungszeiträume je Art, Untergemeinschaften, Objektmappe, Eigentümer mit Verrechnungskonto, Vollmacht und Steuerberater, Bankkonto mit Sachkonto, Dienstleister mit Kundennummer, Freistellungsbescheinigung und Kreditorenkonto, Einheit mit Provision, Kautionsbetrag und Leerstands-Umlagewerten, Zählerwechsel (Migrationen 0148, 0149)
- Verträge: vertragsbezogene Umlagewerte mit Zeitraum, SEPA-Mandate mit Ertragsarten und Sonderumlage-Ausschluss, Einzugs- und Auszugsdatum, Vertragsbeendigung mit Zählerständen, Listen beendeter Verträge, Kautionen und Leerstand zum Stichtag; Vertragsseite mit Abschnitten Eigenschaften, Mandate und Debitorenkonto (Migration 0150)
- Globale Suche findet jetzt auch Gebäude, Tickets (auch als #Nummer) und Buchungen mit Berechtigung je Trefferart; Verknüpfungsleiste und Ereignisprotokoll mit CSV-Export je Datensatz, zunächst im Ticketdetail; Änderungsprotokoll filtert nach Entitätstyp
- Kalender und Fristen vereinheitlicht: Termine entstehen deterministisch aus Datumsfeldern (Eichdatum, Energieausweis, Vertragsende, Ein- und Auszug, Sanierung, Wiedervorlage, Versammlung), tragen Quelle, Kategorie und Erinnerungen und verlinken zur Quelle (Migration 0151)
- Messdienstleister Stufe 2: Oberfläche unter Einstellungen, Schnittstellen (Verbindungen, Einrichtungsassistent mit ehrlichem Funktionsstand, zentrale Zuordnungsübersicht mit Sammelfreigabe, CSV) und Reiter am Objekt (Zuordnungen, Einheiten, Abruf je Datenart, Verbrauch, Abrechnungsergebnisse, Klärung); lesende Adapter für ista und KALO nach bved-Spezifikationen, Dokumentenübernahme ohne Dubletten und mit Versionierung, Auftragsausführung mit Sperre, Cursor und Wiederholungen; Fähigkeitsmatrix im Betreiberdokument
- Betrieb: Migration 0146 idempotent, damit der Produktionsstand mit vorab eingespielter Vertragsfreigabe durchläuft

## 1.28.0 (26.09.2026) Betreiberentscheidungen vom 26.09.2026 umgesetzt: Gmail-Push und Vollabruf, Ticketampel und Auswertung, Kaution, Bank finAPI, Messdienstleister Stufe 1, Betrieb

- Messdienstleister (neues Modul `mhvp.metering`, Stufe 1 Backend, Regel M40-01, Migration 0145): Anbieterkatalog ista, Techem, KALO, Brunata Minol, BRUNATA-METRONA und Sonstige mit ehrlicher Funktionsanzeige in vier Dimensionen (dokumentiert, Adapter, Kontofreigabe, Verbindungstest) und Recherchestand 26.09.2026 (Quellen Q1 bis Q11, vor Implementierung erneut prüfen); zentrale Verbindungen je Mandant mit verschlüsselten Geheimnissen (nur setzen, nie auslesen), Test und Produktion getrennt, Verbindungstest nur lesend; Objektzuordnung zu externen Abrechnungseinheiten mit Leistungsbereich, Gültigkeit, Prüfstatus, Gruppierung, Konfliktprüfung, Versionsprüfung (409) und Anbieterwechsel mit Historie; Einheitenzuordnung mit getrennten Empfängern und Belegungsstatus; manueller Abruf als persistenter Auftrag, Klärungsbereich, Verbrauchswerte und Abrechnungsergebnisse versioniert ohne Buchung; CSV-Vorlage, Vorschau, Übernahme und Export; Rechte metering_connections:manage, metering_assignments:update, metering_sync:run, metering_data:read, metering_users:submit, metering_billing:order; Mandantenschalter metering_module_enabled (Standard aus); Endpunkte unter /metering; keine Anbieteradapter (Stufe 2, OPEN_QUESTIONS M40-01 bis M40-03); Oberfläche folgt
- Tickets: Ampel je Ticketzeile nach Zeit ohne Reaktion unsererseits (gelb neu, orange ab 24 Stunden, rot ab 96 Stunden, grün erledigt), serverseitig berechnet in derselben Abfrage (Felder last_staff_activity_at, last_inbound_at, last_activity_at, attention in GET /tickets und auf der Startseite), nur Handlungen von Mitarbeitern zählen (Statuswechsel, Zuweisung, Kommentar, gesendete Mail, Arbeitsauftrag), eingehende Mails und Portalkommentare setzen die Uhr nicht zurück; Standardsortierung Dringlichkeit (sort=urgency, Erledigte zuletzt), Filterhaken Nach Eingang (sort=created_desc); Legende, Textmarke mit Dauer und farbiger Rand in Übersicht, Meine Tickets, Startseite und Reiter Tickets; Reiter Tickets der Kontakt-, Objekt- und Einheitenseite blendet Erledigte standardmäßig aus (Umschalter Erledigte anzeigen); Regel M19-09, Handbuch Tickets
- Buchhaltung: Kostenkonten der Kontenrahmen-Vorlage als Entwurf nach der Betriebskostenverordnung vorbelegt (M10-02, Betreiberentscheidung 26.09.2026): Konten der Betriebskostenarten des Katalogs umlagefähig mit Abrechnungsart Betriebskosten und Schlüsselvorschlag (Wohnfläche, Verbrauch für Heizung, Warmwasser und Wasser), Heizungsreparaturen nicht umlagefähig, Rauchwarnmelder ohne Einordnung, Umsatzsteueroption bleibt offen; je Zeile Prüfkennzeichen Entwurf mit Vermerk "Freigabe durch Steuerberatung offen"; Seed füllt nur unbesetzte Felder und verändert eigene Einträge und bestehende Buchungskreise nicht; Zuordnungstabelle in Regel M10-02, Handbuch Buchhaltung
- Dokumente: Löschung gespiegelter Dokumente nach Betreiberentscheidung M6-03 vom 26.09.2026: Drive-Kopie wird gelöscht (endgültig, ersatzweise Papierkorb, im Journal vermerkt), Paperless-Dokument bleibt erhalten und erhält das Schlagwort "gelöscht" (wird angelegt, falls es fehlt), beide Schritte im Löschjournal mit Erfolg oder Fehler, Löschung "offen" bis beide Schritte gelungen sind, Wiederholung per Task, neue Endpunkte GET /documents/deletions und POST /documents/deletions/{id}/retry (Migration 0143), Sperre gespiegelter Dokumente entfällt, Restore-Wiederanwendung behandelt gespiegelte Dokumente gleich
- Bank: finAPI (M11-01, Betreiberentscheidung 26.09.2026: Aggregator finAPI zuerst, Datei-Import bleibt, EBICS später): Konten- und Umsatzabruf hinter der bestehenden Aggregator-Schnittstelle, OAuth2 Client-Token plus technischer finAPI-Benutzer und Benutzer-Token je Bankverbindung (verschlüsselt, kein Auto-Update durch den Anbieter), WebForm-Import ohne Bankzugangsdaten, inkrementeller Umsatzabruf je Konto mit Cursor und Überlappung, idempotenter Upsert nach Transaktions-ID, Beträge als NUMERIC, Standard-Basis-URL je Rechenzentrum (Sandbox oder Live, Einstellungen MHVP_FINAPI_BASE_URL_SANDBOX und _LIVE), Fehlercodes MHVP-BANK-0005 (Zugangsdaten abgelehnt) und MHVP-BANK-0006 (Ratenlimit, ohne automatische Wiederholung), Migration 0141; keine Zahlungsauslösung, G2 bleibt geschlossen; Doku docs/integrations/finapi.md
- KI: Einbettungen und Ähnlichkeitssuche (M7-03, Betreiberentscheidung 26.09.2026): OpenAI text-embedding-3-small über den vorhandenen Adapter (EU-Endpunkt bei Region eu), Speicherung in pgvector je Mandant mit RLS (Tabelle ai_embedding, Migration 0142), Indexlauf als Celery-Aufgabe in Stapeln mit Budgetzählung (Aufgabe embed) und maskierter Eingabe, answer_question und Wissensbasis der Mail-Vorbereitung suchen per Ähnlichkeit mit Schlüsselwort-Rückfall, neue Endpunkte POST /ai/embeddings/reindex und GET /ai/embeddings/status
- Betrieb: Lesezugang der Überwachung auf die Betriebskennzahlen (M9-04a, Betreiberentscheidung 26.09.2026): neues Recht platform:metrics:read, das nur ein von einem Plattformadministrator erzeugter API-Schlüssel trägt (POST, GET, DELETE /platform/ops/metrics-keys, Geheimnis einmalig, Ereignisse api_key.created und api_key.revoked, Ratenlimit wie jeder Schlüssel), GET /platform/ops/metrics (JSON und Prometheus) nimmt Plattformadministrator-Sitzung oder diesen Schlüssel an, jeder andere Endpunkt weist den Schlüssel ab, keine Migration; Runbook monitoring.md 3.1 mit Anleitung für Uptime Kuma
- Benachrichtigungen: jede Benachrichtigung trägt ein Ziel (target_type, target_id) und einen vom Server abgeleiteten Link (href) zum Betreff; ein Klick im CRM öffnet Ticket, Auftrag, Mail, Dokument, Vertrag, Objektakte, Fristenliste oder den Kalender mit geöffnetem Termin (/kalender?termin=...) und markiert nur diesen Eintrag als gelesen; Portal: neue Endpunkte GET /portal/notifications und POST /portal/notifications/read mit Portalrouten (Meldung, Auftrag, Übergabe) und Liste auf der Übersicht
- Dokumente: Standard-Aufbewahrungsprofile je Mandant als Entwurf (Entwurf, Prüfung Steuerberatung offen; Betreiberentscheidung M6-04 vom 26.09.2026: Belege, Journale, Abrechnungen 10 Jahre; Geschäftsbriefe, Vorgänge, Mails 6 Jahre; Verträge 10 Jahre nach Ende; Portal- und Bewerberdaten 6 Monate nach Zweckende; WEG-Protokolle und Beschlüsse dauerhaft), Seed idempotent ohne Überschreiben eigener Änderungen, Löschung bleibt bis zur Freigabe gesperrt, Freigabe nur mit Recht Mandanteneinstellungen im Vier-Augen-Prinzip und protokolliert, Felder retention_months, permanent, review_note, status (Migration 0139), noch keine Einstellungsseite (nur API)
- Buchhaltung: Ausgleich offener Posten nach gesetzlicher Reihenfolge als Vorschlag (M10-03, Betreiberentscheidung 26.09.2026): POST /accounting/ledgers/{id}/open-items/settlement-proposal berechnet deterministisch (fällig vor nicht fällig, geringere Sicherheit, größere Last, ältere zuerst, Kosten vor Zinsen vor Hauptforderung), Bestimmung des Zahlers aus Verwendungszweck oder Liste geht vor (D39), Überzahlung bleibt Guthaben; Bestätigung über .../confirm erzeugt einen Buchungsentwurf mit Ausgleichsplan und protokolliert Regelversion und Fingerabdruck, sofortiges Buchen nur mit G1; Karte auf der Buchungskreisseite; Vermerk „Rechtsprüfung vor G1 offen“, Regel M10-03, Handbuch Buchhaltung
- Anmeldung (Betreiberentscheidung M2-01 vom 26.09.2026): Mindestlänge des Passworts 6 Zeichen (Kontosperre nach 10 Fehlversuchen für 15 Minuten unverändert; Hinweis auf die längere BSI-Empfehlung nur in der Dokumentation), zweiter Faktor für CRM und Portal nicht mehr Pflicht (auch nicht für Administratoren), Einrichten und Ausschalten unter Einstellungen, Meine Daten (CRM) und Sicherheit (Portal, neue Seite) mit neuen Endpunkten POST /auth/totp/setup, /confirm, /disable und totp_enabled in GET /auth/me, Anmeldeschritt mfa_setup_required und POST /auth/mfa/setup entfallen; gemerkte Geräte 90 statt 180 Tage (Dieses Gerät 90 Tage merken), jetzt auch im Portal, Liste und Abmelden in den Einstellungen; Regel M2-01, ADR 0006 zweiter Nachtrag, offene Frage M2-09 (Prüfung gegen kompromittierte Passwörter nicht vorhanden)
- Tickets und Mail: Gmail-Push per Pub/Sub (Nachrichten erscheinen sofort, Abruf alle fünf Minuten als Sicherheitsnetz, Watch-Erneuerung täglich), Vollabruf des gesamten Posteingangs beim Verknüpfen und manuell je Postfach (Button und Serverbefehl python -m mhvp.communication.backfill), Mail auf erledigt archiviert sofort in Gmail und schließt das Ticket automatisch mit Auskunft erteilt, wenn keine Mail und kein Arbeitsauftrag mehr offen ist (Migration 0144)
- Tickets: Erledigungsarten um Zahlung geklärt, Termin vereinbart, Mangel behoben, Vertrag geändert erweitert und je Mandant pflegbar (Migration 0136, Einstellungen Mandant); Freigeben und antworten der Telefonassistenz legt keinen Entwurf ohne Empfänger an; Ticketsuche findet auch Mailinhalt und interne Beschreibung
- Auswertung Tickets: neue Seite mit Durchsatz je Tag, Woche, Monat, Quartal und Jahr, erledigte Tickets je Stunde und Minute, Erstreaktion und Bearbeitungsdauer (Median, 90. Perzentil), Rückstand, Tabellen je Mitarbeiter und je Postfach (persönlich oder Standardpostfach), CSV-Export
- Kontakte: Mehrpersonen-Parteien aus dem Immoware24-Adressbuch als eine Partei mit Mitgliedern, Bevollmächtigte mit Zustellregel (beide, nur Bevollmächtigter, nur Eigentümer) für Serienbriefe, Serienversand und WEG-Einladungen (Migration 0140)
- Verträge: Kautionsabrechnung als Entwurf mit Zinsart je Abrechnung (individuell je Jahr, Referenzzinssatz je Jahr aus den Einstellungen, ohne Zins), Freigabe hinter G3 (Migration 0138, Regel M5-02)
- Buchhaltung: Erlöskonten der Mietverwaltung 060300 bis 060800 als Vorschlag mit Prüfkennzeichen Entwurf (Migration 0137, M10-01)
- KI: Lernbeispiele nur bei aktivem Mandantenschalter, Löschung bei Kontaktlöschung (Migration 0134, ADR 0010); zweiter Anbieter mit Wechsel bei Fehler oder Budget, Endpunktregion wird an den Anbieter durchgereicht (M7-02, M7-07)
- Plattform: Superadmin-Kennzeichen und Schalter gate_superadmin_bypass für Gate-Freigaben ohne zweite Person, Standard aus (ADR 0011, Migration 0135); Anmeldung ohne Pflicht zum zweiten Faktor, gemerkte Geräte 90 Tage auch im Portal
- Automatisierung: Regel-Webhooks mit Wiederholung nach Stufenplan, Zustellprotokoll und erneuter Zustellung (A82, Migration 0133)
- Portal: HEIC-Fotos vom iPhone werden angenommen und in JPEG gewandelt (A72); QR-Code im Einladungs-PDF (A86); Kontaktereignisse auch aus Staging- und Objektakte-Import (A87)
- Betrieb: IONOS S3 Object Storage als Produktionsspeicher (make check-s3), Images aus der GitHub Container Registry, Uptime Kuma im Produktions-Compose, Off-site-Backup nach Hetzner Object Storage mit age-Verschlüsselung und Aufbewahrung 14/8/12 (scripts/backup-offsite.sh)
- Oberfläche: Immoware24 nur noch unter Einstellungen erreichbar, nicht mehr im Hauptmenü
## 1.27.1 (26.09.2026) Erledigungsnotiz für Administratoren optional

- Tickets: Mandantenadministratoren schließen Tickets ohne Erledigungsnotiz (einzeln, Sammelaktion), der Abschlussdialog erscheint bei ihnen nicht. Für alle anderen bleibt die Notiz Pflicht.

## 1.27.0 (26.09.2026) Zuordnung im Bericht, Objekteigentümer, Freigabe der Importverträge

- Import: Offene Zuordnungen (nicht gefunden, mehrdeutig, Vermieter fehlt) stehen im Bericht als Tabelle und werden per Kontaktauswahl direkt zugeordnet (POST /imports/immoware24/lists/zuordnung/manuell), bei fehlendem Vermieter mit Auswahl des Objekteigentümers. Der letzte Bericht bleibt im Browser erhalten.
- Objekte: "Eigentümer festlegen" auf der Objektseite für Mietverwaltungsobjekte (Kontakt, seit, Anteil, Ersetzen mit Datum), Reiter "Ohne Eigentümer" und Kennzeichen "Eigentümer fehlt" in der Objektliste (POST /properties/{id}/owner, GET /properties?without_owner=true). WEG-Objekte führen Eigentum je Einheit.
- Verträge: Importverträge tragen Herkunft und Freigabestatus (Migration 0133). Die Sollstellung überspringt nicht freigegebene Verträge und weist das aus. Neue Seite Verträge, Freigabe mit Filter, Summen, Mehrfachauswahl, "Alle freigeben" mit Bestätigung und "Ablehnen" je Vertrag (beendet ihn zum Beginn). Berechtigung contracts:approve (Administratoren). Kennzeichen "Freigabe ausstehend" in Liste und Detail.

## 1.26.1 (26.09.2026) Mail: Aktionen oben, Mehrfachauswahl, Erledigt archiviert

- Mail: Die Aktionen Antworten, Ticket anlegen und Erledigt stehen zusätzlich als feste Leiste oberhalb der Nachricht.
- Mail: Mehrfachauswahl in der Liste (Kontrollkästchen, Strg bzw. Cmd plus Klick, Shift für Bereiche, Alle auswählen, Escape hebt auf) mit Sammelaktion "Als erledigt markieren" (POST /mail/messages/bulk, bis 200 Nachrichten, Postfachzugriff je Nachricht geprüft).
- Mail: "Erledigt" in der Mailansicht archiviert die Gmail-Nachricht wie der Ticketabschluss (Postfacheinstellung "Erledigt archiviert Mail"), einzeln und als Sammelaktion.

## 1.26.0 (26.09.2026) Portalzugang am Kontakt, IBAN-Ablehnungsgrund, Importereignisse, Dokumentliste, Telefonassistenz-Korrekturen

- Kontakte: Abschnitt Portalzugang auf der Kontaktakte mit Status (kein Zugang, eingeladen, aktiv, gesperrt), Einladung mit QR-Code und neuem Leseendpunkt GET /portal-admin/accounts?contact_id (A86, CRM-Teil)
- Kontakte: Ablehnungsgrund der IBAN-Freigabe wird gespeichert und angezeigt (rejected_reason, rejected_by, rejected_at, Migration 0132), Kontaktliste zeigt den Hinweis IBAN wartet auf Freigabe ohne N+1
- Importe: Listen- und Zuordnungsimporte lösen dieselben Ereignisse contact.created und contact.updated aus wie die manuelle Pflege (Regelwerk und Webhooks greifen, A87 teilweise)
- Dienstleisterverträge: Anzeigename des Dienstleisters in Liste und Detail statt Kennung
- Dokumente: neue Dokumentliste im CRM mit Volltextsuche und Entwurfsfilter (is_draft), Upload bei fehlendem oder nicht erreichbarem Dokumentenspeicher antwortet mit 503 MHVP-DOC-0007 statt 500, keine halben Dokumentzeilen
- Tickets: Freigeben und antworten der Telefonassistenz legt keinen Entwurf ohne Empfänger mehr an (422 mit Hinweis), Zusammenführen protokolliert je Quellticket Statusereignis mit Erledigungsnotiz und Lernbeispiel
- Abnahme: Playwright gegen den Stack 12 CRM und 11 Portal grün, zwei Specs an die neue Anzeige angepasst (Bruttobetrag formatiert, Anhangsliste der Meldung), spezifische Spec-Läufe über MHVP_E2E_PW_ARGS
- Dokumentation: Handbuch für Erledigungsnotiz, Telefonassistenz, ausgeblendete erledigte Vorgänge, Objektbezüge und Wissen; Regeln M19-07 bis M19-09, ADR 0010 Lernbeispiele (Betreiberentscheidung), offene Fragen M19-03 und M19-04, Lückenliste A90 bis A99
- Offen (Betreiber): Datenschutzregel für Lernbeispiele (M7-04, ADR 0010), AVV und Anbieterfreigabe Telefonassistenz (M19-03), Erledigungsartenliste (M19-04), QR-Code im Einladungs-PDF (M21-08)

## 1.25.1 (26.09.2026) Adressen nachtragen, Einheitenliste und Einheitenseite

- Importe: Abschnitt "1a. Adressen nachtragen" auf der Listenimport-Seite: Straße und Hausnummer aus den Objektnamen ableiten oder eine Adressliste (Objektnummer, Straße, Hausnummer, PLZ, Ort; CSV oder XLSX) hochladen. Füllt nur leere Felder, meldet Abweichungen als Konflikt.
- Objekte: Einheiten natürlich sortiert (1, 2, 10 statt 1, 10, 2), bei rein numerischen Nummern dreistellige Anzeige. Nummer und Bezeichnung verlinken auf die Einheitenseite. Neue Spalten Eigentümer, Mieter ("kein Mieter") und Fläche.
- Einheitenseite: alle Stammdaten (Typ, Lage, Fläche, Miteigentumsanteile, Umlageschlüssel, Zusatzfelder, Altsystem-Notizen), Karten Eigentümer und Mieter mit Kontaktlink, seit, Anteil und Miete, beendete Verträge aufklappbar. Neue Endpunkte GET /units/{id}/occupants und /properties/{id}/units?with_occupants=true.

## 1.25.0 (26.09.2026) Zusammenführung mit 1.24.0 und Fix- und Abschlusswelle: Vier-Augen nach Betreiberentscheidung, Review-Befunde Tickets und Mail, Sicherheit, Performance, Bedienbarkeit, Vertragsformular, Import-Robustheit, Anhang D 54 von 58

- Tickets und Mail: Betreiberentscheidung M20-03 umgesetzt: Vier-Augen-Freigabe nur für Mitarbeiter mit Kennzeichen Azubi oder neuer Mitarbeiter (Einstellungen, Benutzer, optional befristet), alle anderen senden Ticketantworten direkt; Verfasser und Freigeber mit Zeitpunkt als Ticketereignisse und im Mailverlauf sichtbar; Notbremse alle Antworten mit Freigabe (Standard aus); Freigabeberechtigte werden benachrichtigt (Migration 0129, Regel M20-06)
- Prüfung Tickets und Mail: 31 von 34 Befunden behoben, darunter Doppelversand bei Verbindungsfehler ausgeschlossen (zweiphasiger Versand mit Nachweis), Rechnungsweiterleitung nach Commit, Postfach löschen als Deaktivierung ohne Sichtbarkeitsverlust, Mailliste mit Vorschau statt Volltext, Thread-Zuordnung über References und Gmail-Thread, abgewiesene Anhänge sichtbar, Kommentare mit Autor, interne Beschreibung, Zuweisungsereignis, Archivierung nach Commit, Arbeitsaufträge mit Terminvorschlägen im Ticket (Migration 0126)
- Sicherheit: Review 1.22 ohne hohe Befunde, 5 mittlere und 12 niedrige behoben (Ratenbegrenzung bei gefälschtem API-Key, Größenlimit Paperless-Webhook, Rechtsträgerbereich in WEG-Finanzen, Prüfung, Beirat und Mehrheitsregeln, Aushang-Sichtbarkeit je Zielgruppe, Webhook-Ziel mit gebundener Adresse gegen DNS-Umlenkung, Geheimnisse nur serverseitig, Paketgröße Einsicht, Telefonie-Antwort ohne Trefferstatus)
- Performance: Listen Verträge, Einheiten, Parteien, Journal, Rechnungen, Lastschriftläufe, Dokumenteingang und Startseite ohne N+1 (bis zu 57 auf 11 Abfragen), 18 neue Indizes (Migration 0127), Paginierung Verträge, Mandate, Journal, Rechnungen, Berechtigungskontext je Prozess 30 Sekunden zwischengespeichert mit sofortiger Wirkung von Sperre und Rollenentzug im selben Prozess
- Bedienbarkeit CRM und Portal: 63 Befunde behoben, darunter zwei Seitenabstürze (WEG Prüfauftrag, Objektseite), Kennzahlenkarte Bankabgleich lud im Betrieb nie, Lastschriftläufe haben jetzt eine Seite mit Vier-Augen-Freigabe hinter G2, Rohwerte statt Beträge und Daten in Exposé, Belegeingang und Automatisierung, Fehler- und Ladezustände, mobile Kartenansicht Hausgeldkonto, einklappbares Portalmenü, deutsche Fehler- und 404-Seiten im Portal
- Neue Funktionen: Vertragsformular im CRM für Miet-, Eigentums- und SEV-Verträge mit Zahlungsplan und Kaution; Webhook-Abonnements unter Einstellungen mit Zustellprotokoll; Prüfauftrag Beirat im CRM anlegen mit Positionsfilter und Beiratsstellungnahme (CRM und Portal); Formular-Einreichungen je Vorlage; Terminvorschläge der Dienstleister im CRM; Ratenplan Darlehen als Orientierung, Beschlussbezug am Versicherungsfall, Überleitung im Übernahmejahr (Migration 0128); Regel-Engine mit Bedingungen auf Objekt, Einheit, Kontakt und Vertrag, automatisch erzeugte Briefe als Entwurf gekennzeichnet; OpenImmo-Schemaprüfung mit hinterlegter XSD; Namensmaskierung im Belegeingang für Einzelunternehmer
- Import Immoware24: Listenimport liest Windows-1252, BOM, Semikolon, Komma, Tab, eingebettete Trennzeichen, wiederholte Kopfzeilen und Spalten in beliebiger Reihenfolge; Pflichtspalten mit klarer Meldung; Duplikate gemeldet statt still übernommen; Nummernzuordnung mit führenden Nullen; Telefon und E-Mail in allen Schreibweisen; IBAN nur als maskierter Hinweis; Checkliste im Handbuch
- Abnahme und Tests: Anhang D jetzt 54 von 58 technisch bestanden (offen nur D24 bis D27 wegen fehlender Betreiberregeln); Playwright gegen den Stack 12 CRM und 11 Portal grün inklusive Fototest; 66 neue Abdeckungstests; Ergebnisbuchung nach Eigentümerwechsel repariert, Versionsvergleich der WEG-Abrechnung als Endpunkt und Anzeige; Seed-Skript und Test-Datenbankaufbau stabil
- Dokumentation: Entscheidungsvorlage für den Betreiber (docs/reviews/2026-09-26-entscheidungsvorlage-betreiber.md), Handbuchkapitel für alle Funktionen seit 1.20, Lückenliste konsolidiert (A72 bis A89), Plan-Dokumente mit Stand 26.09.2026, Reviews Performance, Sicherheit 1.22, Bedienbarkeit CRM und Portal
- Offen (Betreiber): OpenImmo-XSD beschaffen (M26-02), Zins und Tilgung in der Jahresabrechnung (M24-03), Heizkosten und Verbrauchsinformation (D24 bis D27), Freigabestufen G1 bis G5 mit Steuerberatung, Rechtsberatung und Bank, Serverhärtung (M9-05)
- Zusammenführung: Stände 1.23.0 bis 1.24.0 der parallelen Sitzung übernommen (Migrationen Erledigungsnotiz und Hallo Heidi laufen jetzt als 0130 und 0131 hinter 0126 bis 0129)

## 1.24.0 (26.09.2026) Ticketfilter, Erledigungsnotiz, Hallo Heidi, Wissensdatenbank, Assistent-Rolle

- Tickets und Mail: Umschalter "Erledigte anzeigen" in den Übersichten, erledigte Vorgänge sind standardmäßig ausgeblendet. Kontakt-, Objekt- und Einheitenseite zeigen die volle Historie. Statusauswahl im Ticket nach Rolle: Administratoren wählen jeden Status, andere nur die erlaubten Folgestatus.
- Tickets: Erledigungsnotiz beim Abschluss (Art aus fester Liste plus Freitext, auch in der Bulk-Aktion und beim Zusammenführen). Jeder Abschluss wird als Lernbeispiel gespeichert, gelernte Playbooks erhalten den Schritt "Erledigung", Vorschläge zeigen "Bei ähnlichen Vorgängen wurde".
- Tickets: Anruf-Mails der KI-Telefonassistenz (Hallo Heidi) werden erkannt, Anrufer über Objekt plus Name, sonst Name oder Rufnummer zugeordnet, Objekt und Einheit am Ticket gesetzt. Eine unbekannte Rufnummer erzeugt automatisch den Vorschlag "Telefonnummer ergänzen" mit Antwortentwurf; "Freigeben und antworten" übernimmt die Nummer und legt die Antwort als Entwurf an. Einstellungen je Mandant unter Postfächer.
- Einstellungen: neue Seite "Wissen" mit gelernten Playbooks (Trefferzahl, letzte Nutzung, Deaktivieren) und Lernbeispielen mit Filter.
- Assistent: Eine Rolle aus der Chatanweisung ("Rolle bank") wird beim Tabellenimport auf alle Kontakte gesetzt, die Werte bank und verwalter sind neu. Ohne erkennbare Rolle fragt der Assistent nach. Rolle nachträglich für einen Importlauf setzbar (Importverlauf und POST /ai/import-runs/{id}/apply-role).
- Migrationen 0126 (Erledigungsnotiz, playbook.last_used_at, KI-Aufgabe ticket_resolution) und 0127 (Anrufassistenz, KI-Aufgabe call_summary).

## 1.23.1 (26.09.2026) Upload-Seite für Immoware24-Listen

- Importe: neue Seite "Immoware24 Listenimport" (/importe/immoware24-listen) mit Upload im Browser für Objektdaten, Kontaktlisten (Rolle je Datei, auch Dienstleister) und die Zuordnung von Eigentümern und Mietern zu Einheiten. Je Abschnitt Testlauf und Übernehmen mit Bestätigung, Bericht mit Zählern, nicht gefundenen und mehrdeutigen Namen sowie Konflikten. Neuer Endpunkt POST /imports/immoware24/lists/zuordnung.

## 1.23.0 (26.09.2026) Objektbezüge im Kontakt, CSV-Zuordnung, Gmail-Archivierung, Ticketfilter

- Kontakte: Abschnitt "Beziehungen zu Objekten und Einheiten" (Mieter, Eigentümer, Kategorie, Zeitraum, Status) unten auf der Kontaktseite, neuer Reiter "Tickets" mit allen personenbezogenen Tickets. Rollen Mieter und Eigentümer werden aus Verträgen, Eigentümerzuordnungen und Objektakte-Zuordnungen automatisch abgeleitet, Backfill über POST /contacts/roles/recompute.
- Import: neues CLI `python -m mhvp.imports.zuordnung` verknüpft Eigentümer und Mieter aus den Objektdaten mit den importierten Kontakten und legt Verträge mit vereinbartem Zahlbetrag an (idempotent, Testlauf als Standard, Bericht zu Leerstand, mehrdeutigen Namen und Konflikten). Kontaktimport speichert Briefanrede, Bundesland und Exportnamen; Rolle Dienstleister auch über die API. Handbuch `docs/handbuch/import-zuordnung.md`.
- Immoware24: "Alle unverknüpften Kontakte übernehmen" scheiterte mit internem Fehler (Telefon ohne Pflichtfeld Label), behoben.
- Gmail: Beim Abruf wird die Gmail-Kennung jeder Nachricht gespeichert, fehlende Kennungen der letzten 90 Tage werden beim nächsten Abruf nachgetragen. Damit greift "Erledigt archiviert Mail" bei done, closed und rejected.
- Tickets: Übersichten blenden done, closed und rejected standardmäßig aus (`include_closed=true` zeigt sie), Mailübersicht analog. Mandantenadministratoren dürfen jeden Status in jeden anderen setzen, ohne Zwischenschritte (Ereignis mit Kennzeichen admin_override). Suche "beinhaltet" jetzt auch über Betreff und Absender verknüpfter Mails sowie Kontakt-E-Mail.
- Server: Runbook um vertrauenswürdige Betreiber-IP (fail2ban ignoreip, sshd Match Address) und den zweiten Teil des Vorfalls vom 26.09.2026 ergänzt.

## 1.22.1 (26.09.2026) SSH-Härtung: Passwortanmeldung bleibt aktiv

- Server: `scripts/server/harden-ssh.sh` lässt die Passwortanmeldung standardmäßig aktiv und schaltet sie nur mit `--nur-schluessel` ab. Drop-in heißt jetzt `00-mhvp-ssh.conf` und hat Vorrang vor fremden Drop-ins.
- Runbook Server-Recovery: Vorfall 26.09.2026 (Drop-in `90-hardening.conf` sperrte Passwort-Login nach cloud-init-Reset) dokumentiert.

## 1.22.0 (26.09.2026) Master-Prompt-Umsetzung Welle 6: Ticket-Mails mit TNR#, Regel-Engine Stufe 2, Portal (Eigentümer, Beirat, Formulare, Schwarzes Brett, PWA), WEG (Darlehen, Versicherung, Überleitung, Protokoll, Einsicht), Telefonie, Abgleichbericht

- Tickets und Mail: Mailverlauf im Ticket als Thread mit Anhängen (Vorschau Bild und PDF, Download, Als Beleg erfassen), Antwortformular im Ticket (An, Kopie, Betreff, Text, Anhänge) mit Vier-Augen-Freigabe wie bisher; jede Antwort trägt die Ticketnummer im Betreff (TNR#412), eingehende Mails mit TNR# werden dem Ticket nur zugeordnet, wenn der Absender am Ticket beteiligt ist, sonst als Vorschlag angezeigt; Antwort auf ein erledigtes Ticket öffnet es wieder und benachrichtigt den Bearbeiter; Postfachzugriff wird auch bei Einzelmails geprüft (Regel M19-06, Migration 0119)
- Behobene Befunde aus der Prüfung Tickets und Mail (docs/reviews/2026-09-26-review-tickets-mail.md): Gmail-Abruf verlor Mails bei mehr als 50 neuen Nachrichten oder bei Einzelfehlern (jetzt seitenweise mit Nachlauf), Rechnungsweiterleitung ohne Anhänge, SLA-Uhr für Tickets aus Mail und Portal, Ticketliste mit Seitensteuerung, Indizes und eindeutige Mail-Deduplizierung (Migration 0120)
- Automatisierung: Regel-Engine Stufe 2 mit Aktionen Webhook (signiert), E-Mail-Entwurf aus Vorlage, Brief-Entwurf, KI-Aufgabe; Zeitplan als Auslöser (täglich, wöchentlich, monatlich, genau ein Lauf je Termin); strukturiertes Regelformular mit Vorschau statt JSON (Migration 0110)
- Portal: Eigentümerseiten Beschlüsse, Ansprechpartner und Hausgeldkonto (nur gebuchte Werte, ohne Rechtsfolge); Portalrolle Beirat mit Prüfungsraum (Prüfauftrag, Belege, Vermerke, Rückfragen, keine Freigabe, Migration 0109); Schwarzes Brett je Objekt im CRM pflegbar und im Portal sichtbar; Lesebestätigungen am Dokument im CRM als Indiz mit Test D34; Fotos an Schadensmeldungen als Dokumentverknüpfung mit Metadatenbereinigung; Dienstleister-Terminvorschläge mit Bestätigung durch den Bewohner und Fotos der Ausführung (Migration 0111); konfigurierbare Formulare je Mandant mit Einreichung als Ticket (Migration 0115); QR-Code zur Einladung im CRM; Portal als PWA installierbar mit Offline-Startseite
- WEG: Darlehen, Versicherungsfälle und größere Maßnahmen mit Positionen aus gebuchten Buchungen (Migration 0116); Überleitungsrechnung Gesamtgeldfluss im Abrechnungspaket mit erklärten Differenzen, unerklärte Differenz sperrt die interne Freigabe (Regeln W04, W10); Protokollentwurf der Versammlung als PDF im Mandanten-CI; Einsichtsanfragen außerhalb des Portals mit Verlauf und Bereitstellungspaket mit Prüfsummen (Migration 0117); neue Berechtigungsressource hoa
- Vermietung: Energieausweisdaten am Objekt und Angebotsmiete an der Anzeige, Vollständigkeitsprüfung von OpenImmo-Export und Exposé darauf gestützt (Migration 0112)
- Kommunikation und Betrieb: Telefonie-Webhook anbieterneutral mit Signatur, Zuordnung über Rufnummer, Anrufliste am Kontakt und Rückrufvorschlag (Migration 0118); täglicher Abgleichbericht Parallelbetrieb je Objekt aus Immoware24-Rohzeilen mit Differenzliste und CSV; Backup-Prüfjob 02:00 mit Kennzahl; ausgehende Webhooks contact.updated und invoice.issued; Namensmaskierung im Belegeingang auch ohne Anrede
- API: Versionsregel als ADR 0009 mit Deprecation-Headern, Drift-Prüfung meldet Entfernung von Pfaden ohne Deprecation; Handbuchkapitel Objekte, Verträge, Dokumente, Buchhaltung, WEG und Abrechnung
- Technik: Seed-Skript registriert alle Modelle (Abbruch bei membership.contact_id behoben), Migrationskette 0108 bis 0120 linear, Downgrades 0110 und 0112 unter erzwungener RLS lauffähig, eindeutige Schemanamen im OpenAPI-Dokument, Testnutzer je Modul eindeutig
- Aus der parallelen Sitzung: Kontakte: neue oder geänderte Bankverbindungen (IBAN) brauchen die Freigabe einer zweiten Person (contacts:approve), der Ersteller darf nicht selbst freigeben; nicht freigegebene Konten werden in Lastschrift, Zahlung, SEPA-Mandat und Rechnungsabgleich nicht verwendet. Bestandskonten gelten mit Migration 0121 als freigegeben
- Aus der parallelen Sitzung: Verträge: Dienstleisterverträge mit Laufzeit, Kündigungsfrist und automatischer Verlängerung; Kündigungstermin als Orientierung in der Fristenliste mit 14 Tagen Vorfrist (Migration 0122)
- Aus der parallelen Sitzung: WEG: Beschlussfrist virtueller Versammlungen mit Quellenangabe, in der Fristenliste mit 7 Tagen Vorfrist (Migration 0123)
- Aus der parallelen Sitzung: Bankabgleich: Tilgungsbestimmung aus dem Verwendungszweck (Rechnungs- und Sollstellungsnummern, Monate, Quartale) setzt den passenden offenen Posten nach vorn, jede Zuordnung trägt eine Begründung
- Aus der parallelen Sitzung: Mahnwesen: Zahlungserinnerung (Stufe 1) immer ohne Gebühr und Zinsen, Validierung in den Einstellungen und Schutz im Mahnlauf; Standard-Zahlungsfristen 14, 10 und 7 Tage je Stufe mit Hinweis im Formular
- Aus der parallelen Sitzung: KI-Kontierung (propose_posting): Ausgabeschema, Prompt mit Datenminimierung und Sperre, aktiv nur mit Mandantenschalter und freigegebenem Anbieter mit AVV; Ergebnis nur als Vorschlag, nichts wird gebucht (Migration 0124)
- Aus der parallelen Sitzung: WEG: Mehrheitsregeln je Beschlussgegenstand mit Fundstelle und Freigabe durch zweite Person, Prüfung "erreicht / nicht erreicht / nicht prüfbar" am Beschluss ohne Statusänderung (Migration 0125)
- Oberfläche: Die obere Menüleiste des CRM ist jetzt deckend; der fixierte Tabellenkopf (Name, Art, Rolle) der Kontaktliste schien beim Scrollen durch die halbtransparente Leiste hindurch
- Offen (Betreiberentscheidungen in docs/OPEN_QUESTIONS.md): Direktversand einfacher Ticketantworten ohne Vier-Augen-Freigabe (M20-03), Wiederholungsplan für Regel-Webhooks (M9-08), Verteilung von Zins und Tilgung in der Jahresabrechnung (M24-03), Fristen und Umfang der Einsicht (M25-05), Telefonieanbieter (M23-06), QR-Bibliothek für Einladungs-PDF (M21-08)

## 1.21.0 (26.09.2026) Master-Prompt-Umsetzung Welle 5: Abnahmefälle Anhang D, Lastschrift, XRechnung, E-Rechnung, Eigentümerabrechnung, Prüfexport, Regel-Engine, Tagesjobs, Portal und Importassistent

- Abnahme Anhang D: 43 von 58 Fällen technisch bestanden (Protokoll docs/acceptance/PROTOKOLL-2026-09-26.md), darunter Konkurrenz und Wiederholung des Sollstellungslaufs (D48), historische Stichtage (D49), Berechtigungen aller 38 Massenendpunkte (D50), Zahlungsfreigabe und Bankrückmeldung (D35 bis D38), Aufbewahrungssperre und Import-Rücknahme (D43, D46), Prompt-Injection ohne Wirkung (D57), WEG-Fälle (D18 bis D20, D54), Beirat (D32, D33, D53), Portalzugriff über alle Pfade (D29 bis D31), Betriebskosten (D21 bis D23, D28), Restore mit Löschjournal (D47); fachliche Bestätigung bleibt offen (V16)
- Behobene Produktfehler aus den Abnahmen: Idempotenzschlüssel blockierte den Neulauf nach Storno des Sollstellungslaufs; Verwalterhonorar belastete SEV-Eigentümer mit allen Einheiten des Objekts; SEV-Abrechnung enthielt Einheiten fremder Eigentümer; KI-Kontext hatte keinen Dokumentfilter je Portalnutzer; Ablehnungsereignis der Löschsperre ging im Rollback verloren; Vier-Augen-Prinzip prüfte nur die Benutzerkennung; Bankabstimmung meldete fremde Konten nicht als unbekannt
- Buchhaltung: SEPA-Lastschriftdatei pain.008 mit Mandatsprüfung, Sequenztyp und Vorabinformation als Entwurf (Datei hinter G2); XRechnung UBL 2.1 für Verwalterhonorare, mit KoSIT-Validator geprüft; E-Rechnung lesen (XRechnung, ZUGFeRD) im Belegeingang mit Widerspruchsanzeige; Eigentümerabrechnung Miete und SEV als Entwurf (Regel A06); Prüfexport nach Abschnitt 7.7 als ZIP mit Prüfsummen; DATEV-Kontenzuordnung je Mandant mit Sperre bei fehlender Zuordnung; Steuerberaterzugang je Rechtsträger; Rechtsträger der verwaltenden Gesellschaft per Einrichtungsschritt; MT940-Import; Kennzahlen Abdeckungsgrad und Fehlerquote des Bankabgleichs
- Mahnwesen und Abrechnung: Textbausteine je Mahnstufe mit Forderungsaufstellung, Mahnbescheid-Vorbereitung als PDF mit Hinweis auf anwaltliche Prüfung, Anschreiben Guthaben und Nachzahlung je Mieter aus dem Snapshot (Regel A07), KI-Plausibilität des Abrechnungsentwurfs (check_statement, 24 Evaluationsfälle)
- Automatisierung und Jobs: Regel-Engine Stufe 1 (Auslöser, Bedingungen, Aktionen Ticket, Benachrichtigung, Feld setzen, Testlauf, Protokoll), Tagesübersicht 07:00 und Fristenliste 20:00 mit Vorfrist, Dokumenteingang 06:30 mit Zuordnungsvorschlägen, protokollierte Spiegellöschung, Erinnerung vor Ablauf der finAPI-Zustimmung, Paperless-Webhook mit Signaturprüfung, Idempotency-Key für alle schreibenden Endpunkte, Ratenbegrenzung mit X-RateLimit-Headern
- Übergabe und Portal: Versionsverknüpfung beim U-Protokoll-Import, Lesebestätigung als Indiz beim Dokumentabruf (Datenmodell), Schwarzes Brett (Datenmodell)
- Importassistent: Immoware24-Listen (Objektdaten, Kontakte) über die Oberfläche mit Testlauf und Übernahme; Schnellpfad für Eigentümer- und Mieterlisten mit deterministischer Zeilenumsetzung; Evaluationsdatensätze für alle KI-Aufgaben mit mindestens 20 Fällen
- KI-Chat: Freitext-Kontakte aus eingefügtem Text, Verbindungstest je Modellstufe, Ausgabegrenze je Stufe; Tickets: Erkennungskorpus für Stammdatenänderungen (100 Prozent Trefferquote im Korpus), Antwortentwürfe je Änderungsart; objektakte: Synchronisationsstand, Benutzerabbildung, KI-Kostenauswertung, Listenablage als Dokument, Eigentümer- und Mieterlisten; Anzeigen: Bilder je Anzeige für den OpenImmo-Export
- Sicherheit: Review der 1.19.0-Endpunkte (docs/reviews/2026-09-26-sicherheitsreview-1.19.0.md), acht Befunde behoben (Dump-Pfad auf Exportverzeichnis begrenzt, Größenlimits, Postfachprüfung bei Ticketantworten, LIKE-Escaping, CSV-Formelschutz); englische Übersetzungen vollständig mit Prüfskript im Lint
- Technik: Migration 0108 (Fremdschlüssel admin_fee_invoice.tenant_id mit ON DELETE RESTRICT), Modelle und Migrationen ohne Abweichung im Autogenerate-Vergleich, Ratenbegrenzung in der Testkonfiguration abgeschaltet und nur im eigenen Test aktiv, Celery-Testisolation (D50)
- Offen: Regel-Engine Stufe 2, Portal Eigentümer (Beschlüsse, Ansprechpartner, Hausgeldkonto), Portalrolle Beirat, Fotoanhang an Portaltickets, CRM-Anzeige der Lesebestätigungen und Pflege des Schwarzen Bretts; Betreiberentscheidungen in docs/OPEN_QUESTIONS.md (unter anderem M10-05, M12-03, M16-14, M7-08, M15-01, M18-01)

## 1.20.1 (26.09.2026) Pflege: Plan-Dokumente, Formatierung, Typprüfung

- Plan-Dokumente M30-sla, M31 und M32: veraltete Abschnitte "Nicht umgesetzt" auf den tatsächlichen Stand gebracht
- Drei ältere Migrationen formatiert, Typfehler in Testdateien behoben, mypy über das ganze Backend ohne Befund

## 1.20.0 (26.09.2026) Übergabeprotokoll, Portal, Belegeingang, Betrieb

- Übergabeprotokoll: Fotos werden beim Hochladen von EXIF- und GPS-Daten befreit und auf höchstens 2000 px Kantenlänge verkleinert (Einstellung handover_image_max_edge); nicht lesbare Bilder werden abgelehnt
- Übergabeprotokoll: Einladungscode für Gehilfen als E-Mail-Entwurf (Vier-Augen-Freigabe, kein Versand) oder als PDF-Anschreiben auf dem Briefbogen; jede Zustellung erzeugt einen neuen Code, aktivierte Zugänge sind gesperrt
- Übergabeprotokoll: Termin anlegen mit Vorbelegung von Titel, Objektadresse als Ort und Beteiligten mit E-Mail als Teilnehmer, danach Link in den Kalender
- Portal: Mitarbeiter mit Portalzugang sehen Übergabeprotokolle ihrer Objekte (GET /portal/handovers), Rollenwechsel in eine ausgenommene Rolle entzieht den Mitarbeiterzugang sofort, Rückwechsel stellt ihn wieder her
- Belegeingang: Mandantenschalter für den automatischen Eingang (Einstellungen, DMS), standardmäßig aus; bei Aktivierung wird je neuem PDF-Anhang mit Rechnungsmerkmal genau eine KI-Extraktion als Vorschlag gestartet, nichts wird gebucht (Migration 0086)
- Tickets: Integrationstest für die Zusammenführung in ein Zielticket; dabei behoben: Zuweiser und Sammelstatus umgingen die Sperre zusammengeführter Tickets, sehr lange Ziffernfolgen in der Suche führten zu einem Datenbankfehler
- Betrieb: Runbook docs/runbooks/server-recovery-und-haertung.md (Zugang wiederherstellen, Ursache prüfen, SSH nur mit Schlüssel, cloud-init stilllegen, Backup) und Skript scripts/server/harden-ssh.sh

## 1.19.0 (26.09.2026) Tickets: Antwortvorlagen, lernende Stammdatenänderung, Links von der Startseite; Belegeingang; Bankkontenauswahl; Mahnwesen je Objekt mit PDF-Entwurf; OpenImmo-Prüfung; objektakte Stufen 4 und 5; Objekt- und Kontaktimport aus Immoware24-Listen; KI-Chat-Fehlerbehandlung

- Tickets: offene Tickets auf der Startseite mit Link ins Ticket; lange Betreffs und Texte laufen nicht mehr über die Seitenbreite hinaus (Ticket #404); Antwortvorlagen mit Platzhaltern (Anrede, Name, Objekt, Einheit, Ticketnummer) und Standardanhängen unter Einstellungen, im Ticket Vorschau, Bearbeiten und Senden zur Vier-Augen-Freigabe, Anhänge werden beim Versand beigefügt
- Tickets lernen: Mails mit Namens- oder Adressänderung (zum Beispiel Kampmeier zu Müller) erzeugen den Vorschlag Stammdatenänderung mit Akzeptieren, Korrigieren, Ablehnen und einem Antwortentwurf; jede Entscheidung fließt als Beispiel in künftige Vorschläge ein; IBAN wird nie vorgeschlagen (Regel M19-05)
- Belegeingang (M14): KI-Extraktion von Rechnungen aus Upload, Mail-Anhang oder Paperless als Entwurf mit Wert, Sicherheit und Quelle je Feld; Maskierung vor dem Anbieteraufruf; Bestätigung legt nur eine offene, ungebuchte Rechnung an; IBAN nur nach ausdrücklicher Bestätigung
- Bankkonten: Auswahlliste je Objekt und Rechtsträger mit Kontostand und letzten Umsätzen, Zuordnung von Konten zu Objekten, Standardkonto je Zweck (Hausgeld, Miete) und je Rechtsträger; WEG-Konten nie für fremde Objekte
- Mahnwesen: Mahnstufen, Mahngrenze, Gebühr und Zins je Objekt mit Vererbung vom Mandanten, Zahlungsfrist und Brieftext je Stufe; Mahnschreiben als PDF-Entwurf nach DIN 5008 mit Ablage als Dokument; Versand bleibt gesperrt (Gate G1)
- Anzeigen: OpenImmo-Export je Anzeige mit Vollständigkeitsprüfung (Adresse, Preis, Fläche, Energieausweis, Kontakt), Exportsperre mit bewusstem Übersteuern, ZIP mit Bildern
- objektakte Stufe 4: Listengenerierung (Anforderungsliste je Objekt, Dokumentenübersicht je Kategorie, CSV-Export), Berechtigungsschlüssel objektakte je Rolle, Benutzerabbildung als Bericht ohne automatische Anlage, Protokoll der KI-Aufrufe je Dokument
- objektakte Stufe 5: Differenzimport aus dem Dump (nur geänderte Zeilen seit dem letzten Lauf, Löschmarkierungen statt Löschung), täglicher Lauf je Mandant abschaltbar, manueller Lauf über die API
- Datenübernahme aus Immoware24-Listen: Befehl für Objekte und Einheiten aus der Objektliste (Verwaltungsart, Gebäude, Lage, Einheitenart abgeleitet, Eigentümer und Mieter nur als Herkunftsnotiz) und Befehl für Kontakte aus den Listen Eigentümer, Mieter, Bank und Sonstige (Rolle aus der Datei, Personen und Firmen getrennt, Telefon und E-Mail geprüft, keine Dubletten über die Immoware24-Nummer); Testlauf ohne Speichern ist Standard; Handbuchkapitel import-objektdaten und import-kontakte
- KI-Chat: Anbieterfehler werden mit Begründung angezeigt und protokolliert (bisher nur HTTP-Code), abgestürzte Läufe gelten nach dem Fehler als fehlgeschlagen statt endlos zu laufen, Zeitlimit von 10 Minuten im Chat, Chip Nur neue nennt die übersprungenen unvollständigen Zeilen; offene Frage M7-07: EU-Endpunkt wird derzeit nicht an den Anbieter übergeben
- Runbook Update einspielen korrigiert: das Produktions-Compose baut keine Images, die drei Images werden mit docker build unter dem Tag aus VERSION gebaut und der Tag in .env.prod gesetzt; exportierte Shell-Variablen überstimmen .env.prod

## 1.18.0 (25.09.2026) Große Sammelversion: Mitarbeiter und Portalrechte, Kalender, Ticketfilter, Open Banking, Mahnwesen, Rechnungseinstellungen, KI-Schnellimport, Immoware-Diagnose, WhatsApp, objektakte

- Mitarbeiter: beim Einladen entsteht automatisch der Kontakt mit Rolle Verwalter und ein sofort aktiver Portalzugang; Portalrechte je CRM-Rolle unter Einstellungen, Rollen einstellbar mit Nachziehen bestehender Zugänge; Löschen nur noch für Administratoren (Regel M2-07)
- Kalender: Termine aus Tickets, Übergabeprotokollen und der Kalenderseite mit Ort und Teilnehmern aus den Kontakten; Einladungen an Externe nur nach ausdrücklicher Bestätigung; Änderungen auf Google-Seite werden angezeigt und nie still überschrieben; Postfächer einmal neu verbinden
- Tickets: Suche über Nummer, Titel, Beschreibung, Kontakt und Adresse, Filter nach Bearbeiter, Objekt, Einheit, Kontaktrolle (Eigentümer, Mieter), Status, Priorität, Kategorie, Team und Zeitraum, Meine Tickets, Filter in der Adresszeile
- Banking: Open Banking über finAPI als Hauptweg für beliebig viele Banken (Bank per IBAN, BIC oder Name, Login im Bankfenster, Konten importieren und Buchungskreisen zuordnen, Umsätze manuell und rückwirkend abrufen, täglicher Abruf je Mandant abschaltbar), Rechnung-zu-Umsatz-Abgleich, Zahlung nur als Vorschlag (Gate G2), Ticket als Rechnung mit Ablage im Drive-Jahresordner, Beleg hinter der Buchung im Portal; finAPI-Einstellungsseite war bisher am Proxy vorbei nicht erreichbar
- Mahnwesen (V7): Vorschlagswerte für die Mahnleiter, Erinnerung kostenlos, Gebühr ab 1. Mahnung nur mit gepflegtem Betrag, Verzugszins nach gesetzlicher Regel nur mit gepflegtem Basiszinssatz, Gebühr als Sollstellung auf dem Debitorenkonto und Rechnungsentwurf der HVM an WEG bzw. Vermieter, Versandmarkierung, Vorbereitung Mahnbescheid (Prüfung durch Rechtsanwalt)
- Rechnungsstellung und Steuer je Mandant: Nummernkreis KUERZEL-JJJJ-000001 lückenlos, Umsatzsteuerstatus, XRechnung nur mit gepflegten Steuerdaten, DATEV-Buchungsstapel-Kopf nur mit Beraterdaten (Kontenzuordnung zu prüfen)
- KI-Import: Tabellen (CSV, Excel) werden deterministisch verarbeitet, die KI liefert nur die Spaltenzuordnung und bearbeitet Restzeilen; 864 Zeilen in Sekunden statt Minuten
- Immoware24: standardbasierte Erkennung von Adressbuch, Kalender und Dokumentwurzel, Diagnose mit Schritttabelle (zeigt, ob das DAV-Modul freigeschaltet ist), Sammelübernahme der Kontakte, Übernahme von Dokumenten einzeln und je Ordner
- WhatsApp als Eskalationskanal (Meta Cloud API, nur freigegebene Vorlagen, Einwilligung für Kontakte, SMS-Rückfall, Zustellstatus per Webhook, Testnachricht); Meta-Konto und Vorlagen sind vom Betreiber einzurichten
- objektakte-Übernahme Stufen 1 bis 3: Datenmodell, Stammdaten- und Dokumentimport aus dem Datenbank-Dump (Drive-Verweise ohne Kopie, OCR-Text per ZIP, IBAN nie im Klartext), Regelklassifikation, KI-Klassifikation mit Maskierung, Review-Center, Vollständigkeitsprüfung mit Nachforderungsentwurf, Menüpunkt Objektakte
- Übergabeprotokoll: Termin anlegen; Portal: Mitarbeiter sehen alle Protokolle; Portal-Anmeldung ohne zweiten Faktor führte in eine Schleife, behoben
- Sicherheit: Review der neuen Endpunkte (docs/reviews), Mitarbeiterzugang nie auf externem Portalkonto, Größenprüfung beim OCR-ZIP, eindeutige Quellkennungen, strengere Rückleitung
- Handbuch (elf Kapitel) und Runbooks (Update einspielen, Ressourcengrenzen); Playwright-Kernpfade mit neuen Rauchtests
- Dashboard: Tagesbalken der Ticketstatistik ordnen Buchungen nach Ortszeit Europa/Berlin zu (bisher nach UTC, dadurch nach 22 Uhr falscher Tag); Schemaabgleich der Tabellen Mahnwesen, Rechnungseinstellungen und Objektakte-Pflichtdokumente
- Tickets: Kontaktrollenfilter erkennt Eigentümer auch über die Objektzuordnung und prüft je Ticket (bisher leer oder zu weit); Dokumentspiegelung bricht bei fehlender Datei nicht mehr für alle Mandanten ab

## 1.17.5 (25.09.2026) SLA: Kanäle je Eskalationsstufe in der Oberfläche

- SLA-Einstellungen: je Regel Tabelle Stufe 1 bis 3 mit Intern, E-Mail und SMS, vorbelegt mit dem Standard (M35), Speichern über die bestehende Regeländerung; Hinweis, dass SMS nur mit aktivem Gateway und Mobilnummer greift
- Korrektur: Bearbeiten einer Regel im Formular setzt channels_by_level nicht mehr auf Standard zurück

## 1.17.4 (25.09.2026) Google-Verbindung ohne Abmeldung

- Google-Verbindung (DMS und Postfächer): die Rückleitung von Google landet auf einer same-site Zwischenseite, damit die Sitzung erhalten bleibt; bisher erschien nach dem Google-Login die Anmeldeseite des CRM, obwohl die Verbindung gespeichert war

## 1.17.3 (25.09.2026) Datenschutz: Ticket-Vorschau lädt nur den Kontaktnamen

- Neuer Endpunkt GET /contacts/{id}/name liefert nur Anzeigename statt des vollständigen Kontakts; die Vorschau beim Zusammenführen von Tickets nutzt ihn (Datenminimierung)

## 1.17.2 (25.09.2026) Worker: KI-Clients sauber schließen

- Die HTTP-Clients der KI-Anbieter (OpenAI, Anthropic) werden nach jedem Anbieterschritt geschlossen. Bisher meldete der Worker nach jedem KI-Lauf "Event loop is closed", weil die SDKs das Schließen erst beim Aufräumen nach Ende der Ereignisschleife anstießen

## 1.17.1 (25.09.2026) KI-Import: parallele Verarbeitung der Teile

- KI: Teile großer Listen werden parallel verarbeitet (vier gleichzeitige Anfragen an den Anbieter statt nacheinander); ein Import mit 11 Teilen braucht damit statt 5 bis 10 Minuten etwa ein Viertel der Zeit. Fortschrittsanzeige und Aufteilung zu großer Teile bleiben erhalten
## 1.17.0 (25.09.2026) Tickets zusammenführen in der Oberfläche

- Tickets: Aktion Zusammenführen im Ticketdetail mit Suche nach Zielticket (Nummer oder Titel), Vorschau beider Tickets und Bestätigung, danach Weiterleitung zum Zielticket
- Tickets: zusammengeführte Quelltickets zeigen einen Hinweis mit Link zum Zielticket und sind für Bearbeitung, Checkliste und Kommentare gesperrt (auch in der API)
- Tickets: Zielticket zeigt Enthält Ticket mit allen Quelltickets
- Ticketliste: zusammengeführte Tickets standardmäßig ausgeblendet, Filter Zusammengeführte anzeigen
- API: Zusammenführen in ein bestehendes Ticket über target_ticket_id; Verlauf des Ziels vermerkt die Herkunft je Quelle mit Anzahl verschobener Einträge
- API: SLA-Uhren der Quelltickets werden erledigt, Zuweiser der Quellen am Ziel ergänzt, Ticketliste mit Suche q, include_merged und merged_into, Ticketdetail mit message_count

## 1.16.0 (25.09.2026) SLA-Eskalation per E-Mail und SMS

- SLA-Eskalation: Kanäle je Stufe (Standard Stufe 1 intern, Stufe 2 intern und E-Mail, Stufe 3 intern, E-Mail und SMS), je Regel über channels_by_level anpassbar
- SLA-Eskalation: E-Mail wird als Systemmail ohne Freigabeprozess über das Standardpostfach versendet (Gmail oder SMTP), mit Objekt, Priorität, Fälligkeit und Link zum Ticket
- SLA-Eskalation: neuer Kanal SMS über ein anbieterneutrales HTTP-Gateway je Mandant, Einstellungen unter SLA, Reiter SMS-Gateway, mit Testnachricht
- Notfallalarme zeigen Zustellung und Fehlerhinweis (delivered_at, delivery_error); fehlt Postfach oder Gateway, wird der Alarm mit Hinweis protokolliert
- Mitglieder: Mobilnummer je Mitglied pflegbar, genutzt für SMS an die Bereitschaft
- Mailversand nach Vier-Augen-Freigabe nutzt denselben gemeinsamen Transport (communication/transport.py); SMTP-Fehler nennen nur noch die Fehlerart

## 1.15.1 (25.09.2026) KI-Chat: Fehlermeldungen mit Schritt und Status

- KI-Chat: Fehlermeldungen nennen jetzt den Schritt (Unterhaltung anlegen, Nachricht senden, Lauf abfragen) und den HTTP-Status, damit Abbrüche wie Datensatz nicht gefunden zuzuordnen sind

## 1.15.0 (25.09.2026) Belegeingang mit KI, OpenImmo, Übergabeprotokoll mit Gehilfen und U-Protokoll-Übernahme

- Belegeingang (M14): KI-Extraktion von Rechnungen als Vorschlag (Aussteller, Nummern, Daten, Beträge, Skonto, Objektbezug) mit serverseitigen Warnungen bei IBAN-Abweichung und Dublette; Übernahme nur als Entwurf mit Vier-Augen-Prüfung, IBAN wird maskiert angezeigt und muss aus dem Original bestätigt werden; Fremdwährung wird gesperrt
- Belegeingang: Erfassung aus Mail-Anhängen (Schaltfläche Als Rechnung erfassen) und aus Paperless per Dokumentnummer; automatische Erfassung bleibt zurückgestellt (M14-05)
- Anzeigen (M26): OpenImmo-Export je Anzeige und als Sammelexport mit vorheriger Vollständigkeitsprüfung, Adresse nur bei Freigabe, kein Portalupload
- Übergabeprotokoll: Objekt und Einheit auch manuell erfassbar (Adresse, Etage, Einheit, externe Objektnummer, Eigentümername), Umschalter Bestand oder manuell
- Übergabeprotokoll: Gehilfenzugang über den bestehenden Portalzugang (Art Gehilfe, Mieter, Eigentümer, 30 Tage gültig), Einladung als Entwurf im Postausgang, Abschluss mit Rückfrage, PDF und Durchschrift an alle Beteiligten als Zustellentwürfe, Verwaltung der Zugänge im CRM
- Übergabeprotokoll: Datenübernahme aus U-Protokoll (MariaDB-Dump mit Vorschau und Übernahme, Dateien per ZIP mit Prüfsummenabgleich), idempotent je Quelldatensatz
- Planung: objektakte wird vollständig ins CRM überführt (docs/plans/M35-objektakte-uebernahme.md, sechs Stufen, offene Entscheidungen M35-01 bis M35-07)

## 1.14.2 (25.09.2026) Mail-Archivierung bei jedem Ticketabschluss

- Tickets: jeder Abschlussstatus (erledigt, abgeschlossen, abgelehnt) archiviert die zugehörigen Mails im Postfach; bisher nur erledigt und abgeschlossen. Die Postfach-Einstellung zur Archivierung bleibt maßgeblich

## 1.14.1 (25.09.2026) Abschaltplan Immoware Hub

- Runbook `docs/runbooks/hub-abschaltung.md`: vierstufige Abschaltung des Immoware Hub mit Rückweg je Schritt, Voraussetzungen, Aufbewahrungsfristen und Hinweis zur Domain mail.mueller-holding.ag
- Zusatzdatei `infra/compose.hub-redirect.yaml`: dauerhafte Weiterleitung der alten Hub-Hostnamen immoware.muellerhv.de und mail.muellerhv.de auf das CRM über Traefik

## 1.14.0 (25.09.2026) KI-Wissensbasis und Mail-Vorbereitung

- KI-Wissensbasis je Mandant und Objekt unter Einstellungen, KI: Ablageregeln, Arbeitsweisen, Fakten und gelernte Korrekturen, filterbar je Objekt
- Mail-Vorbereitung: eingehende Mail wird dem Kontakt, der Einheit und dem Objekt zugeordnet, passende Objektdokumente (z. B. Teilungserklärung) werden gezielt aus Paperless und Google Drive nur im Ordner bzw. unter der Objektnummer des Objekts gesucht, ein Antwortentwurf wird als Vorschlag erzeugt; nichts wird versendet
- Mail: Panel Vorbereitung in der Mail-Ansicht mit Übernehmen (Entwurf) und Korrigieren; Korrekturen werden als gelernte Wissenseinträge gespeichert
- Regel M20-05: Dokumentsuche der KI ist strikt auf das jeweilige Objekt beschränkt, keine Kontoauflistung
## 1.13.0 (25.09.2026) Lernphase Immoware24

- Neue Lernphase (M33) für den Immoware24-Spiegel: WebDAV-, CardDAV- und CalDAV-Läufe erkunden lesend Ordnerstruktur und Feldnutzung der bereits gespiegelten Daten, Übernahme des Moduls Learning aus dem stillgelegten Immoware Hub
- Jeder Lauf vergleicht sich mit dem letzten erfolgreichen Lauf gleicher Art und liefert lesbare Änderungssätze (neue Ordner, neu oder nicht mehr genutzte Felder, geänderte Anzahl gespiegelter Datensätze)
- Neue Seite Immoware24 – Lernphase mit Artauswahl, Lauflisten und Detailansicht der Fakten; Endpunkte `/api/v1/immoware/learning/runs`, kein Schreibpfad Richtung Immoware24

## 1.12.0 (25.09.2026) Portal für Mieter, Eigentümer und Dienstleister

- Portal portal.mueller-holding.ag: Startseite je Rolle nach der Anmeldung; Mieter und Eigentümer sehen Dokumente mit Download, Meldungen mit Verlauf, Foto und Kommentar, Kontoauszug, Zählerstand und Datenänderung; Dienstleister sehen ihre Aufträge mit Ablehnen, Angebot, Termin, Ausführungsbericht und Rechnungseinreichung
- Portal: alle Angaben mit Geld- oder Vertragsbezug sind Vorschläge und werden von der Verwaltung geprüft, nichts wird automatisch übernommen
- Portal: Menü je Rolle, auf Handy und Tablet nutzbar; vertrauenswürdige Geräte gibt es im Portal bewusst nicht, der zweite Faktor bleibt bei jeder Anmeldung

## 1.11.1 (25.09.2026) Immoware24-Kalender werden automatisch erkannt

- Immoware24-Kalender: der Abgleich ermittelt die Kalender unter der eingetragenen Adresse selbst (PROPFIND auf die Kalender-Heimat des Benutzers) und fragt jeden Kalender einzeln ab; eine Heimatadresse wie .../calendars/users/<Login>/ führt nicht mehr zu REPORT 404
- Immoware24-DAV: abgeleitete Adressen für Kalender und Adressbuch nutzen den hinterlegten Login (.../users/<Login>/), wenn keine eigene Adresse eingetragen ist

## 1.11.0 (25.09.2026) Zwei-Faktor für Administratoren, Google-Kalender, Kontakttypen mit SEPA-Mandat, Banking über finAPI, Bearbeiterzuweisung

- Anmeldung: Zwei-Faktor-Pflicht nur noch für Administratoren, vertrauenswürdige Geräte 180 Tage ohne erneuten zweiten Faktor
- Kalender: Google-Kalender je Postfach, Vorgabe ist das Standardpostfach des Mandanten (info@), zusätzlich das dem Benutzer zugewiesene Postfach; Postfächer müssen dafür einmal neu verbunden werden
- Kontakte: Kontakttypen (Eigentümer, Mieter, Verwalter, Dienstleister, Bank, Sonstiges), SEPA-Freigabe je Bankverbindung mit Mandat als PDF oder Erteilung per Telefon, Brief oder E-Mail mit Datum
- Banking: Kontoanbindung über finAPI (Lesezugriff, WebForm) neben dem Dateiupload, Konten werden Objekten und Buchungskreisen zugeordnet; Zahlungsauslösung bleibt hinter Gate G2 gesperrt
- Tickets: automatische Bearbeiterzuweisung nach Postfach, Anrede oder Signatur, Kompetenzen je Benutzer (Katalog unter Einstellungen, Benutzer) und bisheriger Zuordnung; mehrere Bearbeiter je Ticket
- Tickets: Erledigen archiviert die zugehörige Gmail-Nachricht; Tickets werden am Kontakt, Objekt und an der Einheit angezeigt
- Mail: Weiterleitung von Firmenrechnungen (nicht Objektrechnungen) an die Buchhaltungsadresse mit Lernen aus Korrekturen, jede Weiterleitung nur nach Freigabe
- SLA: Schaltfläche Vorschlagswerte laden legt fehlende Regeln je Priorität und den Geschäftszeitenkalender als Vorschlag an (Produktschutz, keine Rechtsvorschrift)
- Oberfläche: Favicon und App-Symbol im CRM

## 1.10.0 (25.09.2026) Tickets mit Sammelstatus und Vorlagen, Start-Auswertungen, Handy-Oberfläche, KI-Stückelung

- Tickets: Sammelauswahl mit Statuswechsel (Mitarbeiter höchstens 10 gleichzeitig, Administratoren unbegrenzt), Ticketvorlagen mit Checklisten und Pflichtfeldern (z. B. IBAN beim Kautionsticket) unter Einstellungen
- Start: Auswertungen mit Kennzahlen und Grafik (Tickets offen, neu und erledigt je Tag, Woche, Monat, Quartal, Jahr), Filter je Benutzer und Vergleich zweier Benutzer
- Menü: Mail und Tickets unter Übersicht, eigene Gruppe Makler (Anzeigen, FLOW-Import, Übergabeprotokoll), WEG-Objekte und WEG-Verwaltung als ein Eintrag, Importassistent ohne Zusatz
- Handy und Tablet: Menü im Vordergrund, Mail-Ansicht ohne seitlichen Überlauf und lesbar auf dem Handy, Chat mit Fortschrittsanzeige und eigener Farbgebung
- KI: Umlaute aus Windows-kodierten CSV-Dateien korrekt, große Listen werden in Teilen verarbeitet statt gesperrt, automatische Wahl des großen Modells bei Umfang, Fortschritt je Teil, Zeichenstatistik je Datei im Lauf
- Buchhaltung: Auswertungen je Buchungskreis (Liquiditätsvorschau 90 Tage, Zahlungen je Debitor, Erträge je Erlöskonto)
- Makler: Anzeigenformulare in Gruppen (Objekt, Adresse und Freigabe, Preise mit Warmmiete, Energieausweis, Ausstattung, Vermarktung)
- Tests: Integrationstests für DMS-Anzeige und Immoware-Spiegel

## 1.9.2 (25.09.2026) OIDC-Anbieter für die Statusseite zusammengeführt

- Das CRM stellt eine OpenID-Connect-Anmeldung für angebundene Dienste bereit, zuerst genutzt von der Statusseite status.mueller-holding.ag
- Zweig für die Statusseiten-Anmeldung in den Hauptstand übernommen, damit spätere Deploys die Funktion behalten (Runbook docs/runbooks/oidc-relying-parties.md)

## 1.9.1 (25.09.2026) Google Drive per OAuth verbinden

- Auf der DMS-Seite verbindet ein Klick auf Mit Google verbinden das Drive-Konto, Client-Secret und Refresh-Token werden automatisch hinterlegt
- Manuelle Eingabe bleibt als Alternative erhalten

## 1.9.0 (25.09.2026) Immoware24-Lesezugriff per DAV

- Neues Paket `mhvp.immoware`: Spiegel von Immoware24 per WebDAV, CardDAV und CalDAV, strikt lesend (kein Schreibpfad, es gibt keine Immoware24-REST-API)
- Anbindung je Tenant mit Verbindungstest (PROPFIND Depth 0), manueller und automatischer Abholung (Celery-Beat alle 15 Minuten, `poll_minutes` je Tenant)
- Dokumentbaum (Ordner und Dateien mit geratener Objektnummer), Adressbuch (Kontakte mit Zuordnung zu oder Anlage als CRM-Kontakt) und Kalender (Termine) als durchsuchbare Spiegeltabellen
- Backend-Endpunkte `/api/v1/immoware/...`; Frontend-Einstellungsseite und Übersichtsseite folgen in einem weiteren Schritt

## 1.8.0 (25.09.2026) Gehilfenzugang für Übergabeprotokolle über das Portal

- Makler, Übergabeprotokolle: Portalzugang je Beteiligtem mit CRM-Kontakt einrichten und beenden; Portalkonto wird bei Bedarf angelegt, Einladungscode einmalig angezeigt
- Portal (apps/web-portal): Anmeldung mit Passwort und zweitem Faktor, Liste der eigenen Übergabeprotokolle, Ausfüllen der Abschnitte, Fotos, Unterschrift, Abschluss; interne Vermerke der Verwaltung bleiben verborgen
- Nach dem Abschluss durch den Beteiligten bleibt das PDF im Portal 14 Tage lesbar, danach erlischt der Zugang; Zustellung weiterhin nur über den Postausgang
- Portal-API `/api/v1/portal/handover`, Regel M30-01 ergänzt, offene Fragen M30-01 (Einladungscode) und M30-05 (zweiter Faktor für Gehilfen)

## 1.7.0 (25.09.2026) Übergabeprotokolle im Bereich Makler

- Neuer Unterpunkt Makler, Übergabeprotokolle: Anlage mit Vorbelegung aus Objekt und Einheit, Beteiligte aus den Kontakten, Zähler, Räume, Mängel, Schlüssel, Gegenstände, Bemerkungen, Fotos und Anhänge als Dokumente
- Unterschriften per Canvas mit Prüfsumme, Hinweise vor dem Abschluss, Abschluss mit PDF auf dem Briefbogen, Festschreibung, neue Versionen ohne Dateiduplikate, Stornierung, Archivierung
- Zustellung an die Beteiligten als E-Mail-Entwurf im Postausgang (Vier-Augen-Freigabe), kein automatischer Versand
- Protokollnummern UP-JJJJMMTT-NNN aus der Nummernfolge je Mandant und Tag
- Migration 0043 (Tabellen handover_*), Regel M30-01, Plan docs/plans/M30-uebergabeprotokoll.md, offene Fragen M30-01 bis M30-04 (Gehilfenzugang über das Portal folgt als Stufe 3)

## 1.6.1 (25.09.2026) Google Drive auf der DMS-Seite einrichtbar

- Google-Drive-Anbindung wird auf der Seite DMS-Anbindung eingerichtet: Wurzelordner, OAuth-Client, Zugangsdaten

## 1.6.0 (25.09.2026) Einstellungsseite DMS-Anbindung

- Neue Einstellungsseite DMS-Anbindung: Paperless-Basis-URL, API-Token und die Feld-IDs Objektnummer und Gesellschaft im Browser pflegbar
- Google Drive wird auf derselben Seite nur lesend angezeigt (aktiv, Basis-URL, Token hinterlegt)
- Karte DMS-Anbindung in den Einstellungen, sichtbar mit dem Recht tenant_settings:update

## 1.5.1 (25.09.2026) Korrektur Migration SLA

- Migration 0042 verwendet den vorhandenen Typ ticket_priority statt ihn erneut anzulegen (Enum sla_alert_channel ebenfalls nur einmal), der Deploy brach bisher mit DuplicateObject ab

## 1.5.0 (25.09.2026) Paperless-Dokumente in Ticket und Objekt

- Abschnitt Dokumente (Paperless) in der Ticketansicht und in der Objektansicht mit Vorschau und Download
- Suche in Paperless über die Objektnummer (Custom Field) und die Ticketnummer im Volltext, Treffer werden zusammengeführt
- Dateien werden über das CRM durchgereicht, der Paperless-Zugang bleibt serverseitig
- Feld-IDs für Objektnummer und Gesellschaft je Mandant in der DMS-Anbindung einstellbar (Optionen object_field_id, company_field_id)
- Versionsnummer im Footer mit Verlauf unter /version
- Plan docs/plans/M31-paperless-view.md, keine Migration

## 1.4.0 (25.09.2026) SLA, Notfallkette und Bereitschaft

- SLA-Regeln je Ticketpriorität mit Reaktions- und Lösungszeit, Uhren laufen nur in der Geschäftszeit
- Arbeitskalender mit Feiertagen, Uhren lassen sich pausieren und fortsetzen
- Eskalationsstufen mit Benachrichtigung an Zuständige und Bereitschaft
- Bereitschaftsplan mit aktueller Bereitschaft und Alarmen zum Quittieren
- Einstellungsseite SLA und Bereitschaft, SLA-Ampel im Ticket
- Erste Antwort per freigegebener Mail stoppt die Reaktionsuhr
- Migration 0042, Plan docs/plans/M30-sla.md

## 1.3.0 (25.09.2026) KI-Vorschläge und Playbooks für Mails

- KI-Antwortvorschlag je eingehender Mail im Ticket
- Playbooks werden aus abgeschlossenen Tickets gelernt und beim nächsten gleichartigen Vorgang angeboten
- Tickets zusammenführen zu einem neuen Ticket mit neuer Nummer, Verlauf bleibt erhalten
- Migrationen 0037 und 0041

## 1.2.1 (24.09.2026) Rückwirkend: Stand vom 24.09.2026 vor Einführung des Versionsverlaufs

- Mietrecht: Regelwerk und Kappungsgebiete NRW, Mieterhöhungsprüfung mit Begründungsmitteln
- Betrieb: Produktivstack auf dem Betreiberserver mit Traefik, Let's Encrypt, Backup-Timer, Wiederherstellungstest, Health-Check, Mehrkern-Einstellungen für API, Celery und PostgreSQL
- Oberfläche: CI der Müller Holding AG, dunkle Seitenleiste mit Icons, Seitenköpfe, Kennzahlen-Kacheln, Anmeldeseite, Dunkelmodus, Bedienung auf Handy und Tablet
- KI: OpenAI als zweiter Anbieter, Anbieterreihenfolge mit automatischem Wechsel, Wiederholung bei Ratenlimit, Chatblase auf jeder Seite mit geführten Importen, Assistent als Protokollseite aller Chats
- Verwaltung: Filter Mietverwaltung, WEG und SEV, Objektebereich, Benutzerverwaltung mit Rollen, Passwort zurücksetzen und Sperren, Benutzermenü, Einstellungen, Mandanten anlegen
- Makler: Anzeigen für Vermietung und Verkauf je Einheit, Felder aus dem FLOW-Datenvertrag, Import des FLOW-Datenbankexports mit Vorschau und Übernahme
- DMS: Bereich mit Absprung in die Objektübernahme je Objektnummer
- Postfach: Gmail-Abruf mit Ticket je Mail, Fehler je Nachricht isoliert

## 1.2.0 (24.09.2026) Postfach im CRM

- Gmail-Abruf je Postfach, jede Mail wird einem Ticket zugeordnet oder eröffnet ein neues
- Google-OAuth-Einstellungen, Standardpostfach und Zugriff je Benutzer
- Mail-Reiter im Ticket mit Vier-Augen-Freigabe vor dem Versand über Gmail
- Fehlerhafte Einzelmails brechen den Abruf nicht mehr ab und werden gemeldet
- Migrationen 0035, 0036, 0039, 0040

## 1.1.0 (24.09.2026) Makler, DMS-Bereich und neue Oberfläche

- Maklerbereich mit Miet- und Kaufangeboten, Felder nach FLOW-Datenvertrag, FLOW-Import
- DMS-Bereich mit Anbindung der Objektübernahme (objektakte)
- Überarbeitetes Design mit dunkler Navigationsleiste, Seitenköpfen und Dashboard-Kacheln, mobile Ansicht
- Einstellungsbereich mit Benutzerverwaltung, Rollen, Mandant, Profil
- KI-Assistent auf jeder Seite mit Seitenkontext, Auswertung aller Chats für Revisionsleser
- Mehrkern-Auslegung für API, Celery und PostgreSQL im Produktivbetrieb

## 1.0.0 (23.09.2026) Marktreife der Grundplattform

- Mandantenfähige Plattform mit Rollen, Rechten und Revisionsprotokoll (M1, M2)
- Kontakte, Objekte, Einheiten, Verträge (M3 bis M5)
- Dokumente mit Aufbewahrung, DMS-Spiegel (Paperless, Google Drive), Briefe und Serienbriefe (M6)
- KI-Gateway, Onboarding-Chat, Immoware24-Import, Oberfläche und Betrieb (M7 bis M9)
- Buchungskreis, Bankanbindung, Matching mit KI-Kontierung, Sollstellung, Verwalterhonorar (M10 bis M13)
- Belegeingang, Kreditoren, Zahlläufe, Mahnwesen, Mietabrechnung, Auswertungen und Exporte (M14 bis M18)
- Tickets und Aufträge, Postfach, Portale für Mieter, Eigentümer und Dienstleister, Kommunikation (M19 bis M23)
- WEG-Wirtschaftsplan und Abrechnung, Versammlung, Beiratsprüfung, Mieterhöhung und Vermietung, Marktreife (M24 bis M27)
