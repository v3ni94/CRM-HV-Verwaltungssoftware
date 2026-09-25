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
| [M26-RL](M26-rent-law.md) | Mieterhöhung Regelwerk | 8, M26 | implemented, not accepted |
| [M28-01](M28-01.md) | Makler: Anzeigen, keine FLOWFACT-Anbindung | M28 | implemented, not accepted |
| [M30-01](M30-01.md) | Übergabeprotokoll: Festschreibung, Versionen, Zustellung | M30 | implemented, not accepted |
| [M11-finapi-dedup](M11-finapi-dedup.md) | finAPI Umsatzabgleich (Bankreferenz vorrangig, D05) | M11 | implemented, not accepted |
| [M11-finapi-authorization](M11-finapi-authorization.md) | finAPI: Recht `banking:approve`, unzugeordnete Konten verborgen | M11 | implemented, not accepted |
| [M3-02](M3-02-sepa-mandate.md) | SEPA-Mandat auf der Bankverbindung des Kontakts | M3, 6.1 | implemented, not accepted |
| [M20-05](M20-05.md) | Mail-Vorbereitung: Dokumentsuche strikt je Objekt, keine Kontoauflistung | M20, M34, 11.2 | implemented, not accepted |
| [B01](B01.md) | Richtiger Rechtsträger | 7.1 | implemented, not accepted |
| [B02](B02.md) | Entwurf und Buchung | 7.1 | implemented, not accepted |
| [B03](B03.md) | Korrektur statt Überschreiben | 7.1 | implemented, not accepted |
| [B04](B04.md) | Eindeutige Nummern | 7.1 | implemented, not accepted |
| B05 | Belegkette | 7.1 | specified, not implemented |
| [B06](D08-rest-cents.md) | Präzision | 7.1 | implemented, not accepted (M17, D08 tested) |
| [B07](B07.md) | Stichtagswahrheit | 7.1 | implemented, not accepted |
| [B08](B08.md) | Keine doppelte wirtschaftliche Wirkung | 7.1 | implemented, not accepted |
| [B09](B09.md) | Abstimmung | 7.1 | implemented, not accepted |
| A01 | Ergebnisstand | 7.6 | specified, not implemented |
| A02 | Betriebskosten Miete | 7.6 | implemented, not accepted (M17, `test_m17_operating_costs.py`) |
| A03 | Schlüssel | 7.6 | implemented, not accepted (M17, time weighted keys) |
| A04 | Vorauszahlungen und Fristen | 7.6 | implemented, not accepted (M17, advances and deadline orientation) |
| A05 | Nutzerwechsel, Leerstand, Heizkosten | 7.6 | implemented, not accepted (M17, vacancy share to owner, heating external only) |
| A06 | Eigentümerabrechnung Miete/SEV | 7.6 | specified, not implemented |
| A07 | Bedienung | 7.6 | specified, not implemented |
| W01 | Eigene Gemeinschaft | 7.8 | implemented (M24), ledger check |
| W02 | Wirtschaftsplan | 7.8 | implemented (M24), behind G4 |
| W03 | Kostenverteilung | 7.8 | implemented, not accepted (M24, `mhvp.hoa.calc.unit_weights`) |
| W04 | Jahresabrechnung als nachvollziehbare Überleitung | 7.8 | specified, not implemented |
| W05 | Abrechnungsspitze und Rückstände | 7.8 | implemented (M24), [W05](W05-hoa-result.md) |
| W06 | Beschluss und Buchung | 7.8 | implemented (M24), [W06](W06-resolution.md) |
| W07 | Eigentümerwechsel | 7.8 | open, M24-01 |
| W08 | Erhaltungsrücklagen | 7.8 | implemented (M24), D03 tested |
| W09 | Sonderumlagen und Maßnahmen | 7.8 | implemented, not accepted (special levy and amendments per W09-01, `test_w09_special_levy.py`) |
| W10 | Darlehen, Versicherungen, größere Maßnahmen | 7.8 | specified, not implemented |
| W11 | Vermögensbericht | 7.8 | partly implemented (M24 asset report); structure open, M24-02 |
| W12 | Abrechnungspaket | 7.8 | implemented, not accepted (package and blocking checks, `test_w09_special_levy.py::test_w12_package_blocks_release`) |
| W13 | Beirat und Versammlung | 7.8 | implemented, not accepted (M25); majority rules open, M25-01 |
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
