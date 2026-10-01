# ADR 0022: Verschachtelung der API Pfade (Abweichung von Abschnitt 12)

- Status: Proposed, Entscheidung des Betreibers offen (AD10-01)
- Date: 02.10.2026

## Context

Abschnitt 12 des Master-Prompts verlangt: "Ressourcen im Plural, verschachtelt höchstens eine
Ebene (`/properties/{id}/units`), sonst Filter (`/contracts?property_id=`)." Befund GB12-01
(Lückenanalyse 3) stellt fest, dass die API davon abweicht und die Abweichung nirgends
festgehalten ist. Dieses ADR hält den Ist-Stand fest, bewertet Alternativen und schlägt eine
Regel für neue Pfade vor. Es ändert keinen Pfad und keinen Code.

### Bestandsaufnahme (Stand 1.59.0, `apps/api/openapi.json`)

Gezählt sind Pfade mit zwei oder mehr Pfadparametern, also Pfade, die unterhalb einer
Ressource mit Kennung eine weitere Ressource oder Aktion mit Kennung adressieren.

| Größe | Wert |
| --- | --- |
| Pfade gesamt | 1.373 |
| Pfade mit zwei oder mehr Pfadparametern | 127 (9,3 Prozent) |
| davon mit zwei Parametern | 123 |
| davon mit drei Parametern | 4 |
| davon endend auf ein Segment (Unterressource, Aktion, Teilansicht) | 78 |
| davon endend auf einen Parameter (Unterressource einzeln) | 49 |
| davon Aktionen mit Verb am Ende (reverse, approve, reject, cancel und ähnlich) | 24 (Näherung nach Endsegment) |

Verteilung nach Bereich: properties 16, contacts 14, portal 13, accounting 11, handover 11,
tickets 10, platform 9, hoa 7, contracts 6, integrations 6, statements 5, letting 4, übrige
je 1 bis 3.

Beispiele nach Art:

* Fachlicher Container: `/accounting/ledgers/{ledger_id}/accounts/{account_id}/sheet`. Der
  Buchungskreis (Ledger) ist die Mandanten und Rechtsträger Trennachse (6.9.1, E01); Konten und
  Buchungen sind ohne ihn nicht eindeutig adressierbar.
* Unterressource mit Eigenleben: `/properties/{property_id}/allocation-keys/{key_id}`,
  `/tickets/{ticket_id}/assignees/{user_id}`.
* Aktion auf einer Unterressource eines Vorgangs:
  `/accounting/ledgers/{ledger_id}/entries/{entry_id}/reverse` (Storno, Regel B07),
  `/contacts/{contact_id}/access-exports/{export_id}/approve` (Vier Augen Freigabe).
* Zuordnung über zwei Kennungen: `/banking/accounts/{bank_account_id}/assignments/{property_id}`.

Die meisten dieser Pfade sind in `apps/web-crm` und `apps/web-portal` in den BFF Allowlists
(`src/app/api/bff/[...path]/route.ts`) und im erzeugten Client (`packages/api-client`)
verdrahtet. Die Verschachtelung ist gewachsen, weil Kennungen innerhalb des Elternobjekts
geprüft werden (RLS und Zugehörigkeit zum Objekt), nicht aus einem einzelnen Entwurf.

## Alternativen

| Variante | Inhalt | Aufwand | Risiko | Bewertung |
| --- | --- | --- | --- | --- |
| A Umbau auf flache Pfade | Alle 127 Pfade auf `/<plural>/{id}` mit Filter umstellen, alte Pfade als Version v1 beibehalten und `/api/v2` einführen (Abschnitt 12: Entfernen nur mit neuer Version) | hoch: 127 Router, Schemas, Client, zwei BFF Allowlists, Tests, Handbuch | hoch: parallele Pflege zweier Versionen, Regression bei Buchhaltung und Freigaben | wirtschaftlich nicht begründet, kein fachlicher Gewinn |
| B Spezifikation anpassen | Abschnitt 12 ändern: "höchstens zwei Ebenen, wenn das Kind ohne Elternkennung nicht eindeutig ist" | gering | gering, aber Änderung des verbindlichen Master-Prompts durch den Betreiber nötig | formal sauber, Regel bleibt aber unscharf |
| C Bestand belassen, Regel für neue Pfade | Bestehende Pfade unverändert (Regel 0.1.12, keine unverlangten Großumbauten). Für neue Pfade gilt die Regel unten; Ausnahmen brauchen eine Begründung im Pull Request | gering | gering | empfohlen |
| D Flache Aliase zusätzlich | Zu jedem tief verschachtelten Pfad ein flacher Alias | mittel, doppelte Pflege | mittel: zwei Wege zum selben Recht, doppelte Berechtigungsprüfung | nicht empfohlen |

## Empfehlung (Variante C)

Bestehende Pfade nicht umbauen. Die Abweichung ist dokumentiert, in der Wirkung begrenzt (9,3
Prozent der Pfade, überwiegend Buchhaltung, Vorgangs und Freigabeaktionen) und ohne
Risikoanstieg für Geld, Recht oder Datenschutz. Ein Umbau würde Buchungs und Freigabepfade
verändern, ohne dass ein Gate, ein Abnahmefall oder ein Anwender davon profitiert.

Regel für neue Pfade (Vorschlag, wirksam erst nach Entscheidung):

1. Standard ist eine Ebene: `/<eltern>/{id}/<kinder>` für Listen und Anlage, flach mit Filter
   (`/<kinder>?<eltern>_id=`) für alles andere.
2. Ein zweiter Pfadparameter ist zulässig, wenn (a) die Kennung des Kindes nur innerhalb des
   Elternobjekts eindeutig ist (zum Beispiel Zuordnung über zwei Kennungen), (b) der Elternteil
   die Trennachse bildet (Ledger, 6.9.1) oder (c) der Pfad eine Aktion auf einem Vorgang
   benennt (`/<kinder>/{id}/<verb>`, höchstens ein Verb am Ende).
3. Drei Pfadparameter sind nicht zulässig.
4. Die Begründung steht in der Beschreibung des Endpunkts und im Pull Request; ein späterer
   Ratchet Test (Baseline 127 Pfade, Zahl darf nicht steigen) kann die Einhaltung prüfen. Er
   ist nicht Teil dieses ADR.

## Konsequenzen

* Keine Code und keine Schemaänderung durch dieses ADR.
* Bis zur Entscheidung gilt Variante C faktisch, neue Pfade folgen der Regel.
* Bei Variante A oder B ist ein eigener Plan unter `docs/plans/` nötig.
* Zuständig für die Entscheidung: Timo Müller. Gate: keines. Offene Frage: AD10-01.
