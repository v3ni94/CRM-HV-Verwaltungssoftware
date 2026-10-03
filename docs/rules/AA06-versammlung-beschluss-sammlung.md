# AA06 Versammlungsarten, Ergebnis je TOP, Stimmkanal, Beschluss-Sammlung, Geltungsdauer Grundlagenbeschluss

Status: technisch umgesetzt am 01.10.2026, fachlich und rechtlich nicht freigegeben.
Migration 0308. Befunde GA03-01, GA03-02, GA03-03, GA03-04, GA07-01 (Lückenliste 01.10.2026).

## Geltungsbereich

Modul `mhvp.hoa` (meetings, meeting_rules, routers, protocol), Eigentümerportal
(`portal/owner_meetings`, nur öffentliche Beschreibung). Kein Geldfluss, betrifft G4.

## Quellenstatus (Anhang C)

* GA03-01 bis GA03-04: Fachliche Umsetzung nach Abschnitt 6.5 (Datenmodell), keine
  Rechtsregel. Die Prüfung `all_owners` zählt Zustimmungen aller am Versammlungstag
  stimmberechtigten Eigentümer; ob ein Gegenstand diese Zustimmung braucht, entscheidet die
  Verwaltung je TOP, das System stellt keine Rechtslage fest.
* GA03-03: Die Status `deleted` und `irrelevant` sind Vermerke in der Beschluss-Sammlung,
  keine physische Löschung. Die Zuordnung des bisherigen Status `void` ist offen (AA06-01).
* GA07-01: Abschnitt 7.8 W13 Satz 4, Einschätzung ohne Gewähr: Der Grundlagenbeschluss für
  virtuelle Versammlungen gilt höchstens drei Jahre. Zu prüfen durch Rechtsanwalt; die
  Übergangsregel des § 48 Abs. 6 WEG ist weder geprüft noch umgesetzt (AA06-02).

## Anforderungstyp

Fachliche Umsetzung; GA03-03 (void) und GA07-01 (Sperre) mit offener Entscheidung,
Eigentümer Timo Müller mit Rechtsanwalt, Gate G4.

## Regel

* Wiederholung und Fortsetzung brauchen eine frühere Ursprungsversammlung derselben GdWE;
  andere Arten dürfen keine haben. Ende nach Beginn. Vorlagen müssen zum Mandanten gehören.
* Ergebnis je TOP: angenommen oder abgelehnt nur durch die Verkündung; vertagt oder ohne
  Abstimmung nur ohne erfasste Stimmen, danach keine Stimme und keine Verkündung (409).
* Abweichendes Stimmprinzip je TOP nur mit dokumentierter Grundlage.
* Stimmkanal: online oder Präsenz aus der Anwesenheit, Umlauf nur im Umlaufverfahren.
* Geltungsdauer: Gültigkeitsende später als Beschlussdatum plus drei Jahre (29.02. wird
  28.02.) ergibt einen Hinweis; Sperre `MHVP-HOA-0030` nur mit Mandantenschalter
  `hoa_virtual_basis_term_lock_enabled` (Standard aus).

## Abnahmefall (Anhang D)

Kein eigener D-Fall; Testfälle `tests/integration/test_aa06_meeting_resolution.py`,
`tests/unit/test_aa06_virtual_basis_term.py`. Erwartung von Hand: zwei Eigentümer, einer
stimmt online mit Ja, einer fehlt: `all_owners` negativ (1 von 2). Beschluss vom 01.03.2026:
spätestes Gültigkeitsende 01.03.2029.

## Änderungsgrund

Lückenliste 01.10.2026, Paket AA06 (Welle 12).

## Nachtrag AB06 (01.10.2026)

* GA03-01: Wiederholungs- und Fortsetzungsversammlungen sind im CRM anlegbar (Auswahl der Ursprungsversammlung derselben GdWE, Pflicht), Vorlagen werden aus der Liste der aktiven Vorlagen gewählt. Das Portal zeigt nur die öffentliche Beschreibung, nie die interne.
* GA07-01: Der Hinweis zum Gültigkeitsende über drei Jahre nach Beschlussdatum erscheint dauerhaft in `GET /hoa/meetings/{id}` und in der CRM-Detailansicht. Die Sperre MHVP-HOA-0030 bleibt hinter dem Mandantenschalter (Standard aus). Offen: AA06-02, G4.
* GA03-03 bleibt teilweise offen (AA06-01, Status void).
* Änderungsgrund: Folgearbeit aus Welle 12 (Abnahmefall unverändert).

## Nachtrag 03.10.2026 (GAM-809): Pflichtfelder des Regelformats

| Feld | Inhalt |
| --- | --- |
| ID | AA06 |
| Geltungsbereich | siehe Abschnitt Geltungsbereich oben (Modul `mhvp.hoa`, Eigentümerportal, betrifft G4) |
| Quellenstatus | siehe Abschnitt Quellenstatus (Anhang C) oben, fachlich und rechtlich nicht freigegeben |
| Abnahmefall | siehe Abschnitt Abnahmefall (Anhang D) oben, `apps/api/tests/integration/test_aa06_meeting_resolution.py` |
| Änderungsgrund | siehe Abschnitt Änderungsgrund oben |
