# A07 Anschreiben Guthaben/Nachzahlung und Vorauszahlungsvorschlag je Mieter

| Field | Content |
| --- | --- |
| ID | `A07-tenant-letters` |
| Title | Bedienung: Anschreiben für Guthaben/Nachzahlung und neue Vorauszahlungsvorschläge aus dem Abrechnungsergebnis (7.6 A07) |
| Scope | `mhvp.billing.letters`, `mhvp.billing.letter_routers`; Betriebskostenabrechnungen (`statement`, Buchungskreis Vermieter oder SEV-Eigentümer) mit Ergebnis-Snapshot; alle Mandanten; Zustellung hinter G3 |
| Source status | Fachliche Umsetzung (7.6 A07: "Anschreiben für Guthaben/Nachzahlung ... und neue Vorauszahlungsvorschläge bleiben als Funktionen erhalten. Entscheidende Angaben müssen aus freigegebenen Daten stammen."). Keine Rechtsnorm für die Höhe des Vorschlags im Quellenregister; die Anpassung der Vorauszahlung selbst ist ein eigener Vorgang nach § 560 BGB [R08] (A04) und wird hier nicht ausgelöst. Produktschutz (0.1.3, 0.1.6): keine KI-Texte, alle Beträge aus dem Snapshot |
| Acceptance case | keine in annex D; Test `apps/api/tests/integration/test_m17_operating_costs.py::test_a07_tenant_letters_from_snapshot` (Werte von Hand: 1.200,00 nach Wohnfläche 50/50, Mieter 01 mit 700,00 Vorauszahlung Guthaben 100,00, Mieter 02 ohne Vorauszahlung Nachzahlung 600,00, Vorschlag je 50,00; Vorschau einzeln und gebündelt, Ablage als Dokument je Vertrag, Zustellung gesperrt, Mandantentrennung) |
| Implementation | `POST /statements/{id}/letters/preview` (PDF eines Mieters mit `contract_id`, sonst Sammel-PDF in Einheitenreihenfolge), `POST /statements/{id}/letters` (Ablage als Dokument je Mieter, Quelle `generated`, Verknüpfung Vertrag, Einheit, Objekt, Kontakt), `POST /statements/{id}/letters/send` (G3 erforderlich, danach immer 409, Zustellung nicht umgesetzt); Briefbogen `mhvp.documents.letters` (DIN 5008, Firmendaten des Mandanten, ohne Pflichtangaben `MHVP-DOC-0004`) |
| Change reason | Aufgabe A34 (26.09.2026, docs/plans/LUECKENLISTE-2026-09-26.md): Anschreiben waren nicht umgesetzt (M17-05) |

## Regeln

- Alle Beträge des Schreibens stammen aus `statement_snapshot.results` der Abrechnung
  (Kostenanteil, Vorauszahlungen Soll und Ist, Saldo). Es wird nichts nachgerechnet, keine
  KI erzeugt Text; ohne Snapshot (Status Entwurf) gibt es kein Schreiben (409).
- Ergebnis: Saldo größer null ist Nachzahlung, kleiner null Guthaben, null ausgeglichen.
  Beträge im Format 1.234,56 EUR, Daten TT.MM.JJJJ.
- Vorauszahlungsvorschlag: der Master-Prompt hält die Funktion fest, definiert aber keine
  Formel. Bis zur Freigabe einer Regel durch den Betreiber gilt: Kostenanteil des Mieters im
  Abrechnungszeitraum geteilt durch zwölf, kaufmännisch auf den Cent gerundet, im Schreiben
  ausdrücklich als Vorschlag gekennzeichnet ("Vorschlag, Anpassung erfolgt gesondert"). Ein
  Mietverhältnis, das im Abrechnungszeitraum geendet hat, erhält keinen Vorschlag. Ein
  Mietverhältnis, das im Zeitraum begonnen hat, erhält den Vorschlag mit dem Hinweis, dass
  der Nutzungszeitraum kürzer als der Abrechnungszeitraum ist. Die Anpassung der
  Vorauszahlung wird nicht ausgelöst (A04, § 560 BGB).
- Das Schreiben nennt keine Zahlungsfrist, keinen Verzug und keine Rechtsfolgen; es trägt
  immer "Entwurf, kein Versand". Die Sperre einer Nachforderung nach Fristorientierung
  (`late_claim_blocked`, A04) erscheint nicht im Brief, sondern als Hinweis in der Antwort
  der Ablage.
- Vorschau und Ablage sind ab Status `calculated` erlaubt und ändern den Status der
  Abrechnung nicht. Die Zustellung verlangt G3 und ist auch danach gesperrt, bis Zugang und
  Versandweg mit M17-04 freigegeben sind.

## Offene Entscheidung

Formel des Vorauszahlungsvorschlags, Informationsblatt und §-35a-Nachweis (M17-05, Betreiber
mit Steuerberatung); Zustellung und Zugangsnachweis (M17-04).
