# P08 Beiratsprüfung und Einsicht: Verlauf, Bestätigung, Befristung

Status: technisch umgesetzt am 30.09.2026, fachlich nicht freigegeben. Migration 0257.

## Geltungsbereich

Modul `mhvp.hoa` (Prüfauftrag, Prüfposition, Prüfbericht, Einsichtsanfrage). Kein Geldfluss,
keine Buchung. Anforderungstyp: Fachliche Umsetzung (PÜ06 bis PÜ09, PÜ13) und Produktschutz.

## Quellenstatus (Anhang C)

PÜ06 bis PÜ13 sind Anforderungen der Spezifikation (7.9.2). Rechtsgrundlagen R01 (§ 18 WEG)
und R25 (DSGVO) sind nicht geprüft. Die Dauer einer Befristung ist eine Produktleistung und
keine Rechtsfrist; sie ist zu prüfen durch Rechtsanwalt, ob und wie lange Einsicht gewährt werden muss.

## Regeln

* P08-01 Prüfauftrag speichert Berechtigungsnachweis (`authorization_text`, Beschluss oder
  Auftrag, Freitext) und Datenstand (`data_as_of`, Standard heutiges Datum) und weist beides im
  Prüfbericht aus (M25-08, PÜ06). Es wird kein Beirat erfunden: der Nachweis ist optional.
* P08-02 Prüfpositionen sind filterbar nach Betrag von/bis, fehlendem Beleg, Risikohinweis und
  Prüfstatus (`GET /hoa/audits/{id}`); der Gesamtstatus hängt nie vom Filter ab (M25-02, PÜ08).
  Der Risikohinweis ist ein Vermerk der Prüfenden und keine automatische Bewertung.
* P08-03 Jede tatsächliche Änderung von Status, Vermerk, Rückfrage, Antwort oder Risikohinweis
  erzeugt eine Zeile in `audit_item_event` mit altem und neuem Wert, Person und Zeitpunkt;
  eine Änderung auf denselben Wert erzeugt keine Zeile und erhöht die Version nicht (M25-05).
* P08-04 Ein Prüfbericht kann je Version einmal bestätigt werden (Name, Zeitpunkt, Benutzer,
  Anmerkung). Die Bestätigung ändert den Bericht nicht, erzeugt keinen Beschluss, keine
  Entlastung und keine Zahlungsfreigabe (M25-03, PÜ09, W13).
* P08-05 Ein Bereitstellungspaket kann mit `valid_days` (1 bis 365) befristet werden. Nach
  Ablauf oder Widerruf (`POST /hoa/inspection-requests/{id}/revoke`, Ereignis `revoked`) ist der
  Abruf mit 409 gesperrt; ein neues Paket hebt die Sperre auf. Ein Abruf mit reinem Leserecht
  ist keine Anerkennung (PÜ13, M25-07).

## Abnahmefälle

SD-05, SD-06, SD-07 in `tests/integration/test_p08_hoa_audit_inspection.py`, SD-03 und SD-04 in
`tests/integration/test_p08_sd_portal.py`. Protokoll: `docs/acceptance/PROTOKOLL-2026-09-30.md`.

## Änderungsgrund

Lückenliste 30.09.2026, Befunde M25-02, M25-03, M25-05, M25-07, M25-08.

## Offen

Benachrichtigung als eigenes Ereignis und Prüfung bei Eigentümerwechsel (M25-07), geschwärzte
Belegkopien (M25-01), Navigation mit Vertrags- und Vorjahresdaten (M25-04), Portalsuche und
Sammel-Download (M25-06): siehe `docs/OPEN_QUESTIONS.md` (P08-01 bis P08-03).

## Nachtrag R05 (01.10.2026): Standardfrist der Einsichtspakete, Migration 0287

* P08-06 Die Standardfrist der Bereitstellung ist eine Mandanteneinstellung
  (`tenant_settings.inspection_package_default_days`, 1 bis 365 Tage, leer bedeutet ohne Ablauf).
  Sie gilt nur, wenn beim Erzeugen eines Pakets weder `valid_days` noch `no_expiry` angegeben
  ist. `valid_days` überschreibt die Standardfrist, `no_expiry=true` hebt sie für dieses eine Paket
  auf. Bereits erzeugte Pakete behalten ihre Frist. Änderungen stehen im Ereignis
  `tenant_settings.updated`. Der Vorschlag 14 Tage aus P08-02 ist nicht voreingestellt; die Frist
  ist eine Produktleistung und keine Rechtsfrist (Quellenstatus wie oben, Prüfung durch
  Rechtsanwalt offen). Abnahmefall: `tests/integration/test_r05_positive_paths.py`.
