# Runbook: FinTS-Betrieb (Bankanbindung PIN/TAN)

Beleg: `apps/api/src/mhvp/banking/fints.py`, `fints_routers.py`, `tasks.py`; fachliche
Beschreibung und Betreiberentscheidung in `docs/integrations/fints.md`. Nur lesend, Gate G2
bleibt geschlossen. Rückmeldecodes der Banken sind Einschätzungen aus dem Code und der
Bankantwort; im Zweifel gilt die Auskunft der Bank.

## 1. Einrichtung und Produktregistrierung

- Die Registrierungsnummer der Deutschen Kreditwirtschaft kommt als `MHVP_FINTS_PRODUCT_ID`
  in die Umgebung (`core/config.py:262`), optional `MHVP_FINTS_PRODUCT_VERSION` (Standard `1.0`).
- Ohne ID liefert die API `MHVP-BANK-0007` (501, `problems.py:535`), `GET
  /api/v1/banking/fints/config` meldet `configured: false` (`fints_routers.py:64`, `:396`) und
  das CRM zeigt statt der Schaltfläche den Hinweis. Die Prüfung steht in `_require_product_id`
  (`fints_routers.py:309`).
- Die DK verteilt neue Nummern an die Banken erst nach mehreren Werktagen
  (Kommentar `fints.py:431`ff.). Frisch registrierte IDs können in dieser Zeit mit 9010
  scheitern, ohne dass ein Fehler bei uns vorliegt.
- Die Nummer gehört nicht in den Code und nicht in Tickets.

## 2. Institutsliste und FinTS-Adresse

- Die Institutssuche (`GET .../institutes?q=`) nennt nur Institute mit FinTS-URL als
  `connectable`; sonst `MHVP-BANK-0008` (`fints_routers.py:431`).
- Falsche oder veraltete Adresse: `PATCH .../connections/{id}` setzt die FinTS-URL
  (`fints_routers.py:505`ff.). Adressen mit Ziel im internen Netz lehnt der Code mit
  `MHVP-BANK-0062` ab, ohne Verbindung und ohne PIN-Versand (`problems.py:607`).

## 3. Der Fall Rückmeldecode 9010

Meldung im CRM: "Die Bank hat den Dialog nicht eröffnet (Rückmeldecode 9010)." mit
`MHVP-BANK-0014` (502). Ursprung: python-fints meldet bei 9010 in der Dialoginitialisierung nur
"could not fetch BPD"; `is_dialog_init_rejection` (`fints.py:391`) erkennt das, die Abbildung
steht in `problem_for_exception` (`fints.py:431`ff.).

Was die Software selbst tut (`fints.py:983`ff.): Lag ein gespeicherter Dialogzustand vor
(System-ID, Bankparameter, TAN-Registrierung) und lehnt die Bank ihn mit 9010 ab, wird er
verworfen und der Dialog genau einmal frisch eröffnet (Logeintrag
`fints_dialog_init_rejected_with_stored_state ... retry=fresh_state`). Danach kann die Bank
erneut eine TAN verlangen (SCA).

Prüfschritte bei bleibendem 9010, in dieser Reihenfolge:

1. Text der Bank in der Fehlermeldung lesen; falls vorhanden steht er hinter "Rückmeldung der
   Bank" (`fints.py:385`ff.).
2. FinTS-Adresse der Verbindung mit der Angabe der Bank vergleichen und passend zur
   Bankleitzahl setzen (Abschnitt 2). Nach einer Bankfusion ändern sich BLZ und Adresse.
3. Produktregistrierung prüfen: Wie lange liegt die Zuteilung zurück? Bei weniger als einigen
   Werktagen später erneut versuchen. Bei der Bank oder der DK erfragen, ob die Nummer dort
   bekannt ist.
4. Verbindung neu starten (`POST .../connections/{id}/restart`, PIN neu eingeben). Das
   erzwingt einen frischen Dialogzustand.
5. Vorübergehende Störung bei der Bank ausschließen (später erneut, kein Dauerversuch).
6. Hilft nichts: Verbindungsdatensatz, Zeitpunkt, BLZ, Fehlercode und Bankmeldung dem Betreiber
   melden. Keine PIN und keine TAN weitergeben.

Wichtig: Nicht mehrfach in kurzer Folge neu starten. Wiederholte Fehlversuche können den Zugang
bei der Bank sperren (siehe Abschnitt 4).

## 4. PIN abgelehnt, Zugang gesperrt, TAN, SCA

| Code | Bedeutung | Reaktion im System | Maßnahme |
| --- | --- | --- | --- |
| `MHVP-BANK-0009` PIN abgelehnt (9340, 9910, 9930, 9931, 9942 laut `fints.py:268`) | Anmeldename oder PIN falsch | gespeicherte PIN verworfen, `pin_blocked` gesetzt (`tasks.py:1170`ff.) | im Online-Banking prüfen, dann PIN neu eingeben |
| `MHVP-BANK-0010` Zugang gesperrt (3938, 9931, `fints.py:269`) | Bank hat gesperrt | wie oben, kein Wiederholversuch | Sperre bei der Bank aufheben lassen (Prüfschritte `fints.py:274`ff.) |
| `MHVP-BANK-0016` PIN gesperrt | PIN wird nach Fehlversuch nicht wiederverwendet (`fints_routers.py:494`, `:682`) | Aktion abgelehnt | PIN neu eingeben (Restart) |
| `MHVP-BANK-0011` TAN abgelehnt | falsche oder abgelaufene TAN | Sitzung `failed` | Schritt mit neuer TAN wiederholen |
| `MHVP-BANK-0012` SCA nötig (9075) | starke Kundenauthentifizierung, meist alle 90 Tage | Verbindung `UPDATE_REQUIRED` (`tasks.py:1179`) | neue TAN-Sitzung starten |
| `MHVP-BANK-0013` nicht erreichbar | Netz oder Bankserver | Fehlermeldung mit Host | später erneut |
| `MHVP-BANK-0057` Warteschlange | Redis oder Worker nicht erreichbar | Auftrag nicht eingereiht | Redis und Worker der Queue `bank` prüfen (`incident.md`, `skalierung.md`) |

Nach einem gesperrten Zugang kein automatischer zweiter Versuch: drei Fehler sperren den
Zugang bei der Bank (`problems.py` zu `MHVP-BANK-0016`).

## 5. Laufender Betrieb

- Jeder Schritt läuft im Celery-Worker, Queue `bank` (Mandanten-RLS in `bank_fints_session`).
  Bei Split-Workern muss `worker-bank` laufen (ADR 0029).
- Hängende Sitzungen: offene Sitzung blockiert einen neuen Start (`MHVP-BANK-0015`,
  `fints_routers.py:347`). Status in der Sitzung prüfen, Blobs werden bei `done` und `failed`
  gelöscht.
- Zugangsdaten und PIN sind mandantenverschlüsselt; PIN wird nicht protokolliert.
- Rechtsträgerzuordnung der Konten (`POST .../accounts/{id}/assign`) vor dem ersten Abruf
  prüfen; Bankguthaben gehören dem jeweiligen Rechtsträger.
