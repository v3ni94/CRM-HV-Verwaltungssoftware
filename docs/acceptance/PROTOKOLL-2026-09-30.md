# Abnahmeprotokoll Stand 30.09.2026, Paket P08 (Prüfung und Einsicht)

Format nach `docs/acceptance/PROTOKOLL-2026-09-26.md`. Aufgabe: Lückenliste 30.09.2026, Nummern SD-03 bis SD-07. Arbeitsstand 1.47.0, Branch claude/funny-cerf-ppg9in, Migration 0257.

Geltung: Dokumentation der technischen Testausführung, keine fachliche Abnahme. Bestätigung der Sollwerte durch die fachkundige Person (V16) und Rechtsprüfung (R01, R06, R25) sind offen. Alle Freigabestufen G1 bis G5 bleiben geschlossen. Alle Eingaben sind synthetische Modellwerte.

Gesamtergebnis: Die Tests sind geschrieben, aber zum Zeitpunkt der Erstellung NICHT AUSGEFÜHRT. Grund: Der gemeinsame Arbeitsbaum war nicht importierbar (fremde, noch unfertige Änderungen in `mhvp/accounting/models.py`, zuletzt `NameError: name 'Contract' is not defined`) und die Migrationskette hatte eine Lücke (0250 fehlte, Vorgänger von 0257 ist 0256). Ausführung und Ergebnis sind nachzutragen.

Sammelbefehl:

```
cd apps/api && uv run pytest \
  tests/integration/test_p08_sd_portal.py \
  tests/integration/test_p08_hoa_audit_inspection.py \
  -q --no-cov -p no:cacheprovider
```

## Übersicht

| Kennung | Regel | Test | Ergebnis Test | Status Fall |
| --- | --- | --- | --- | --- |
| SD-03 | PÜ10 | `test_p08_sd_portal.py::test_sd03_pue10_owner_right_is_no_board_privilege` | nicht ausgeführt | offen |
| SD-04 | PÜ11 | `test_p08_sd_portal.py::test_sd04_pue11_tenant_receipt_inspection_with_redaction` | nicht ausgeführt | teilweise vorgesehen (Erzeugung geschwärzter Kopien fehlt, P08-01) |
| SD-05 | PÜ12 | `test_p08_hoa_audit_inspection.py::test_package_index_outside_portal_sd05` | nicht ausgeführt | teilweise vorgesehen (Portalsuche, Sortierung, Sammel-Download fehlen, P08-03) |
| SD-06 | W13 | `test_p08_hoa_audit_inspection.py::test_audit_filters_history_confirmation_and_authorization` (Abschnitt SD-06) | nicht ausgeführt | offen |
| SD-07 | PÜ13 | `test_p08_hoa_audit_inspection.py::test_package_expiry_and_revocation_sd07` | nicht ausgeführt | teilweise vorgesehen (Benachrichtigung und Eigentümerwechsel fehlen, P08-02) |

## Fallbeschreibung und Sollwerte

* SD-03: Eigentümer ohne Beiratsrolle sieht Beschluss, Protokoll und Wirtschaftsplan der eigenen GdWE außerhalb seiner Einzelabrechnung; fremde GdWE, SEV-Akten und fremde Vertragsakten liefern 404. Regelstand: `docs/rules/` ohne eigene PÜ10-Regel, Verweis D29, D30.
* SD-04: Mieter der Abrechnung sieht genau die freigegebene Fassung des Belegs mit Schwärzungshinweis, nie das Original; Nachbar sieht nichts; Original bleibt mit Rolle generated verknüpft.
* SD-05: Paket mit Index (JSON und CSV, SHA-256 je Datei) ohne Portal erzeugbar; Dokument einer anderen Gemeinschaft wird namentlich abgewiesen (422).
* SD-06: Prüfauftrag ohne Beiratskonto und ohne Nachweis möglich (kein Beirat wird erfunden); Prüfbericht und Bestätigung erzeugen keinen Eintrag in der Beschluss-Sammlung (Sollwert: leere Liste), Status des Prüfauftrags bleibt open.
* SD-07: Verlauf Antrag, Freigabe, Paket, Rückfrage, Antwort, Bereitstellung, Abruf in genau dieser Reihenfolge; Abruf mit Leserecht lässt den Status auf provided; kein Status acknowledged oder accepted; nach Widerruf 409 (alte Freigabe eröffnet keine dauernde Einsicht).

## Auffälligkeiten

* Eine formale Regelversion fehlt wie im Protokoll vom 26.09.2026; Regeldatei `docs/rules/P08-pruefung-einsicht.md`.
* SD-04, SD-05 und SD-07 decken die Anforderung nur teilweise ab, die Lücken stehen in `docs/OPEN_QUESTIONS.md` (P08-01 bis P08-03).
