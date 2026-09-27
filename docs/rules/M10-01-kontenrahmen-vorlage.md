# M10-01 Kontenrahmen-Vorlage: Entwurf nach Anhang A.1 mit vorgeschlagenen Erlöskonten der Mietverwaltung

| Field | Content |
| --- | --- |
| ID | `M10-01` |
| Title | Kontenrahmen-Vorlage (Anhang A.1) als Entwurf; Erlöskonten der Mietverwaltung als Vorschlag mit Prüfkennzeichen `review_status = "entwurf"` und Vermerk "Freigabe durch Steuerberatung offen" |
| Scope | `mhvp.accounting.defaults` (`A1_ACCOUNTS`, `PROPOSED_ACCOUNTS`, `TEMPLATE_ACCOUNTS`, `merge_missing`), `mhvp.accounting.services.default_template` und `create_ledger`, `LedgerAccount.review_status` und `review_note` (Migration 0137), `POST /api/v1/accounting/templates/default`, `GET /api/v1/accounting/templates`, `GET /api/v1/accounting/ledgers/{id}/accounts`. Alle Mandanten; Vorschläge gelten für die Rechtsträgerarten `rental_owner` und `sev_owner` |
| Source status | Offene Entscheidung. Keine Rechtsnorm: Kontonummern sind Migrations- und Produktkonvention (7.2, Ergänzende Einordnung). Nummern der A.1-Konten aus Anhang A.1 (Abruf 23.09.2026). Nummern der Vorschläge nach dem Muster von A.1 (060100 Hausgeld, 060200 Erhaltungsrücklage, dann je Zahlungsart in Hunderterschritten) auf Betreiberauftrag vom 26.09.2026. Zuständig für die Freigabe: Steuerberatung mit Betreiber (V8). Freigabestatus: Vorlage nicht freigegeben (`released = false`), Vorschläge `review_status = "entwurf"` |
| Acceptance case | keine in Anhang D; Tests `apps/api/tests/integration/test_m10_chart_template.py` (Nummernmuster, Idempotenz der Vorlage ohne Überschreiben bestehender Zeilen, Mandantentrennung, Prüfkennzeichen in der Kontenausgabe, keine Vorschläge im GdWE-Buchungskreis) und `test_m10_ledger.py` (Vorlage nicht freigegeben) |
| Implementation | Vorschläge: 060300 Miete, 060400 Betriebskostenvorauszahlung, 060500 Heizkostenvorauszahlung, 060600 Garagenmiete, 060700 Stellplatzmiete, 060800 Sonstige Erlöse (Kategorie `revenue`, Typ `income`). Umlagefähigkeit, Abrechnungsart und Umsatzsteueroption bleiben `none` (M10-02 offen). Seed ergänzt nur fehlende Zeilen je Nummer, bestehende Zeilen bleiben unverändert |
| Change reason | Betreiberentscheidung 26.09.2026 zu M10-01: Sollstellungen der Mietverwaltung (M13) benötigen Erlöskonten je Zahlungsart; bis dahin blockierten fehlende Konten die Sollstellung. Der Vorschlag ersetzt keine Freigabe |

## Regeln

- Die Vorlage `a1` Version 1 enthält die Konten aus Anhang A.1 unverändert und zusätzlich
  die sechs Vorschlagskonten der Mietverwaltung. Jede Vorschlagszeile trägt
  `review_status = "entwurf"` und `review_note = "Freigabe durch Steuerberatung offen"`;
  A.1-Zeilen tragen `review_status = "none"`.
- `POST /accounting/templates/default` ist idempotent: existiert die Vorlage, werden nur
  Zeilen ergänzt, deren Nummer fehlt. Bestehende Zeilen, auch vom Mandanten geänderte, werden
  nie überschrieben oder entfernt. Bereits angelegte Buchungskreise werden nicht verändert;
  fehlende Konten werden dort je Buchungskreis ergänzt (7.2).
- Ein Buchungskreis übernimmt aus der Vorlage nur Zeilen, deren `applies_to` die
  Rechtsträgerart enthält. Die Vorschläge gelten für `rental_owner` und `sev_owner`, nicht
  für GdWE oder Verwalter. Das Kennzeichen wird auf das Konto übernommen und in
  `GET /accounting/ledgers/{id}/accounts` ausgegeben.
- Das Kennzeichen ist ein Prüfhinweis, keine Sperre: die Freigabe der Vorlage (V8) und die
  Freigabe produktiver Buchhaltung (G1) bleiben getrennte Entscheidungen. G1 bleibt geschlossen.
- Nicht vorgeschlagen: Kaution als Verbindlichkeit und Mietforderungen. Anhang A.1 nennt
  beide nicht, 7.2 sieht keinen Nummernbereich für Kautionsverbindlichkeiten vor, und
  Mietforderungen werden über die Debitorenkonten je Vertrag (090000 bis 099999) geführt.
  Ein Kautionskonto wird erst nach Entscheidung der Steuerberatung ergänzt (OPEN_QUESTIONS
  M10-01).
- Umlagefähigkeit, Abrechnungsart und Umsatzsteueroption der Konten bleiben unbesetzt, bis
  M10-02 entschieden ist.

## Nachtrag 27.09.2026: Freigabeworkflow (V8, Gate G1)

- Jede Vorlage trägt einen Status `draft` (Entwurf), `in_review` (zur Prüfung) oder
  `released` (freigegeben) (Migration 0190, `mhvp.accounting.chart_release`). Die Freigabe
  speichert Datum, Freigeber, Kommentar und optional das Dokument der Steuerberatung
  (`release_document_id`, Dokument muss im Mandanten existieren). Sie ist idempotent: eine
  freigegebene Version wird nicht erneut freigegeben oder überschrieben.
- Schnittstelle: `POST /accounting/templates/{id}/submit-review`,
  `POST .../back-to-draft`, `POST .../release` (Body `comment`, `document_id`, Recht
  `accounting:approve`), `POST .../versions` (neue Version als Entwurf,
  `supersedes_id` zeigt auf die Vorgängerversion), `PUT .../accounts` (nur im Entwurf,
  sonst `MHVP-BILL-0010`), `GET .../history`, `GET .../export?format=csv|pdf`.
- Änderungen nach Freigabe erzeugen eine neue Version mit erneuter Prüfung und Freigabe;
  die freigegebene Version bleibt unverändert und nachvollziehbar.
- Gate G1 wird nur genehmigt, wenn im Mandanten eine freigegebene Vorlage existiert
  (`MHVP-GATE-0004`, Prüfung in der Gate-Entscheidung `mhvp.platform.routers._decide`).
  Der Antrag bleibt bis dahin offen. Die Freigabe der Vorlage ist keine Öffnung von G1; beide
  Entscheidungen bleiben getrennt (Vier-Augen-Regel des Gates unverändert).
- Zuständig für die Freigabe bleibt der Betreiber mit der Steuerberatung (V8). Das System
  protokolliert die Entscheidung, es trifft sie nicht.
- Tests: `apps/api/tests/integration/test_m18_datev_check_chart_release.py` (Workflow,
  Sperre, neue Version, Gate ohne Freigabe geschlossen, Mandantentrennung).
