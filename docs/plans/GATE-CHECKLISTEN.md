# Checklisten der Freigabestufen G2 bis G4 (GA14-03)

Grundlage: Abschnitt 18.0 (Tabelle der Stufen), ADR 0003 Punkt 5. Die Codes sind technisch in
`apps/api/src/mhvp/platform/gate_checklists.py` hinterlegt und über
`GET /api/v1/tenant/release-gates/checklists` abrufbar. Ein Antrag auf G2, G3 oder G4 lässt sich
nur genehmigen, wenn jeder Code mit einer Bestätigungsnotiz versehen ist und ein Nachweisdokument
des Mandanten verknüpft ist (Fehler `MHVP-GATE-0006`). Die Liste ist der technische Mindestumfang
aus 18.0; der erforderliche Prüfumfang je Stufe ist offen (AA02-01). G1 nutzt weiter das
Öffnungspaket (`docs/plans/G1-oeffnungspaket-2026-09-29.md`), G5 die Nachweisliste aus M27.

Alle Stufen bleiben geschlossen. Diese Liste öffnet nichts.

## G1 Produktive Buchführung

Die Prüfpunkte der Öffnungsliste M12-09 stehen in `apps/api/src/mhvp/accounting/g1_opening.py`
und unter Einstellungen, Buchhaltung, G1 Öffnung (`GET /api/v1/accounting/g1-opening`). Je
Punkt: Status, Datum, bestätigende Person, verantwortliche Person und Nachweis (Dokument oder
Verweis, Welle 16, AE03). Der Automatikschalter lässt sich erst nach offener G1 mit Antrag
und Freigabe durch eine zweite Person einschalten (`/api/v1/banking/automation/switch-requests`);
der Vergleichslauf (`GET /api/v1/banking/automation/comparison`) ist Nachweis, kein Beweis.

Welle 23 (AM10, GAJ-503): eigene Prüfpunkte für die in 18.0 genannten Voraussetzungen
geprüfte Migration (`migration_verified`, Abgleichbericht ohne ungeklärte Differenz, Abnahme
M8-08), Rechtsträgertrennung (`legal_entity_separation`) und dokumentierte Korrektur
(`documented_correction`). Diese drei Punkte lassen sich nur mit verknüpftem Nachweis abhaken
(422 sonst). GAJ-504: Nachweisverweise sind prüfbar typisiert, `ci-run:<Lauf>@<Commit>`
(CI-Lauf mit den annex_d-Markern), `commit:<SHA>`, `version:<x.y.z>`, `doc:<Pfad>`; die
Übersicht zeigt `evidence_kind` je Punkt und `cases_passed_without_test_run`, der G1-Antrag
nennt beide Lücken im Nachweistext. Für G2 bis G4 zeigt `checklist_unverified` am Antrag die
Codes, deren Bestätigung keinen solchen Verweis enthält; die Genehmigungsregel selbst bleibt
unverändert (AA02-01).

## G2 Zahlungsveranlassung

| Code | Prüfpunkt | Nachweis |
| --- | --- | --- |
| bank_contract | Bankvertrag geprüft | Vertrag, EBICS oder Schnittstellenvereinbarung |
| permissions | Berechtigungen geprüft | Rollen und Freigabeberechtigte |
| mandate_payee_check | Mandats- und Empfängerprüfung geprüft | Testfälle Mandat, Empfänger, IBAN-Änderung |
| approval_versioning | Freigabeversionierung geprüft | Testprotokoll Vier-Augen und Version |
| retry_return_flows | Wiederholungs- und Rückgabeabläufe geprüft | Testprotokoll Rücklastschrift, Abbruch |
| reconciliation | Abstimmung geprüft | Abgleich Auftrag und Kontoauszug |

## G3 Mietabrechnung

| Code | Prüfpunkt | Nachweis |
| --- | --- | --- |
| contract_allocation_basis | Vertrags- und Umlagegrundlagen geprüft | Freigegebene Abnahmefälle Miete |
| heating_co2_rules | Heiz- und CO2-Regeln geprüft | Fachliche Freigabe der Regeln |
| prepayments | Vorauszahlungen geprüft | Zahlenfälle |
| deadlines | Fristen geprüft | Fristenregeln mit Quelle |
| access_document_inspection | Zugang und Belegeinsicht geprüft | Portal und Einsichtspaket |
| released_cases | Prüfung anhand freigegebener Fälle | Abnahmeprotokoll |

## G4 WEG-Abrechnung

| Code | Prüfpunkt | Nachweis |
| --- | --- | --- |
| w01_w13 | W01 bis W13 geprüft | Abnahmeprotokoll |
| independent_number_cases | Unabhängige Zahlenfälle geprüft | Fälle mit vorab festgelegten Sollwerten |
| owner_change | Eigentümerwechsel geprüft | Testfall Stichtag |
| resolution_basis | Beschlussgrundlage geprüft | Beschlussvorlage |
| reserves | Rücklagen geprüft | Rücklagenentwicklung |
| advisory_board_process | Beiratsprozess geprüft | Ablauf Belegprüfung Beirat |
| inspection | Einsicht geprüft | Einsichtspaket |

## Umfang einer Freigabe (GA14-02)

Ein Antrag kann den Umfang strukturiert begrenzen: `scope_property_ids` (Objekte),
`scope_legal_entity_ids` (Rechtsträger), `scope_functions` (Funktionscodes aus der
Checklistenabfrage). Fehlt eine Angabe, gilt sie für alle (Standard). Eine begrenzte Freigabe
öffnet die Stufe nur für Prüfungen mit passendem Kontext (`DbReleaseGateResolver.is_open_for`);
Prüfungen ohne Kontext sehen die Stufe weiter geschlossen. Die Router reichen den Objektbezug
noch nicht durch (AA02-02).

## Nachweis und Widerruf (GA14-04)

Genehmigung schreibt `opened_by` und `opened_at`, Widerruf nur `revoked_by`, `revoked_at` und
`revoke_comment`. Wer wann geöffnet hat, bleibt nach dem Widerruf erhalten.
`evidence_document_id` verknüpft das Nachweisdokument (Migration 0304).
