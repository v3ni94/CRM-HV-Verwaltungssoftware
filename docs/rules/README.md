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
| [M2-07](M2-07.md) | Löschen nur Administrator | M2 | implemented, not accepted |
| [M10-01](M10-01-kontenrahmen-vorlage.md) | Kontenrahmen-Vorlage nach Anhang A.1 mit vorgeschlagenen Erlöskonten der Mietverwaltung (`review_status = "entwurf"`, Freigabe durch Steuerberatung offen) | M10, 7.2, A.1 | implemented, not accepted (Offene Entscheidung V8, M10-02) |
| [M10-02](M10-02-kostenkonten-vorbelegung.md) | Kostenkonten der Vorlage als Entwurf nach BetrKV vorbelegt (umlagefähig mit üblichem Schlüssel, sonst nicht umlagefähig, Umsatzsteueroption offen), Seed füllt nur unbesetzte Felder | M10, 7.2, A.1, A.2 | implemented, not accepted (Offene Entscheidung mit Steuerberatung) |
| [M8-04](M8-04-mehrpersonen-bevollmaechtigte.md) | Mehrpersonen-Parteien aus dem Adressbuch als eine Partei mit Mitgliedern, unklare Fälle zur Prüfung; Bevollmächtigte mit Zustellregel für Versand, Serienbriefe und WEG-Einladungen | M8, M3, M23, 6.1 | implemented, not accepted |
| [M13-04](M13-04.md) | XRechnung für Verwalterhonorar-Rechnungen nur aus eingetragenen Mandantendaten | M13, 13.5 | implemented, not accepted |
| [M16-01](M16-01.md) | Mahngebühr nur mit hinterlegtem Betrag, Rechnung an Gemeinschaft nur mit vertraglicher Grundlage | M16 | implemented, not accepted |
| [M16-02](M16-02.md) | Mahnstufen je Objekt erben vom Mandanten, Mahnschreiben nur als Entwurf | M16 | implemented, not accepted |
| [M15-02](M15-02-pain008.md) | SEPA-Basislastschrift pain.008: Mandatsprüfung, Sequenz, Vier-Augen, Datei nur hinter G2 | M15, 7.5 SEPA | implemented, not accepted |
| [M18-02](M18-02-pruefexport.md) | Prüfexport: maschinell auswertbar im Umfang von Abschnitt 7.7, kein Datenträgerüberlassungsformat | M18, 7.7, D55 | implemented, not accepted |
| [M18-03](M18-03.md) | DATEV-Buchungsstapel: EXTF-Header nur mit Beraterdaten, keine erfundene Kontenzuordnung | M18 | implemented, not accepted |
| [M18-04](M18-04-datev-kontenzuordnung.md) | DATEV-Kontenzuordnung je Mandant: Betreiberpflege ohne vorbelegten Kontenrahmen, Export nur mit vollständiger Zuordnung (MHVP-BILL-0008) | M18, A36 | implemented, not accepted |
| [M18-05](M18-05-steuerberaterzugang.md) | Steuerberaterzugang: Zugriffsbereich je Rechtsträger (`membership.legal_entity_ids`), leerer Bereich bedeutet kein Zugriff, fremde Rechtsträger 404 | M18, M18-02, A37 | implemented, not accepted |
| [M26-RL](M26-rent-law.md) | Mieterhöhung Regelwerk | 8, M26 | implemented, not accepted |
| [M28-01](M28-01.md) | Makler: Anzeigen, keine FLOWFACT-Anbindung | M28 | implemented, not accepted |
| [M26-02](M26-02.md) | OpenImmo-Export: Format-Mapping, nur lesend, kein Portal-Upload | M26 | implemented, not accepted |
| [M30-01](M30-01.md) | Übergabeprotokoll: Festschreibung, Versionen, Zustellung | M30 | implemented, not accepted |
| [M30-06](M30-06.md) | Übergabeprotokoll: Gehilfenzugang, Sichtbarkeit und Ablauf | M30 | implemented, not accepted |
| [M11-finapi-dedup](M11-finapi-dedup.md) | finAPI Umsatzabgleich (Bankreferenz vorrangig, D05) | M11 | implemented, not accepted |
| [M11-finapi-authorization](M11-finapi-authorization.md) | finAPI: Recht `banking:approve`, unzugeordnete Konten verborgen | M11 | implemented, not accepted |
| [M11-05](M11-05-credentials-never-in-crm.md) | Zugangsdaten nie im CRM (Bank-WebForm) | M11 | implemented, not accepted |
| [M10-03](M10-03-tilgungsfolge-vorschlag.md) | Ausgleich offener Posten nach gesetzlicher Reihenfolge, nur Vorschlag mit Bestätigung (Tilgungsfolge, D39) | M10, 7.4 Nr. 5 | implemented, not accepted |
| [M11-06](M11-06-payment-proposal-only-until-g2.md) | Zahlung nur Vorschlag bis G2 (Rechnungsabgleich) | M11, 18.0 | implemented, not accepted |
| [M3-02](M3-02-sepa-mandate.md) | SEPA-Mandat auf der Bankverbindung des Kontakts | M3, 6.1 | implemented, not accepted |
| [M20-05](M20-05.md) | Mail-Vorbereitung: Dokumentsuche strikt je Objekt, keine Kontoauflistung | M20, M34, 11.2 | implemented, not accepted |
| [M19-05](M19-05.md) | Stammdatenänderung aus einer Ticket-Mail: nur Vorschlag, Entscheidung durch Menschen, nie IBAN | M19, M20, 9.1 | implemented, not accepted |
| [M23-05](M23-05.md) | Google-Kalender: Einladungen nur nach Bestätigung, kein stiller externer Überschreib | M23 | implemented, not accepted |
| [M35-01](M35-01.md) | objektakte-Übernahme: Quellkennung und IBAN-Regel | M35 | implemented, not accepted |
| [M35-02](M35-02.md) | objektakte-Übernahme: Klassifikation Stufe 1 (Regeln) | M35 | implemented, not accepted |
| [M35-03](M35-03.md) | objektakte-Übernahme Stufe 4: Berechtigungsschlüssel `objektakte:*`, Benutzerabbildung nur als Vorschlag, KI-Protokoll nur lesend | M35 | implemented, not accepted |
| [M21-05](M21-05.md) | WhatsApp nur mit freigegebenen Vorlagen und Einwilligung | M21 | implemented, not accepted |
| [M21-06](M21-06.md) | Zugriffsmatrix auf jedem Pfad: GdWE-Einsicht, fremde Akten, KI-Kontext, freigegebene Fassung (D29 bis D31) | M21, M6, M7, 6.9.6, 14, E06 | implemented, not accepted |
| [M21-07](M21-07.md) | Prüfungsraum Beirat: Portalrolle `board` je Prüfauftrag, nur Lesen und Vermerk, keine Buchung oder Freigabe, Belege nur aus Prüfpositionen (PÜ07, PÜ08) | M21, M25, 7.9.2, 14, D32, D33 | implemented, not accepted |
| [M19-02](M19-02-ticket-templates.md) | Ticketvorlagen mit Checkliste und Pflichtfeldern (inkl. IBAN), Sammelstatuswechsel | M19, 6.6 | implemented, not accepted |
| [M25-01](M25-01-mehrheitsregeln.md) | Mehrheitsregeln je Beschlussgegenstand: Prüfung "erreicht / nicht erreicht / nicht prüfbar" ohne Statusänderung, Freigabe durch zweite Person | M25, 6.9.12, W13 | implemented, not accepted |
| [M9-02](M9-02-automation.md) | Regel-Engine Stufe 1 und 2: Ticket, Benachrichtigung, Ticketfeld, Webhook (signiert), Mail- und Briefentwurf, KI-Aufgabe; Zeitplan als Auslöser; Tiefe 1, Testlauf ohne Wirkung | M9, 15.2 | implemented, not accepted |
| [M7-06](M7-06.md) | Tabellenimport deterministisch, KI nur für Spaltenzuordnung und Restzeilen | M7 | implemented, not accepted |
| [B01](B01.md) | Richtiger Rechtsträger | 7.1 | implemented, not accepted |
| [B02](B02.md) | Entwurf und Buchung | 7.1 | implemented, not accepted |
| [B03](B03.md) | Korrektur statt Überschreiben | 7.1 | implemented, not accepted |
| [B04](B04.md) | Eindeutige Nummern | 7.1 | implemented, not accepted |
| B05 | Belegkette | 7.1 | specified, not implemented |
| [B06](D08-rest-cents.md) | Präzision | 7.1 | implemented, not accepted (M17, D08 tested) |
| [B07](B07.md) | Stichtagswahrheit | 7.1 | implemented, not accepted |
| [B08](B08.md) | Keine doppelte wirtschaftliche Wirkung | 7.1 | implemented, not accepted |
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
| W11 | Vermögensbericht | 7.8 | partly implemented (M24 asset report); structure open, M24-02 |
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
| [M6-03](M6-03-loeschung-spiegel.md) | Löschung gespiegelter Dokumente: Drive-Kopie löschen (endgültig, ersatzweise Papierkorb, vermerkt), Paperless-Dokument behalten und mit "gelöscht" kennzeichnen, beide Schritte protokolliert, Löschung "offen" bis beide Schritte gelungen sind, Wiederholung per Task, erneutes Anstoßen per API | 6.9.5, D46, D47, V17 | implemented, not accepted (Migration 0143; Betreiberentscheidung 26.09.2026) |
| [M6-04](M6-04-aufbewahrungsprofile.md) | Standard-Aufbewahrungsprofile je Mandant als Entwurf ("Entwurf, Prüfung Steuerberatung offen"), Seed idempotent ohne Überschreiben, Löschung bleibt bis zur Freigabe gesperrt, Freigabe je Mandant mit `tenant_settings:update`, Vier-Augen und Protokoll | 6.9.5, S04, S05, V17 | implemented, not accepted (Migration 0139; Entscheidung Steuerberatung offen) |
| [M5-02](M5-02-kautionsabrechnung.md) | Kaution: getrennte Verwahrung, Verzinsung je Jahr als Bewegung, Kautionsabrechnung bei Vertragsende als Entwurf mit Zinsart (individuell je Jahr, Referenzzinssatz je Jahr, keine), Freigabe hinter G3 | M5, 6.9.1, D56, 7.1 B01 | implemented, not accepted (Migration 0138; Zinssatz rechtlich zu bestätigen, Betreiberentscheidung 26.09.2026) |
| [M20-06](M20-06-mail-versand-nachweis.md) | Mailversand nur mit Nachweis: Idempotenzschlüssel je Versand, kein zweiter Versand, Weiterleitung erst nach Commit, Postfach-Soft-Delete | M20, 6.6 | implemented, not accepted |
| [M20-07](M20-07-gmail-push-vollabruf-erledigt.md) | Gmail-Push über Pub/Sub mit Sicherheitsnetz alle fünf Minuten, Vollabruf des Posteingangs beim Verbinden und auf Anforderung, Erledigt archiviert je Mail, Ticketabschluss per letzter erledigter Mail | M20, 6.6 | implemented, not accepted (Migration 0144; Pub/Sub-Thema M20-05 offen) |
| [M40-01](M40-01.md) | Messdienstleister: zentrale Verbindungen, Objekt- und Einheitenzuordnung, ehrliche Funktionsanzeige, lesender Abruf mit Klärungsbereich | Masterprompt Messdienstleister 2 bis 10 | implemented, not accepted (Migration 0145; Adapter Stufe 2 offen) |

Index checked against the files in this folder on 26.09.2026: every rule file has one row above (`M19-02` and `M25-01` were added, `M9-02` and `W13` updated).
