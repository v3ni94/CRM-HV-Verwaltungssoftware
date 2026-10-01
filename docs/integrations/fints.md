# FinTS/HBCI PIN/TAN (M11-01 Nachtrag, Betreiberentscheidung 27.09.2026)

Direkte Bankanbindung per FinTS 3.0 (HBCI) mit PIN/TAN, zusätzlich zu finAPI. Umsetzung in
`apps/api/src/mhvp/banking/fints.py` (Workflow), `fints_routers.py` (Endpunkte),
`tasks.py` (`mhvp.banking.fints_step`, Queue `bank`), Migration 0161. Bibliothek
`python-fints` (PyPI `fints`, Version 4.x, gepinnt in `uv.lock`). Nur lesend: Konten,
Salden, Umsätze. Keine Zahlungsauslösung, Gate G2 bleibt geschlossen.

## Betreiberentscheidung

Bankanbindung per FinTS/HBCI direkt (PIN/TAN) neben finAPI. Gewünschter Ablauf unter Bank:
Bank verbinden, BLZ/BIC/IBAN eingeben, Bank wird erkannt, Anmeldename und PIN, TAN-Verfahren
und TAN-Freigabe (pushTAN/decoupled mit Abfrage, chipTAN/photoTAN mit Challenge), Konten
laden, Konten Rechtsträger und Objekt zuordnen, Umsätze und Salden per Klick aktualisieren.

## Voraussetzungen (Betreiber)

1. **Produktregistrierung bei der Deutschen Kreditwirtschaft (DK).** Seit FinTS 3.0
   (Pflicht ab 2019/2020) muss jedes Produkt, das den FinTS-Zugang nutzt, bei der DK
   registriert sein. Der "Antrag auf Produktregistrierung" ist kostenlos
   (Formular auf der Seite der Deutschen Kreditwirtschaft, Rubrik FinTS). Die DK
   vergibt eine Registrierungsnummer (Produkt-ID). Ohne diese ID lehnen die Banken den
   Dialog ab und `python-fints` startet keinen Dialog.
2. Die Registrierungsnummer wird als `MHVP_FINTS_PRODUCT_ID` gesetzt (siehe
   `infra/env.prod.example`), optional `MHVP_FINTS_PRODUCT_VERSION` (Standard `1.0`).
   Ohne gesetzte ID antwortet die API mit `MHVP-BANK-0007` (501) und die Oberfläche zeigt
   den Hinweis. Die ID ist kein Geheimnis im Sinne einer PIN, gehört aber nicht in Code.
3. Online-Banking-Zugang des Kontoinhabers (Anmeldename, PIN, freigeschaltetes
   TAN-Verfahren). Der Zugang gehört dem jeweiligen Rechtsträger (WEG, Vermieter); die
   Hausverwaltung nutzt ihn nur im Rahmen ihrer Vollmacht.

## Ablauf und Zustandsautomat

`python-fints` ist synchron und blockierend. Jeder Schritt läuft deshalb im Celery-Worker
(Queue `bank`), der Zustand liegt in `bank_fints_session` (RLS je Mandant):

| Status | Bedeutung |
| --- | --- |
| `queued` | Schritt eingereiht, Worker noch nicht gestartet |
| `running` | Worker spricht mit der Bank (keine Datenbanktransaktion offen währenddessen) |
| `awaiting_tan` | Bank verlangt eine TAN: Challenge-Text, HHD-Startcode (chipTAN) oder Bild (photoTAN) liegen in der Sitzung |
| `awaiting_decoupled` | pushTAN/decoupled: Freigabe in der Bank-App, Abfrage per `POST .../tan` ohne TAN (Oberfläche alle 5 Sekunden) |
| `done` | Konten, Salden und ggf. Umsätze übernommen, alle Blobs gelöscht |
| `failed` | Fehler mit registriertem Code (`error_code`), Blobs gelöscht |

Pause und Wiederaufnahme nutzen die Mittel von `python-fints`: `client.pause_dialog()`
(Dialog einfrieren), `client.deconstruct(including_private=True)` (Client-Zustand mit
System-ID, BPD/UPD und Kontonummern), `NeedTANResponse.get_data()` (offene TAN-Anfrage);
später `FinTS3PinTanClient(from_data=...)`, `client.resume_dialog(dialog_data)` und
`client.send_tan(NeedRetryResponse.from_data(...), tan)`. Verlangt die Bank mitten in der
Arbeit eine TAN (etwa je Umsatzabruf), merkt sich `Progress` Konto und Stufe und macht
nach der TAN genau dort weiter.

Endpunkte (`/api/v1/banking/fints`, alle im OpenAPI-Export):

| Methode | Pfad | Recht | Zweck |
| --- | --- | --- | --- |
| GET | `/institutes?q=` | `accounting:read` | Institutssuche (BLZ, BIC, IBAN, Namensfragment), max. 20 Treffer, `connectable` nur mit FinTS-URL |
| POST | `/connections` | `banking:approve` | Verbindung anlegen (Institut, Anmeldename, PIN, optional TAN-Verfahren), startet Sitzung |
| POST | `/connections/{id}/restart` | `banking:approve` | Neue Sitzung: PIN erneut eingeben, TAN-Verfahren wechseln, erneute Freigabe |
| PATCH | `/connections/{id}` | `banking:approve` | FinTS-Adresse der Verbindung von Hand setzen (mit erneuter PIN) oder mit `fints_url: null` auf die Institutsliste zurücksetzen, startet keinen Dialog |
| GET | `/connections` | `accounting:read` | Verbindungen mit Konten (nicht zugeordnete Konten nur mit `banking:approve`) |
| GET | `/sessions/{id}` | `accounting:read` | Status, Challenge, TAN-Verfahren, Fehler |
| POST | `/sessions/{id}/tan` | `banking:approve` | TAN senden oder decoupled-Freigabe abfragen |
| POST | `/connections/{id}/refresh` | `accounting:update` | Salden aller Konten, Umsätze der zugeordneten Konten (ab Stand minus 3 Tage, erstmals 89 Tage), ggf. erneut TAN |
| POST | `/accounts/{link_id}/assign` | `banking:approve` | Konto einem internen Konto zuordnen (IBAN muss übereinstimmen) oder neues internes Konto für Objekt und Rechtsträger anlegen |
| DELETE | `/connections/{id}` | `banking:approve` | Trennen: PIN, Client-Zustand und Sitzungen löschen, Verbindung `disabled` |

Umsätze kommen als MT940 (`get_transactions`) und laufen durch die bestehende
Normalisierung des `:86:`-Felds (`mhvp.banking.mt940.parse_info`) und die bestehende
Dublettenregel (Bankreferenz `fints:<Ref>` vorrangig, ohne Bankreferenz ein aus Buchungstag,
Betrag, Kundenreferenz und `:86:` abgeleiteter Schlüssel; Inhalts-Hash nur als
Prüfhinweis, D05, `services.import_finapi_transactions`).

## Sicherheit

- Anmeldename, PIN und Client-Zustand liegen verschlüsselt mit dem Master-Key
  (`EncryptedText`, wie Postfach-Secrets). Die PIN wird nie in einer Antwort ausgegeben,
  nie protokolliert (`python-fints` maskiert sie als `Password`, der Logger `fints` läuft
  auf WARNING) und nie in einen Blob geschrieben.
- Eine eingegebene TAN liegt nur bis zum nächsten Worker-Schritt verschlüsselt in der
  Sitzung und wird danach gelöscht.
- Sperrverhalten: nach einer Ablehnung von Anmeldename oder PIN (Rückmeldecodes 9340,
  9910, 9930, 9931, 9942, Sperre 3938) wird die gespeicherte PIN verworfen
  (`pin_blocked`), es gibt keinen automatischen zweiten Versuch. Die Bank sperrt den
  Zugang nach drei Fehlversuchen; die Oberfläche weist darauf hin und verlangt die PIN neu.
- PSD2: starke Kundenauthentifizierung ist spätestens alle 90 Tage erneut nötig. Die
  Oberfläche zeigt "Freigabe gültig bis" und einen Hinweis, wenn die Bank eine erneute
  Freigabe verlangt (`MHVP-BANK-0012`, Verbindung `update_required`).
- Challenge-Bilder (photoTAN) werden nur zur Anzeige gehalten und mit Abschluss der
  Sitzung gelöscht.

## Fehlercodes (ADR 0004)

| Code | HTTP | Bedeutung |
| --- | --- | --- |
| MHVP-BANK-0007 | 501 | Produktregistrierung fehlt (`MHVP_FINTS_PRODUCT_ID` leer) |
| MHVP-BANK-0008 | 422 | Institut ohne FinTS-URL in der Liste |
| MHVP-BANK-0009 | 502 | Bank hat Anmeldename oder PIN abgelehnt (9340, 9910, 9930, 9931, 9942) |
| MHVP-BANK-0010 | 502 | Zugang gesperrt (3938, 9931), Meldung deutsch mit fünf Prüfschritten |
| MHVP-BANK-0011 | 502 | TAN abgelehnt (9941 ff) |
| MHVP-BANK-0012 | 409 | Erneute Freigabe nötig (9075, PSD2) |
| MHVP-BANK-0013 | 503 | Bank nicht erreichbar (Verbindung, Zeitüberschreitung, SSL), Meldung nennt den Rechnernamen und vier Prüfschritte |
| MHVP-BANK-0014 | 502 | Sonstige Ablehnung (9xxx) mit Banktext |
| MHVP-BANK-0015 | 409 | Sitzung oder Verbindung im falschen Zustand (auch abgelaufene Sitzung nach 15 Minuten) |
| MHVP-BANK-0016 | 409 | PIN nach Fehlversuch gesperrt, neue Eingabe nötig |

## Institutsliste

`apps/api/src/mhvp/banking/data/fints_institutes.txt`, je Zeile
`BLZ=Name|Ort|BIC|Prüfziffer|HBCI-Domain|FinTS-URL|HBCI-Version|FinTS-Version|`. Die Liste
wird extern gepflegt (Stand der Übernahme: 29.09.2026, Liste der Deutschen Kreditwirtschaft vom 20.08.2026 (Registrierungsmail vom 28.09.2026), 4062 Institute, davon 2721 mit
FinTS-URL; die DK-Datei selbst führt 1738 Bankleitzahlen in 4788 Standortzeilen, davon 3537 mit URL). Die Aktualisierung ist eine Betriebsaufgabe: neue Datei einspielen (Skript unten), Tests
laufen lassen, ausliefern. Die Bundesbank veröffentlicht die BLZ-Datei quartalsweise; die
FinTS-URLs stammen aus der Liste der DK bzw. der jeweiligen Bank. Ein Institut ohne
FinTS-URL ist nicht verbindbar (`MHVP-BANK-0008`).

Altadressen der Rechenzentren: Die DK-Liste nennt bei rund 590 Genossenschaftsbanken noch die
abgeschalteten Hosts `hbci-pintan.gad.de` (GAD) und `hbci11.fiducia.de` (Fiducia), während
die Spalte HBCI-Domain bereits den Atruvia-Host (`fints1.atruvia.de` oder
`fints2.atruvia.de`) führt. Der Parser baut die URL in diesem Fall aus der Domain-Spalte
(`https://<domain>/cgi-bin/hbciservlet`). Geprüft am 01.10.2026: beide Althosts lehnen die
Verbindung ab, beide Atruvia-Hosts antworten. Betreiberbefund: Heinsberger Volksbank
(39061981). Fusionen (zum Beispiel Aachener Bank eG und Volksbank Heinsberg eG zur
Volksbank im Westen eG) ändern Bankleitzahl oder Anmeldename erst mit der technischen
Fusion; bis zur nächsten DK-Liste gilt die Angabe der Bank, Umstellungshinweise der Bank
beachten.

### Institutsliste aktualisieren (Skript)

Die DK stellt die Liste als Excel-Datei und als CSV bereit ("fints_institute ... Master",
Semikolon, Windows-1252). Liegt nur die Excel-Datei vor, in Excel als CSV (Trennzeichen
Semikolon) speichern. Dann im Repository:

1. Trockenlauf: `python3 scripts/update_fints_institutes.py --dk-csv "<Datei>.csv"`.
   Der Bericht nennt aktualisierte, neue und unveränderte Zeilen, die Zahl der Zeilen mit
   Altadresse (GAD, Fiducia) und Warnungen (URL nicht https, doppelte Bankleitzahl mit
   verschiedenen URLs).
2. Bericht lesen. Das Skript verweigert das Schreiben, wenn die Datei weniger als 500
   Institute enthält (falsche Datei) oder mehr als 10 Prozent der verbindbaren Zeilen ihre
   URL verlören (`--force` nach Prüfung).
3. Übernehmen: dieselbe Zeile mit `--apply`. Zuordnung nur über die Bankleitzahl; Name, Ort,
   BIC und Prüfziffer bleiben, Domain, URL und Versionen kommen aus der DK-Zeile. Neue
   Bankleitzahlen werden ergänzt. Eine URL, die die DK-Liste nicht mehr nennt, wird nicht
   gelöscht, sondern im Bericht als `KEPT` aufgeführt (`--allow-clear` entfernt sie).
   `--match-bic` überträgt Angaben zusätzlich auf Zeilen ohne eigene DK-Zeile mit exakt
   gleicher BIC; standardmäßig aus, weil Sondergeschäftsstellen einer BIC oft keinen
   FinTS-Zugang haben.
4. Datumszeile oben in diesem Abschnitt anpassen, `apps/api/tests/unit/test_fints.py` und
   `test_ae26_fints_institutes_script.py` laufen lassen, ausliefern. Bestehende Verbindungen
   übernehmen die neue Adresse beim nächsten Dialog, sofern keine manuelle Adresse gesetzt ist.

Der Lauf vom 01.10.2026 mit der Datei vom 20.08.2026 ergab keine Änderung (Stand der Liste
deckt sich mit der DK-Datei); beim Lesen wurde ein Name mit falsch gelesenem Zeichen
(U+0096 statt Gedankenstrich, BLZ 45451555) berichtigt.

### FinTS-Adresse je Verbindung (Bankfusion)

Bei Fusionen und Wechseln des Rechenzentrums folgt die Institutsliste mit Verzug. Unter
Bank, FinTS-Verbindung zeigt die Karte "FinTS-Adresse der Bank" (verwendeter Rechnername und
Herkunft: Institutsliste oder manuell). Mit "Adresse ändern" (bei Fehler `MHVP-BANK-0013`
"FinTS-Adresse prüfen") wird die aktuelle Adresse der Bank eingetragen; die PIN ist dabei
erneut einzugeben und ersetzt die gespeicherte. Es wird kein Anmeldeversuch gestartet; danach
"Erneut freigeben" wählen. Reihenfolge der verwendeten Adresse: manuell, Eintrag der
aktuellen Institutsliste, beim Anlegen gespeicherte Adresse. "Adresse der Institutsliste
verwenden" nimmt die manuelle Adresse zurück. Zulässig sind nur `https://`-Adressen mit
öffentlichem Rechnernamen (keine IP-Adresse, kein `localhost`, keine interne Domain, keine
Zugangsdaten in der Adresse). Das ist eine namensbasierte Prüfung; die Ausgangsregeln des
Servers (Firewall, Proxy) bleiben die zweite Schutzebene. Ändern sich bei der Fusion auch
Bankleitzahl oder Anmeldename, ist die Verbindung mit den neuen Angaben neu anzulegen.

## Grenzen

- 90-Tage-Regel (PSD2): erneute TAN nach spätestens 90 Tagen; manche Banken verlangen die
  TAN je Umsatzabruf über 90 Tage zurück. Beides wird über die Sitzung abgewickelt.
- Keine Zahlungen, keine Lastschriften, keine Daueraufträge (G2 geschlossen).
- Kreditkarten- und Depotkonten werden nicht abgerufen (nur SEPA-Konten aus `HKSPA`).
- Nur PIN/TAN; Schlüsseldatei/Chipkarte (RDH/DDV) nicht vorgesehen.
- Kein automatischer Abruf per Zeitplan: jede Aktualisierung ist ein Klick, weil die Bank
  jederzeit eine TAN verlangen kann.
- Testsystem: die Tests laufen gegen einen Fake-Client (`tests/fints_fake.py`); ein Test
  gegen ein echtes Bankkonto erfolgt durch den Betreiber nach DK-Registrierung.
