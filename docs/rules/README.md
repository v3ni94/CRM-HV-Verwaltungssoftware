# Domain rule registry

Rule 0.1.11 of `docs/MASTER-PROMPT.md`: every new or changed domain rule gets an ID, scope,
source status, acceptance case and change reason. No contradicting parallel rule sets: the
master prompt text is authoritative; this registry records implementation status and
evidence. Legal sources come only from annex C (never invent norms); open source gaps are
P01 to P05 in `docs/OPEN_QUESTIONS.md`.

## Entry format

Each implemented rule gets its own file `docs/rules/<ID>.md` with:

| Field | Content |
| --- | --- |
| ID | e.g. `B08` |
| Title | German title from the master prompt |
| Scope | legal entity kinds, contract types, periods, tenants, excluded special cases |
| Source status | annex C entry (R.. / P..), retrieval date, validity from/to, responsible person, release status |
| Acceptance case | annex D case IDs (e.g. D05) and test paths |
| Implementation | modules, migrations, rule version |
| Change reason | why the rule was added or changed, with date and approver |

## Index

Status values: `specified, not implemented`, `implemented, not accepted`, `accepted`
(acceptance per annex D.3), `superseded`. Titles are the German titles of the master prompt.

| ID | Title | Master prompt section | Status |
| --- | --- | --- | --- |
| [M2-02](M2-02.md) | Freigabestufen: Vier-Augen-Prinzip und Superadmin-Umgehung nur hinter Plattformschalter (ADR 0011) | M2, 18.0 | implemented, not accepted |
| [M2-01](M2-01.md) | Passwortregel und Kontosperre, zweiter Faktor freiwillig, gemerkte Geräte 90 Tage | M2, 3.4 | implemented, not accepted |
| [M2-05](M2-05.md) | Mandantenübergreifende Arbeitssicht, nur lesend, je Mandant getrennt (RLS), Schreiben nur nach Mandantenwechsel | M2, 5.3, ADR 0002, ADR 0011 | implemented, not accepted |
| [M2-07](M2-07.md) | Löschen nur Administrator | M2 | implemented, not accepted |
| [M4-05](M4-05-objekt-deaktivieren.md) | Objekt deaktivieren bei Beendigung des Verwaltungsverhältnisses, Reaktivierung nur durch den Superadmin | M4, 6.2 | implemented, not accepted |
| [M10-01](M10-01-kontenrahmen-vorlage.md) | Kontenrahmen-Vorlage nach Anhang A.1 mit vorgeschlagenen Erlöskonten der Mietverwaltung (`review_status = "entwurf"`, Freigabe durch Steuerberatung offen) | M10, 7.2, A.1, G1 | implemented, not accepted (Offene Entscheidung V8; Freigabeworkflow seit 27.09.2026, Nachtrag) |
| [M10-02](M10-02-kostenkonten-vorbelegung.md) | Kostenkonten der Vorlage als Entwurf nach BetrKV vorbelegt (umlagefähig mit üblichem Schlüssel, sonst nicht umlagefähig, Umsatzsteueroption offen), Seed füllt nur unbesetzte Felder | M10, 7.2, A.1, A.2 | implemented, not accepted (Offene Entscheidung mit Steuerberatung) |
| [M8-04](M8-04-mehrpersonen-bevollmaechtigte.md) | Mehrpersonen-Parteien aus dem Adressbuch als eine Partei mit Mitgliedern, unklare Fälle zur Prüfung; Bevollmächtigte mit Zustellregel für Versand, Serienbriefe und WEG-Einladungen | M8, M3, M23, 6.1 | implemented, not accepted |
| [M12-01](M12-01-kontierung-zwei-stufen.md) | Kontierung in zwei Stufen: deterministisch (Regel, Mandat, Vertrags- oder Rechnungsnummer, IBAN, Betrag) immer aktiv, KI nur als freigegebener Vorschlag, nie automatische Buchung | M12, 7.4, 9.2 | implemented, not accepted (Nachtrag 27.09.2026, KI-Stufe hinter Mandantenschalter, AVV offen) |
| [M12-04](M12-04-lernender-buchhalter.md) | Lernender Buchhalter: Vorschlags- und Entscheidungsprotokoll je Bankumsatz (unveränderlich, Mandantenschalter Standard aus), Storno-Grundcode, Regel-Lebenszyklus-Ereignisse; bucht nichts, öffnet kein Gate (ADR 0013, Fahrplan S0 und S1) | M12, 7.4, 6.9.4, B03 | implemented, not accepted (Datenschutzprüfung M12-06 vor Aktivierung offen) |
| [M13-01](M13-01.md) | Zeitanteilige Sollstellung bei Beginn, Ende oder Betragswechsel im Monat | M13, 7.5 | implemented, not accepted (Entwurf, Feature-Flag je Mandant, G1) |
| [M13-02](M13-02.md) | Nicht monatliche Zahlweisen und Fälligkeitsermittlung | M13, 7.5 | implemented, not accepted (Entwurf, Feature-Flag je Mandant, G1) |
| [M13-03](M13-03.md) | Umsatzsteuer auf Sollstellungen bei gewerblicher Vermietung mit Option | M13, 7.5, 7.7 | implemented, not accepted (Entwurf, Feature-Flag je Mandant, G1) |
| [M13-04](M13-04.md) | XRechnung für Verwalterhonorar-Rechnungen nur aus eingetragenen Mandantendaten | M13, 13.5 | implemented, not accepted |
| [M16-01](M16-01.md) | Mahngebühr nur mit hinterlegtem Betrag, Rechnung an Gemeinschaft nur mit vertraglicher Grundlage | M16 | implemented, not accepted |
| [M16-02](M16-02.md) | Mahnstufen je Objekt erben vom Mandanten, Mahnschreiben nur als Entwurf | M16 | implemented, not accepted |
| [M16-03](M16-03.md) | Fälligkeit und Verzug getrennt: Verzugsbeginn je Modus nur aus erfassten Tatsachen, Zinsen nur als Entwurf, Verbraucherkennzeichen am Kontakt | M16, 7.5, R10 | implemented, not accepted, zu prüfen durch Rechtsanwalt |
| [M16-13](M16-13.md) | Bankverbindung im Mahnschreiben: Standardkonto des Rechtsträgers, dem die Forderung gehört, vollständige IBAN, ohne Konto kein Schreiben | M16, 6.9.1 | implemented, not accepted |
| [M17-01](M17-01-betrkv-katalog.md) | Umlagefähigkeit je Kostenposition: Systemkatalog der Betriebskostenarten nach BetrKV, Kontenzuordnung, Prüfhinweis in der Vorschau | M17, 7.6 A02/A03 | implemented, not accepted (Entwurf, Freigabe Rechtsberatung offen) |
| [M17-03](M17-03-vorschussregel.md) | Vorschussregel: Vorjahresergebnis geteilt durch zwölf, optional Sicherheitsaufschlag, Vorschlag mit Bestätigung und Textbaustein | M17, 7.6 A04/A07 | implemented, not accepted (Offene Entscheidung Betreiber) |
| [M17-05](M17-05-eigentuemerabrechnung-ausgabe.md) | Eigentümerabrechnung Miete und SEV als PDF-Entwurf je Objekt mit Auszahlungsbetrag über die Briefbausteine | M17, 7.6 A06 | implemented, not accepted (Ausgabe hinter G3) |
| [M15-01](M15-01-pain-versions.md) | Zahlungsdatei pain.001 in der je Bank konfigurierten Version (03/09), XSD-Prüfung im Test, Prüfsumme, Download-Protokoll, Einreichung nur manuell bestätigt | M15, 7.5, Kapitel 8 Zahlläufe | implemented, not accepted (Bankbestätigung offen) |
| [M15-02](M15-02-pain008.md) | SEPA-Basislastschrift pain.008: Mandatsprüfung, Sequenz, Vier-Augen, Datei nur hinter G2 | M15, 7.5 SEPA | implemented, not accepted |
| [M18-02](M18-02-pruefexport.md) | Prüfexport: maschinell auswertbar im Umfang von Abschnitt 7.7, kein Datenträgerüberlassungsformat | M18, 7.7, D55 | implemented, not accepted |
| [M18-03](M18-03.md) | DATEV-Buchungsstapel: EXTF-Header nur mit Beraterdaten, keine erfundene Kontenzuordnung | M18 | implemented, not accepted |
| [M18-04](M18-04-datev-kontenzuordnung.md) | DATEV-Kontenzuordnung je Mandant: Betreiberpflege ohne vorbelegten Kontenrahmen, Export nur mit vollständiger Zuordnung (MHVP-BILL-0008) | M18, A36 | implemented, not accepted |
| [M18-05](M18-05-steuerberaterzugang.md) | Steuerberaterzugang: Zugriffsbereich je Rechtsträger (`membership.legal_entity_ids`), leerer Bereich bedeutet kein Zugriff, fremde Rechtsträger 404 | M18, M18-02, A37 | implemented, not accepted |
| [M18-06](M18-06-datev-formatpruefung.md) | DATEV-Buchungsstapel: formale Selbstprüfung (Regeln DC-01 bis DC-22 mit Quellenstatus belegt oder zu prüfen), gespeicherte Exportdatei, Prüfbericht JSON/Text, Testdatei für den Importtest | M18, M18-03, M18-04 | implemented, not accepted (Importtest beim Steuerberater offen) |
| [M26-RL](M26-rent-law.md) | Mieterhöhung Regelwerk | 8, M26 | implemented, not accepted |
| [M27-01](M27-01.md) | Preisstruktur ohne Beträge (Stufen, Zusatzmodule, Testphase), Angebot nur als PDF-Entwurf | M27, 18, 6.8 | implemented, not accepted (Offene Entscheidung M27-01) |
| [M27-02](M27-02.md) | Freigabe G5: Nachweisliste je Mandant, Gate nur mit allen Nachweisen und Superadmin | M27, 18.0, ADR 0003 | implemented, not accepted |
| [M27-03](M27-03.md) | Onboarding Drittmandanten (Rechtsträger, Administrator, CI, Flags aus, E-Mail-Entwurf) und Mandanten-Export im Vier-Augen-Prinzip | M27, 18, 5.3 | implemented, not accepted |
| [UI-BANK-01](UI-BANK-01-bankoberflaeche.md) | Bankoberfläche im CRM: Buchungsdialog (freie Posten, Teilbeträge, Splits, Gegenkonto ohne Bank-, System- und inaktive Konten, Ausgänge, Transferpaare), Dublettenklärung, Massenbestätigung nur mit Vorschau und geprüften Vorschlägen, MT940- und CSV-Upload, Bankabstimmung B09, Bankregeln im Vier-Augen-Lebenszyklus, Automatikschalter nur lesend | 7.4, 7.1 B02/B03/B08/B09, 6.9.4, D04, D07, D51 | implemented, not accepted (BK-2, Plan M12 S2, 28.09.2026) |
| [M28-01](M28-01.md) | Makler: Anzeigen, keine FLOWFACT-Anbindung | M28 | implemented, not accepted |
| [M26-02](M26-02.md) | OpenImmo-Export: Format-Mapping, nur lesend, kein Portal-Upload | M26 | implemented, not accepted |
| [M30-01](M30-01.md) | Übergabeprotokoll: Festschreibung, Versionen, Zustellung | M30 | implemented, not accepted |
| [M30-06](M30-06.md) | Übergabeprotokoll: Gehilfenzugang, Sichtbarkeit und Ablauf | M30 | implemented, not accepted |
| [M30-07](M30-07.md) | Übergabeprotokoll: Vertragsverknüpfung und Übernahme der Zählerstände | M30 | implemented, not accepted |
| [M11-finapi-dedup](M11-finapi-dedup.md) | finAPI Umsatzabgleich (Bankreferenz vorrangig, D05) | M11 | implemented, not accepted |
| [M11-finapi-authorization](M11-finapi-authorization.md) | finAPI: Recht `banking:approve`, unzugeordnete Konten verborgen | M11 | implemented, not accepted |
| [M11-05](M11-05-credentials-never-in-crm.md) | Zugangsdaten nie im CRM (Bank-WebForm) | M11 | implemented, not accepted |
| [M11-07](M11-07-fints-pin-tan.md) | FinTS PIN/TAN: Zugangsdaten verschlüsselt, keine Wiederholung nach Fehlversuch, 90 Tage, nur lesend | M11 | implemented, not accepted |
| [AI-LOOKUP-01](AI-LOOKUP-01.md) | KI-Assistent: Antworten aus Plattformdaten nur über berechtigungsgeprüfte Abfragen, Links nur von der Plattform, Änderungen nur als Vorschlag | 9, 10 | implemented, not accepted |
| [INT-SDT-01](INT-SDT-01-schadenbearbeiter.md) | Schadenbearbeiter: Austausch nur nach AVV, nur ausdrücklich gewählte Inhalte, Übernahme nur nach Bestätigung | Integrationen | implemented, not accepted |
| [INT-LEXO-01](INT-LEXO-01-lexware-office.md) | Lexware Office: Organisation je Gesellschaft nur nach AVV und Verbindungstest, Stammdaten nur nach Personenentscheidung in eine Richtung ohne Bankdaten, Rechnungskopien nur an den bekannten Empfänger mit zweiter Freigabe, Entwürfe ohne finalize, Dauerrechnungen nur vorbereitet | Integrationen, Betreiberauftrag 28.09.2026 | implemented, not accepted (Migration 0233; Freigabe ADR 0013 offen) |
| [M10-03](M10-03-tilgungsfolge-vorschlag.md) | Ausgleich offener Posten nach gesetzlicher Reihenfolge, nur Vorschlag mit Bestätigung (Tilgungsfolge, D39) | M10, 7.4 Nr. 5 | implemented, not accepted |
| [M11-06](M11-06-payment-proposal-only-until-g2.md) | Zahlung nur Vorschlag bis G2 (Rechnungsabgleich) | M11, 18.0 | implemented, not accepted |
| [M14-02](M14-02.md) | Vorsteuer: getrennte Erfassung, Abzug nur als Vorschlag bei optierten Objekten nach Umsatzschlüssel, Schalter Standard aus | M14, 7.2, PÜ03 | implemented, not accepted (zu prüfen durch Steuerberater) |
| [M14-03](M14-03.md) | Freigabegrenzen je Rolle: zweite Freigabe durch dritte Person über der Grenze (Produktschutz) | M14, 6.9.9 | implemented, not accepted |
| [M14-04](M14-04.md) | Reverse Charge, Bauabzugsteuer (Warnung, Einbehalt nur Vorschlag), § 35a Kennzeichen je Position und Ausweis als PDF-Entwurf | M14, M17, PÜ03 | implemented, not accepted (zu prüfen durch Steuerberater) |
| [M3-02](M3-02-sepa-mandate.md) | SEPA-Mandat auf der Bankverbindung des Kontakts; Portalstufe: digitales Mandat als Vorschlag mit Textform-Nachweis | M3, 6.1, 14 | implemented, not accepted |
| [M20-05](M20-05.md) | Mail-Vorbereitung: Dokumentsuche strikt je Objekt, keine Kontoauflistung | M20, M34, 11.2 | implemented, not accepted |
| [M19-05](M19-05.md) | Stammdatenänderung aus einer Ticket-Mail: nur Vorschlag, Entscheidung durch Menschen, nie IBAN | M19, M20, 9.1 | implemented, not accepted |
| [M23-05](M23-05.md) | Google-Kalender: Einladungen nur nach Bestätigung, kein stiller externer Überschreib | M23 | implemented, not accepted |
| [M23-01](M23-01.md) | Brief- und Postversand mit Statusrückmeldung: anbieterneutrale Schnittstelle, Postausgangsliste, LetterXpress-Adapter, kein Versand ohne Freigabe je Mandant, Zugang nur mit Nachweis, Mahnfall erhält Zugangsnachweis | M23, M16 | implemented, not accepted |
| [M35-01](M35-01.md) | objektakte-Übernahme: Quellkennung und IBAN-Regel | M35 | implemented, not accepted |
| [M35-02](M35-02.md) | objektakte-Übernahme: Klassifikation Stufe 1 (Regeln) | M35 | implemented, not accepted |
| [M35-03](M35-03.md) | objektakte-Übernahme Stufe 4: Berechtigungsschlüssel `objektakte:*`, Benutzerabbildung nur als Vorschlag, KI-Protokoll nur lesend | M35 | implemented, not accepted |
| [M21-02](M21-02.md) | Adressänderung aus dem Portal mit Gültigkeitsdatum und Nachweis, Übernahme nur durch Entscheidung im CRM | M21, 14 | implemented, not accepted |
| [M21-03](M21-03.md) | Freigabeflag je Dokument: intern, Eigentümer, Mieter, Dienstleister, Beirat | M21, M6, 6.9.6, 14 | implemented, not accepted |
| [M21-05](M21-05.md) | WhatsApp nur mit freigegebenen Vorlagen und Einwilligung | M21 | implemented, not accepted |
| [M21-06](M21-06.md) | Zugriffsmatrix auf jedem Pfad: GdWE-Einsicht, fremde Akten, KI-Kontext, freigegebene Fassung (D29 bis D31) | M21, M6, M7, 6.9.6, 14, E06 | implemented, not accepted |
| [M21-07](M21-07.md) | Prüfungsraum Beirat: Portalrolle `board` je Prüfauftrag, nur Lesen und Vermerk, keine Buchung oder Freigabe, Belege nur aus Prüfpositionen (PÜ07, PÜ08) | M21, M25, 7.9.2, 14, D32, D33 | implemented, not accepted |
| [M19-02](M19-02-ticket-templates.md) | Ticketvorlagen mit Checkliste und Pflichtfeldern (inkl. IBAN), Sammelstatuswechsel | M19, 6.6 | implemented, not accepted |
| [M25-01](M25-01-mehrheitsregeln.md) | Mehrheitsregeln je Beschlussgegenstand: Prüfung "erreicht / nicht erreicht / nicht prüfbar" ohne Statusänderung, Freigabe durch zweite Person | M25, 6.9.12, W13 | implemented, not accepted |
| [M25-02](M25-02-umlaufbeschluss.md) | Umlaufbeschluss mit abgesenkter Mehrheit nach zulassendem Beschluss: Schalter je Mandant, Pflichtverweis auf den Beschluss, Zählung nach Mehrheitsregel des Mandanten, Frist und Textform-Nachweis, Feststellung als Protokollvermerk; Rechtsgrundlage zu prüfen durch Rechtsanwalt | M25, W13 | implemented, not accepted, legal review open |
| [M25-03](M25-03-einladung-virtuell.md) | Einladungsfrist je Mandant mit spätestem Versanddatum, Warnung und Grund bei Unterschreitung, Protokollvermerk, Kalendereintrag; virtuelle Versammlung nur mit Schalter je Mandant und zulassendem Beschluss mit Gültigkeitsende, Einwahldaten nur für Eigentümer im Portal, Teilnahmenachweis mit Kanal; Rechtsgrundlage zu prüfen durch Rechtsanwalt | M25, W13, V13 | implemented, not accepted, legal review open |
| [M9-02](M9-02-automation.md) | Regel-Engine Stufe 1 und 2: Ticket, Benachrichtigung, Ticketfeld, Webhook (signiert), Mail- und Briefentwurf, KI-Aufgabe; Zeitplan als Auslöser; Tiefe 1, Testlauf ohne Wirkung | M9, 15.2 | implemented, not accepted |
| [M9-11](M9-11-lern-workflow.md) | Lern-Workflow: Regelvorschlag nach wiederholter gleicher manueller Zuordnung je Absender (Standard 5), aktiv nur nach ausdrücklicher Annahme, nie für Zahlungsempfänger, IBAN, Beschlüsse, Gebühren oder Steuer (Produktschutz) | M9, 15.2, 0.1.6 | implemented, not accepted |
| [M7-06](M7-06.md) | Tabellenimport deterministisch, KI nur für Spaltenzuordnung und Restzeilen | M7 | implemented, not accepted |
| [B01](B01.md) | Richtiger Rechtsträger | 7.1 | implemented, not accepted |
| [B02](B02.md) | Entwurf und Buchung | 7.1 | implemented, not accepted |
| [B03](B03.md) | Korrektur statt Überschreiben | 7.1 | implemented, not accepted |
| [B04](B04.md) | Eindeutige Nummern | 7.1 | implemented, not accepted |
| B05 | Belegkette | 7.1 | specified, not implemented |
| [B06](D08-rest-cents.md) | Präzision | 7.1 | implemented, not accepted (M17, D08 tested) |
| [B07](B07.md) | Stichtagswahrheit | 7.1 | implemented, not accepted |
| [B08](B08.md) | Keine doppelte wirtschaftliche Wirkung (Transferpaar D04 seit 28.09.2026) | 7.1 | implemented, not accepted |
| [B09](B09.md) | Abstimmung | 7.1 | implemented, not accepted |
| A01 | Ergebnisstand | 7.6 | implemented, not accepted (M17, rule version by period start in `statement_snapshot.rule_version`, D28 tested; document version and difference report open) |
| A02 | Betriebskosten Miete | 7.6 | implemented, not accepted (M17, `test_m17_operating_costs.py`; D22: account allocation category and posted split are checked, cost type schema stays M17-01) |
| A03 | Schlüssel | 7.6 | implemented, not accepted (M17, time weighted keys; D21: SEV refuses template keys, key source in position basis, key facts in the snapshot) |
| A04 | Vorauszahlungen und Fristen | 7.6 | implemented, not accepted (M17, advances and deadline orientation; D23: access day checked at issue, never the calculation day) |
| A05 | Nutzerwechsel, Leerstand, Heizkosten | 7.6 | implemented, not accepted (M17, vacancy share to owner, heating external only) |
| [A06](A06-owner-statement.md) | Eigentümerabrechnung Miete/SEV | 7.6 | implemented, not accepted (M17 task A25, `mhvp.billing.owner_statement`, `test_m17_owner_statement.py`; PDF behind G3) |
| A07 | Bedienung | 7.6 | specified, not implemented |
| W01 | Eigene Gemeinschaft | 7.8 | implemented (M24), ledger check |
| W02 | Wirtschaftsplan | 7.8 | implemented (M24), behind G4 |
| [W03](W03-cost-allocation.md) | Kostenverteilung | 7.8 | implemented, not accepted (M24, `mhvp.hoa.calc.unit_weights`; D18 partial scope check in `mhvp.hoa.package`) |
| [W04](W04-cash-flow-reconciliation.md) | Jahresabrechnung als nachvollziehbare Überleitung | 7.8 | implemented, not accepted (A60: Gesamtgeldfluss and bridge in `mhvp.hoa.calc.cash_flow_reconciliation`, unexplained difference blocks the package; migration year open) |
| W05 | Abrechnungsspitze und Rückstände | 7.8 | implemented (M24), [W05](W05-hoa-result.md) |
| W06 | Beschluss und Buchung | 7.8 | implemented (M24), [W06](W06-resolution.md); D54 contested resolution locks the posting, reverses nothing |
| W07 | Eigentümerwechsel | 7.8 | open, M24-01 |
| W08 | Erhaltungsrücklagen | 7.8 | implemented (M24), D03 and D19 tested (bank balance shown apart, no settlement entry) |
| W09 | Sonderumlagen und Maßnahmen | 7.8 | implemented, not accepted (special levy and amendments per W09-01, D20 partial refund, `test_w09_special_levy.py`) |
| [W10](W10-loans-insurance-measures.md) | Darlehen, Versicherungen, größere Maßnahmen | 7.8 | implemented, not accepted (A59: `mhvp.hoa.finance`, items only with journal entry reference; treatment in the statement open, M24-03) |
| W11 | Vermögensbericht | 7.8 | implemented, not accepted ([M24-02](M24-02-vermoegensbericht.md): `mhvp.hoa.assets`, report per date with reconciliation and PDF draft behind G4); structure open, M24-02 |
| W12 | Abrechnungspaket | 7.8 | implemented, not accepted (package and blocking checks, `test_w09_special_levy.py::test_w12_package_blocks_release`) |
| W13 | Beirat und Versammlung | 7.8 | implemented, not accepted (M25); majority rules per subject kind since 26.09.2026, see [M25-01](M25-01-mehrheitsregeln.md); minutes draft A62 |
| PÜ01 | Vollständigkeit | 7.9.1 | implemented, not accepted (M14 findings; recipient and reference hints, `test_pue_invoice_checks.py`) |
| PÜ02 | Sachliche Prüfung | 7.9.1 | partly implemented (factual review step M14, missing reference hint); order/budget match open |
| PÜ03 | Rechnerische/steuerliche Prüfung | 7.9.1 | implemented, not accepted (M14 arithmetic findings and review step) |
| PÜ04 | Dubletten/Betrugsrisiko | 7.9.1 | implemented, not accepted (number, amount and day, same document, IBAN confirmation) |
| PÜ05 | Prüfentscheidungen | 7.9.1 | implemented, not accepted (M14 review steps per version, four eyes release) |
| PÜ06 | Prüfauftrag | 7.9.2 | implemented, not accepted (M25, audit engagement) |
| PÜ07 | Nachvollziehbare Navigation | 7.9.2 | partly implemented (M25, items link entries and documents) |
| PÜ08 | Prüfen und nachfordern | 7.9.2 | implemented, not accepted (M25, note, question, answer, outdated on new version) |
| PÜ09 | Aussagekräftiger Abschlussbericht | 7.9.2 | implemented, not accepted (M25, versioned report) |
| PÜ10 | Eigentümer | 7.9.3 | implemented, not accepted (M21 access matrix) |
| PÜ11 | Mieter | 7.9.3 | implemented, not accepted (M21 access matrix) |
| PÜ12 | Praktischer Zugang | 7.9.3 | specified, not implemented |
| PÜ13 | Protokoll ohne Rechtsfiktion | 7.9.3 | partly implemented (M21, M23 logs); request log open, M25-04 |
| H01 | Messdienst oder Eigenberechnung | 7.10 | implemented, not accepted (M17, external heating statement required) |
| H02 | HeizkostenV | 7.10 | specified, not implemented |
| H03 | Laufende Pflichten | 7.10 | specified, not implemented |
| [H04](H04-co2.md) | CO₂-Regeln mit Geltungsstand | 7.10 | implemented, not accepted (M17, CO₂ split) |
| [M17-02](M17-02-heizkosten.md) | Heizkostenabrechnung als Entwurf (H02, H04, D25 bis D27) | 7.10 | implemented, not accepted (M17-02, 27.09.2026; Werte als Konfiguration zu prüfen, Ausgabe hinter G3) |
| H05 | Bereits veröffentlichte spätere Regeln | 7.10 | specified, not implemented |
| H06 | § 35a | 7.10 | specified, not implemented |
| S01 | Steuerlicher Kontext | 7.11 | specified, not implemented |
| S02 | E-Rechnung | 7.11 | specified, not implemented |
| S03 | Original und Verarbeitung | 7.11 | specified, not implemented |
| S04 | Differenzierte Fristen | 7.11 | specified, not implemented |
| S05 | WEG-Dauerunterlagen, Sperren und Löschung | 7.11 | specified, not implemented |
| S06 | Datenschutz und Auskunft | 7.11 | specified, not implemented |
| [A07-tenant-letters](A07-tenant-letters.md) | Bedienung: Anschreiben Guthaben/Nachzahlung und Vorauszahlungsvorschlag je Mieter | 7.6 A07 | implemented, not accepted |
| [M9-06](M9-06-tagesjobs.md) | Tagesjobs Tagesübersicht und Fristenliste: Orientierung, Vorfrist aus Einstellungen, keine Rechtsfristen | M9, 15.1 | implemented, not accepted |
| [A61](A61-einsicht.md) | Einsichtsanfragen außerhalb des Portals protokollieren | 14, M25 (PÜ12, PÜ13) | implemented, not accepted |
| [M19-06](M19-06-tnr.md) | Ticketnummer im Betreff (TNR#<nummer>), Zuordnung eingehender Mails nur bei bekanntem Absender, Wiedereröffnung, Postfachzugriff je Mail | M19, M20, 6.6 | implemented, not accepted |
| [M19-07](M19-07-erledigungsnotiz.md) | Erledigungsnotiz beim Abschluss (Artenliste je Mandant: eingebaute Arten abschaltbar, eigene Arten, plus Freitext, auch Bulk und Zusammenführen), Lernbeispiel je Abschluss ohne KI-Lauf, Hinweis "Bei ähnlichen Vorgängen wurde" | M19, M20, 6.6, 9.1 | implemented, not accepted (1.24.0, Migrationen 0130 und 0136; M19-04 entschieden 26.09.2026; Datenschutz M7-04 offen) |
| [M19-08](M19-08-anrufassistenz.md) | Anruf-Mails der Telefonassistenz (Hallo Heidi): deterministische Erkennung und Zuordnung, KI füllt nur Lücken, neue Rufnummer nur als Vorschlag mit Antwortentwurf, kein Versand | M19, M20, 9.1, 13.5 | implemented, not accepted (1.24.0, Migration 0131; M19-03 offen) |
| [M19-09](M19-09-erledigte-ausgeblendet.md) | Erledigte Vorgänge in Ticket- und Mailübersicht standardmäßig ausgeblendet (`include_closed`), Administratoren setzen jeden Status (`admin_override`), Abschlussprüfungen bleiben | M19, M20, 6.6 | implemented, not accepted (1.23.0 und 1.24.0) |
| [M19-10](M19-10-folgevorgang.md) | Neue Mail zu einem abgeschlossenen Ticket: Wiedereröffnung nur bis `ticket_reopen_window_days` Kalendertage nach dem Abschluss (Standard 30, je Mandant), danach Folgeticket mit Verweis, Vorbelegung von Objekt, Einheit und Kontakt und Hinweis in beiden Tickets; automatische Antworten öffnen nie wieder | M19, M20, 6.6 | implemented, not accepted (Migrationen 0219 und 0221; Betreiberentscheidung 28.09.2026 durch den Lead; Zusammenführen mit Folgetickets seit Review 1.40.2) |
| [M6-03](M6-03-loeschung-spiegel.md) | Löschung gespiegelter Dokumente: Drive-Kopie löschen (endgültig, ersatzweise Papierkorb, vermerkt), Paperless-Dokument behalten und mit "gelöscht" kennzeichnen, beide Schritte protokolliert, Löschung "offen" bis beide Schritte gelungen sind, Wiederholung per Task, erneutes Anstoßen per API | 6.9.5, D46, D47, V17 | implemented, not accepted (Migration 0143; Betreiberentscheidung 26.09.2026) |
| [M6-04](M6-04-aufbewahrungsprofile.md) | Standard-Aufbewahrungsprofile je Mandant als Entwurf ("Entwurf, Prüfung Steuerberatung offen"), Seed idempotent ohne Überschreiben, Löschung bleibt bis zur Freigabe gesperrt, Freigabe je Mandant mit `tenant_settings:update`, Vier-Augen und Protokoll. Nachtrag 27.09.2026: Kategoriezuordnung, Fristberechnung nach Startregel, Sperre je Vorgang, monatlicher Löschvorschlagslauf mit Vier-Augen-Freigabe und getrennter Ausführung, Löschprotokoll, Spiegellöschung nach M6-03 | 6.9.5, S04, S05, V17 | implemented, not accepted (Migrationen 0139, 0175; Quellenstatus zu prüfen durch Steuerberater) |
| [M5-02](M5-02-kautionsabrechnung.md) | Kaution: getrennte Verwahrung, Verzinsung je Jahr als Bewegung, Kautionsabrechnung bei Vertragsende als Entwurf mit Zinsart (individuell je Jahr, Referenzzinssatz je Jahr, keine), Freigabe hinter G3 | M5, 6.9.1, D56, 7.1 B01 | implemented, not accepted (Migration 0138; Zinssatz rechtlich zu bestätigen, Betreiberentscheidung 26.09.2026) |
| [M5-03](M5-03-eigentuemerwechsel-sollbetraege.md) | Eigentümerwechsel als Dialog auf Vertrags- und Einheitenseite mit Vorschau; Übernahme der am Übergang gültigen Sollbeträge, des Zahlungsplans und der Umlagewerte als tatsächliche Kopie ab dem Übergang, ohne Aufteilung der Abrechnung (W07, P01 offen) | M5, 6.9.2, D15 bis D17 | implemented, not accepted (Betreiberwunsch 28.09.2026; keine Migration) |
| [M20-06](M20-06-mail-versand-nachweis.md) | Mailversand nur mit Nachweis: Idempotenzschlüssel je Versand, kein zweiter Versand, Weiterleitung erst nach Commit, Postfach-Soft-Delete | M20, 6.6 | implemented, not accepted |
| [M20-07](M20-07-gmail-push-vollabruf-erledigt.md) | Gmail-Push über Pub/Sub mit Sicherheitsnetz alle fünf Minuten, Vollabruf des Posteingangs beim Verbinden und auf Anforderung, Erledigt archiviert je Mail, Ticketabschluss per letzter erledigter Mail | M20, 6.6 | implemented, not accepted (Migration 0144; Pub/Sub-Thema M20-05 offen) |
| [M20-08](M20-08-gmail-rueckkanal-erledigt.md) | Rückkanal Gmail zu Plattform: Archivierung, Papierkorb, Spam, Löschung und Wiederherstellung je Postfachkopie aus dem Gmail Verlauf; im Modus Übernehmen erledigt das Sammelpostfach die Mail, optional Ticketabschluss; eigene Archivierungen nie eine Entscheidung | M20, 6.6 | implemented, not accepted (Migration 0224; Modus done erst nach Spike, Standard record_only) |
| [M40-01](M40-01.md) | Messdienstleister: zentrale Verbindungen, Objekt- und Einheitenzuordnung, ehrliche Funktionsanzeige, lesender Abruf mit Klärungsbereich | Masterprompt Messdienstleister 2 bis 10 | implemented, not accepted (Migration 0145; Adapter Stufe 2 offen) |
| [M40-02](M40-02.md) | Messdienstleister: kontrollierte schreibende Vorgänge (Rollen, Billing Input) mit getrennten Schritten Prüfen, Freigeben, verbindlich beauftragen, Datenversion und Protokoll | Masterprompt Messdienstleister 12, Fälle 11 und 12 | implemented, not accepted (Migration 0153; Freigabe der Rechte und Vier-Augen-Entscheidung offen, M40-03) |
| [P1-01](P1-01-kontakt-sperre-loeschdatum.md) | Kontakt: Sperrdatum beim Sperren, Löschprofil (nur freigegebene Aufbewahrungsprofile) mit vorgemerktem Löschdatum, Sperrliste; Löschung bleibt manuell im Vier-Augen-Prinzip, kein automatischer Löschlauf | Ergänzung 27.09.2026 4.1, M6-04 | implemented, not accepted (Migration 0147; Betreiberentscheidung 26.09.2026) |
| [P1-02](P1-02-energieausweis-gebaeude.md) | Objekt, Gebäude, Einheit: Ergänzungsfelder 4.2 bis 4.4, Energieausweis nur am Gebäude, ETag-Änderung für Gebäude und Einheit, Abrechnungszeiträume, Untergemeinschaften, Objektmappe, Leerstands-Umlagewerte, Zählerwechsel | Ergänzung 27.09.2026 4.2 bis 4.4 | implemented, not accepted (Migrationen 0148, 0149; Betreiberentscheidung 26.09.2026) |

| [M11-02](M11-02-csv-import.md) | Bank-CSV-Import mit automatischer Formaterkennung nur nach geprüften Kopfzeilen, generisches Mapping sonst, gleicher Dublettenschutz wie CAMT/MT940 | Masterprompt Kapitel 8, Datei-Import | implemented, not accepted (Migration 0168; Kopfzeilen bis auf Sparkasse CSV-CAMT nicht gegen reale Exporte verifiziert) |
| [M24-02](M24-02-vermoegensbericht.md) | Vermögensbericht zum Stichtag: Rücklage Soll und Ist, Bankbestände, Forderungen, Verbindlichkeiten, Darlehen, manuelle Positionen, Abstimmung mit sichtbarer Differenz, PDF-Entwurf hinter G4 | Masterprompt W11, R04 als Einschätzung | implemented, not accepted (27.09.2026) |
| [M24-03](M24-03-darlehen-jahresabrechnung.md) | Zins und Tilgung je Abrechnungsjahr aus Buchungen oder Ratenplan, Verteilung nach Schlüssel als Ausweis ohne Ergebniswirkung, Restschuld im Vermögensbericht | Masterprompt W04, W10; Umlage offen (M24-03) | implemented, not accepted (27.09.2026) |

| [M21-01](M21-01.md) | Magic-Link-Anmeldung des Kundenportals (E-Mail, 15 Minuten, einmal nutzbar), QR-Einladung für den Brief (90 Tage), optionaler zweiter Faktor per E-Mail-Code | M21, 14, 0.1.13 | implemented, not accepted |

| [M19-01](M19-01-sla-freigabe.md) | SLA-Regeln je Priorität und Kategorie als Entwurf; nur von der Geschäftsführung (`tenant_settings:update`) freigegebene Werte steuern Uhren und Eskalation, sonst "keine SLA" mit Hinweis | M19, M21, 6.6 | implemented, not accepted (Migration 0203; M19-01 Wertetabelle offen) |
| [M19-02](M19-02-beiratsbeteiligung.md) | Beiratsbeteiligung: Vorlage an den Verwaltungsbeirat (Kategorie Beirat der Objektkontakte) zur Kenntnis oder um Votum mit Frist, Rückmeldung im Portal und CRM, Protokoll am Ticket, Empfehlungsregel je Mandant, kein Geldbezug | M19, M21, M25, 6.2, 6.6 | implemented, not accepted (Migration 0203; M19-02 Wertgrenzen offen) |

| [A80-01](A80-01-zuordnungskette.md) | Zuordnungsprüfung: sichere Kette vom Kontakt (eindeutiger Mietvertrag oder eindeutiges Eigentum einer Einheit) zu Einheit und Objekt, nur in ein leeres Feld, erneute Prüfung nach einem Ja auf die Kontakt-Rückfrage | A-068, Betreiberauftrag 27.09.2026 | implemented, not accepted |
| [C2-01](C2-01-wartungszyklus.md) | Wartungszyklus: Erledigung mit Intervall rückt die Fälligkeit um das eingetragene Intervall vor (Monatsende begrenzt), ohne Intervall wird der Eintrag geschlossen; Prüfzyklen sind Betreibereingaben ohne Vorgabe | Masterprompt 6.2, Handbuch Stammdaten 28.09.2026, Fachliche Umsetzung | implemented, not accepted (28.09.2026; STAMM-01 offen) |
| [ES-01 to ES-11](ES-erfassungsstandards.md) | Erfassungsstandards: PLZ fünfstellig in Deutschland (hart, auch API), sonst nicht blockierende Hinweise zu Anschrift und Objektname, Namensfeldern von Kontakten, Fristdatum und verantwortlicher Person; Bericht Datenqualität ohne automatische Änderung | Betreiberrückmeldung 28.09.2026, Produktschutz | implemented, not accepted |
| [WS-01](WS-01-fristtypen.md) | Fristtypen je Mandant (Auslöser, Dauer vom Betreiber ohne Vorgabe, verantwortliche Rolle), eigene Fristen aus Ticket, Vertrag, Einheit, Objekt oder Mieterhöhungsfall mit verantwortlicher Person (ES-10), Kündigungsfrist als Orientierung, Checkliste Verwalterwechsel je Objekt, Zugangsdatum Mieterhöhung im CRM; alles zu verifizieren, keine Rechtsfrist | Arbeitsplatz M9, Vermietung M26, Handbuchlücken 28.09.2026 | implemented, durations open (WS-01-Q1, WS-01-Q2) |

Index checked against the files in this folder on 27.09.2026: every rule file has one row above (`A80-01` added).
