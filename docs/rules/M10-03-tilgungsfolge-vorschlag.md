# M10-03 Ausgleich offener Posten nach gesetzlicher Reihenfolge (nur Vorschlag)

| Field | Content |
| --- | --- |
| ID | `M10-03` |
| Title | Ohne Tilgungsbestimmung des Zahlers schlägt die Plattform den Ausgleich offener Posten in der gesetzlichen Reihenfolge vor; sie wendet ihn nie selbst an. Eine ausdrückliche Bestimmung des Zahlers geht immer vor (D39) |
| Scope | Domäne `accounting`, Debitoren (Forderungen) je Buchungskreis; Endpunkte `POST /accounting/ledgers/{id}/open-items/settlement-proposal` und `.../settlement-proposal/confirm`; alle Mandanten |
| Source status | Rechtsgrundlage: Tilgungsbestimmung des Schuldners und gesetzliche Tilgungsfolge nach dem BGB (Quellenregister Anhang C, R09: §§ 366, 367 BGB), Master-Prompt 7.4 Nr. 5. Die konkrete Rangfolge in dieser Regel ist die Umsetzung der Betreiberentscheidung vom 26.09.2026; ihre rechtliche Prüfung durch die Rechtsberatung ist vor G1 offen (Vermerk im Vorschlag). Vertragliche Besonderheiten (abweichende Tilgungsvereinbarungen) werden nicht ausgewertet |
| Acceptance case | Anhang D39 (eindeutige Tilgungsbestimmung widerspricht freier Kontenpriorität), D07 (Überzahlung bleibt Guthaben). Tests `apps/api/tests/unit/test_settlement_order.py` (handgerechnete Reihenfolgen), `apps/api/tests/integration/test_m10_03_settlement_proposal.py` (API, Bestätigung, Mandantentrennung, G1) |
| Implementation | `mhvp.accounting.settlement` (`propose`, `statutory_key`, `items_for`, `determination_from_purpose`, `RULE_VERSION = "1"`), Routen in `mhvp.accounting.routers`, CRM `SettlementProposalPanel`; keine Migration, Bestätigung als Domänenereignis `open_item_settlement.proposal_confirmed` mit Regelversion und Fingerabdruck |
| Owner | Rechtsberatung (fachliche Freigabe der Rangfolge vor G1), Betreiber |
| Change reason | Betreiberentscheidung 26.09.2026 zu M10-03: Vorschlag mit Freigabe statt keiner Tilgungsfolge |

## Regeln

- **Nur Vorschlag.** Der Endpunkt `settlement-proposal` berechnet deterministisch und schreibt
  nichts. Jeder Vorschlag trägt den Vermerk „Vorschlag nach gesetzlicher Reihenfolge,
  Rechtsprüfung vor G1 offen“, die Regelkennung, die Regelversion und einen Fingerabdruck
  über Betrag, Stichtag und alle Ausgleichszeilen.
- **Bestimmung des Zahlers geht vor (D39).** Eine ausdrückliche Bestimmung (Liste
  `determination` mit Posten und optionalem Betrag, sonst aus dem Verwendungszweck über den
  deterministischen Parser des Bankabgleichs, M12-03: Sollstellungs- oder Rechnungsnummer,
  Monat oder Quartal) wird zuerst und in der angegebenen Reihenfolge ausgeglichen, Grund
  „Bestimmung des Zahlers“. Nur ein Rest ohne Bestimmung folgt der gesetzlichen Reihenfolge
  (Grundlage `mixed`). Eine Bestimmung auf einen unbekannten Posten wird abgewiesen, nicht
  still umgedeutet.
- **Gesetzliche Reihenfolge (Regelversion 1).** Sortierschlüssel, kleiner zuerst:
  1. fällige Posten (Fälligkeit bis Stichtag) vor nicht fälligen;
  2. geringere Sicherheit zuerst (auf offenen Posten sind keine Sicherheiten hinterlegt, alle
     Posten gelten insoweit als gleichrangig, siehe offene Punkte);
  3. der lästigere Posten zuerst (Posten in einem versandten Mahnvorgang);
  4. der ältere zuerst (Fälligkeitsdatum, dann Buchungsdatum);
  5. innerhalb desselben Rangs Kosten (Buchungsart `dunning_fee`) vor Zinsen (`interest`)
     vor Hauptforderung;
  6. zuletzt die Kennung des Postens, damit zwei Läufe stets dasselbe Ergebnis liefern.
- **Überzahlung ist Guthaben, kein Ertrag (D07).** Ein nicht zuordenbarer Rest bleibt im
  Vorschlag als `unallocated` ausgewiesen und bei Bestätigung als Haben auf dem
  Personenkonto; es entsteht kein Ertrags- oder Ausgleichssatz dafür.
- **Bestätigung durch eine Person mit Buchungsrecht.** `confirm` verlangt dieselbe
  Berechtigung wie der bestehende ausdrückliche Ausgleich (`accounting:create`), rechnet den
  Vorschlag neu und vergleicht den Fingerabdruck; bei Abweichung (Posten oder Regelversion
  haben sich geändert) wird mit 409 abgewiesen. Die Bestätigung erzeugt einen Entwurf
  (`debtor_payment`, Bank an Personenkonto) mit ausdrücklichem Ausgleichsplan und schreibt das
  Ereignis `open_item_settlement.proposal_confirmed` mit Regel, Regelversion, Grundlage,
  Fingerabdruck und allen Zeilen (Rang, Betrag, Grund) in das Ereignisprotokoll.
- **G1 gilt für jede Buchung.** Das Buchen des Entwurfs läuft über den bestehenden Weg
  (Journal, `POST .../entries/{id}/post`, nicht führender Buchungskreis) und bleibt für die
  produktive Buchführung hinter G1. Das sofortige Buchen aus der Bestätigung
  (`post_immediately`) ist nur mit offener Freigabestufe G1 möglich, sonst
  `MHVP-GATE-0001`; nichts wird geschrieben.
- **Keine Automatik.** Weder Import, Job, Massenaktion noch KI wendet den Vorschlag ohne
  Bestätigung an (0.1.6, 7.4 Nr. 4). Die Bankautomatik (`mhvp.banking.matching.auto_post`)
  ist unverändert und nutzt diese Regel nicht.

## Offene Punkte

- Rechtsprüfung der Rangfolge und der Behandlung vertraglicher Tilgungsvereinbarungen durch
  die Rechtsberatung vor G1 (`docs/OPEN_QUESTIONS.md`, M10-03).
- Sicherheiten je Forderung sind nicht erfasst; das Kriterium „geringere Sicherheit“ ist
  vorbereitet (`ProposalItem.security`), aber ohne Datenquelle.
- Anbindung an den Bankabgleich (Vorschlag direkt aus einem Bankumsatz) ist nicht Teil dieser
  Regel; dort gilt weiterhin M12-03 (manuelle Prüfung bei mehreren Posten).
