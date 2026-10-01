# Runbook: XRechnung-Prüfung mit dem KoSIT-Validator

Stand: 01.10.2026 (GA14-05, AC11, AE26). Gilt für die Prüfung der vom Generator (`mhvp.accounting.xrechnung`) erzeugten XRechnung-Dateien (UBL) gegen den amtlichen Prüfer. Ergebnis ist ein technischer Konformitätsnachweis gegen die gepinnte Konfiguration, keine steuerliche Freigabe (P05, G1).

## Gepinnte Fassungen (Datei `scripts/kosit.lock`)

Die Download-Adressen und SHA-256-Prüfsummen stehen im Repository in `scripts/kosit.lock`. Dieselben Werte nutzen `make kosit-fetch` und der CI-Job `xrechnung-kosit`; Repository-Variablen sind nur noch optionale Überschreibungen.

| Bestandteil | Quelle | Datei | SHA-256 |
| --- | --- | --- | --- |
| KoSIT Validator 1.5.0 (Distribution mit validationtool-1.5.0-standalone.jar) | github.com/itplr-kosit/validator, Release v1.5.0 | validator-1.5.0-distribution.zip | ac78fb3e89d6daa81770049b004bd1408cad81100b885dd1d8da2cd169bd679f |
| XRechnung-Konfiguration 3.0.2 vom 31.10.2024 | github.com/itplr-kosit/validator-configuration-xrechnung, Release release-2024-10-31 | validator-configuration-xrechnung_3.0.2_2024-10-31.zip | 8468086983fa57f08681ddd4e5b7ccafca46def76d02ec146eae254065c93334 |

Herkunft der Prüfsummen: Beide Archive wurden am 01.10.2026 ein zweites Mal von den offiziellen Release-Dateien über eine TLS-geprüfte Verbindung geladen und mit `sha256sum` berechnet; die Werte stimmen mit dem ersten Download desselben Tages überein. Der Herausgeber veröffentlicht keine Prüfsummendatei (die Adressen `...zip.sha256` antworten 404). Die Werte belegen also die geladene Release-Datei, nicht eine vom Herausgeber unterzeichnete Prüfsumme. Vor einer Freigabeentscheidung mit der Release-Seite abgleichen. Ob diese Konfiguration zum Zeitpunkt der Nutzung noch die gültige ist, ist zu prüfen (P05, AA02-03, AC11-01). Lizenzen: Validator Apache License 2.0 (Datei LICENSE in der Distribution); Lizenz der Konfiguration vor produktiver Weitergabe prüfen.

## Pins aktualisieren

1. Neue Fassung auf den Release-Seiten der beiden Projekte auswählen (Validator und passende XRechnung-Konfiguration; die Konfiguration nennt die Validator-Mindestversion).
2. Beide Archive über eine TLS-geprüfte Verbindung laden und `sha256sum <datei>` berechnen. Wenn der Herausgeber eine Prüfsumme veröffentlicht, diese vergleichen.
3. In `scripts/kosit.lock` URL und Prüfsumme eintragen. Ist eine Prüfsumme noch nicht belegt, `PLACEHOLDER` eintragen: `make kosit-fetch` bricht dann mit Exit-Code 3 ab und der CI-Job meldet den Grund (der Job ist nicht blockierend).
4. `make kosit-test` ausführen (Java 11 oder höher), Ergebnis hier und in `docs/OPEN_QUESTIONS.md` (AC11-01) vermerken.

## Lokaler Lauf

1. Java ab Version 11 bereitstellen (`java -version`; getestet mit OpenJDK 21.0.10).
2. `make kosit-fetch` lädt die gepinnten Archive nach `.cache/kosit` (Verzeichnis änderbar mit `KOSIT_DIR=...`, im Git ignoriert), prüft die SHA-256-Werte und entpackt erst danach. Ein zweiter Aufruf mit unveränderten Pins lädt nichts erneut.
3. `make kosit-test` startet den Test `tests/unit/test_aa02_kosit_validator.py` gegen den Prüfer (Generatordateien regelbesteuert und Kleinunternehmer).
4. Eigene Dateien: `make kosit-validate FILES="datei.xml weitere.xml"`; ohne Make `MHVP_KOSIT_DIR=... scripts/kosit_validate.sh datei.xml`. Berichte liegen in `$MHVP_KOSIT_DIR/report`. Exit-Code 0 heißt: alle Dateien angenommen.

Exit-Codes von `scripts/kosit_fetch.sh`: 0 bereit, 2 Aufruf- oder Werkzeugfehler (curl, unzip fehlen, unerwartetes Archiv), 3 Pin fehlt oder ist Platzhalter, 4 Prüfsumme stimmt nicht (nichts entpackt), 5 Download fehlgeschlagen.

Hinter einem Proxy: Der Download nutzt `curl` und damit `HTTPS_PROXY` und das CA-Bundle des Systems (`CURL_CA_BUNDLE`); die TLS-Prüfung wird nie abgeschaltet.

## CI

Job `xrechnung-kosit` in `.github/workflows/ci.yml` (nicht blockierend, `continue-on-error`). Er läuft standardmäßig und liest die Pins aus `scripts/kosit.lock`; Repository-Variablen sind nicht nötig:

- Abschalten: Repository-Variable `MHVP_KOSIT_ENABLED=false`.
- Optionale Überschreibung einzelner Werte: `KOSIT_JAR_URL`, `KOSIT_JAR_SHA256`, `KOSIT_CFG_URL`, `KOSIT_CFG_SHA256` (leere Variablen zählen als nicht gesetzt).

Der Job ruft `scripts/kosit_fetch.sh` mit `MHVP_KOSIT_DIR=$RUNNER_TEMP/kosit` auf und führt danach denselben Test aus wie `make kosit-test`. Ob der Job später blockierend wird, ist Betreiberentscheidung (AA02-03, AC11-01).

## Fehlerbilder

- `no validationtool-*-standalone.jar`: Distribution nicht entpackt oder falsches Verzeichnis (Exit 2).
- `no cfg/scenarios.xml`: Konfiguration nicht nach `cfg/` entpackt (Exit 2).
- Download scheitert mit 403/407: Proxy-Status prüfen (`curl -sS "$HTTPS_PROXY/__agentproxy/status"`), Host muss freigegeben sein.
- Test wird übersprungen: `MHVP_KOSIT_DIR` oder `java` fehlt; das gilt als nicht ausgeführt, nicht als bestanden.
- Befund `reject`: Bericht im Verzeichnis `report` lesen, Regel-ID (BR-..., BR-DE-...) dem Generator zuordnen.
- `pin for 'validator' is missing or a placeholder` (Exit 3): `scripts/kosit.lock` trägt `PLACEHOLDER` oder eine ungültige Prüfsumme; siehe "Pins aktualisieren".
- `checksum mismatch` (Exit 4): die geladene Datei weicht vom Pin ab (neue Veröffentlichung unter derselben Adresse, Proxy-Eingriff oder Übertragungsfehler); nichts wurde entpackt. Nicht einfach den neuen Wert übernehmen, sondern Herkunft klären.
