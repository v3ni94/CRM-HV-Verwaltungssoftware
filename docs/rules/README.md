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
| [B01](B01.md) | Richtiger Rechtsträger | 7.1 | implemented, not accepted |
| [B02](B02.md) | Entwurf und Buchung | 7.1 | implemented, not accepted |
| [B03](B03.md) | Korrektur statt Überschreiben | 7.1 | implemented, not accepted |
| [B04](B04.md) | Eindeutige Nummern | 7.1 | implemented, not accepted |
| B05 | Belegkette | 7.1 | specified, not implemented |
| B06 | Präzision | 7.1 | specified, not implemented |
| [B07](B07.md) | Stichtagswahrheit | 7.1 | implemented, not accepted |
| [B08](B08.md) | Keine doppelte wirtschaftliche Wirkung | 7.1 | implemented, not accepted |
| [B09](B09.md) | Abstimmung | 7.1 | implemented, not accepted |
| A01 | Ergebnisstand | 7.6 | specified, not implemented |
| A02 | Betriebskosten Miete | 7.6 | specified, not implemented |
| A03 | Schlüssel | 7.6 | specified, not implemented |
| A04 | Vorauszahlungen und Fristen | 7.6 | specified, not implemented |
| A05 | Nutzerwechsel, Leerstand, Heizkosten | 7.6 | specified, not implemented |
| A06 | Eigentümerabrechnung Miete/SEV | 7.6 | specified, not implemented |
| A07 | Bedienung | 7.6 | specified, not implemented |
| W01 | Eigene Gemeinschaft | 7.8 | implemented (M24), ledger check |
| W02 | Wirtschaftsplan | 7.8 | implemented (M24), behind G4 |
| W03 | Kostenverteilung | 7.8 | specified, not implemented |
| W04 | Jahresabrechnung als nachvollziehbare Überleitung | 7.8 | specified, not implemented |
| W05 | Abrechnungsspitze und Rückstände | 7.8 | implemented (M24), [W05](W05-hoa-result.md) |
| W06 | Beschluss und Buchung | 7.8 | implemented (M24), [W06](W06-resolution.md) |
| W07 | Eigentümerwechsel | 7.8 | open, M24-01 |
| W08 | Erhaltungsrücklagen | 7.8 | implemented (M24), D03 tested |
| W09 | Sonderumlagen und Maßnahmen | 7.8 | specified, not implemented |
| W10 | Darlehen, Versicherungen, größere Maßnahmen | 7.8 | specified, not implemented |
| W11 | Vermögensbericht | 7.8 | specified, not implemented |
| W12 | Abrechnungspaket | 7.8 | specified, not implemented |
| W13 | Beirat und Versammlung | 7.8 | specified, not implemented |
| PÜ01 | Vollständigkeit | 7.9.1 | specified, not implemented |
| PÜ02 | Sachliche Prüfung | 7.9.1 | specified, not implemented |
| PÜ03 | Rechnerische/steuerliche Prüfung | 7.9.1 | specified, not implemented |
| PÜ04 | Dubletten/Betrugsrisiko | 7.9.1 | specified, not implemented |
| PÜ05 | Prüfentscheidungen | 7.9.1 | specified, not implemented |
| PÜ06 | Prüfauftrag | 7.9.2 | specified, not implemented |
| PÜ07 | Nachvollziehbare Navigation | 7.9.2 | specified, not implemented |
| PÜ08 | Prüfen und nachfordern | 7.9.2 | specified, not implemented |
| PÜ09 | Aussagekräftiger Abschlussbericht | 7.9.2 | specified, not implemented |
| PÜ10 | Eigentümer | 7.9.3 | specified, not implemented |
| PÜ11 | Mieter | 7.9.3 | specified, not implemented |
| PÜ12 | Praktischer Zugang | 7.9.3 | specified, not implemented |
| PÜ13 | Protokoll ohne Rechtsfiktion | 7.9.3 | specified, not implemented |
| H01 | Messdienst oder Eigenberechnung | 7.10 | specified, not implemented |
| H02 | HeizkostenV | 7.10 | specified, not implemented |
| H03 | Laufende Pflichten | 7.10 | specified, not implemented |
| H04 | CO₂-Regeln mit Geltungsstand | 7.10 | specified, not implemented |
| H05 | Bereits veröffentlichte spätere Regeln | 7.10 | specified, not implemented |
| H06 | § 35a | 7.10 | specified, not implemented |
| S01 | Steuerlicher Kontext | 7.11 | specified, not implemented |
| S02 | E-Rechnung | 7.11 | specified, not implemented |
| S03 | Original und Verarbeitung | 7.11 | specified, not implemented |
| S04 | Differenzierte Fristen | 7.11 | specified, not implemented |
| S05 | WEG-Dauerunterlagen, Sperren und Löschung | 7.11 | specified, not implemented |
| S06 | Datenschutz und Auskunft | 7.11 | specified, not implemented |
