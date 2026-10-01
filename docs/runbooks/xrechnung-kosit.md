# Runbook: XRechnung-Prüfung mit dem KoSIT-Validator

Stand: 01.10.2026 (GA14-05, AC11). Gilt für die Prüfung der vom Generator (`mhvp.accounting.xrechnung`) erzeugten XRechnung-Dateien (UBL) gegen den amtlichen Prüfer. Ergebnis ist ein technischer Konformitätsnachweis gegen die gepinnte Konfiguration, keine steuerliche Freigabe (P05, G1).

## Gepinnte Fassungen (am 01.10.2026 geladen und geprüft)

| Bestandteil | Quelle | Datei | SHA-256 |
| --- | --- | --- | --- |
| KoSIT Validator 1.5.0 (Distribution mit validationtool-1.5.0-standalone.jar) | github.com/itplr-kosit/validator, Release v1.5.0 | validator-1.5.0-distribution.zip | ac78fb3e89d6daa81770049b004bd1408cad81100b885dd1d8da2cd169bd679f |
| XRechnung-Konfiguration 3.0.2 vom 31.10.2024 | github.com/itplr-kosit/validator-configuration-xrechnung, Release release-2024-10-31 | validator-configuration-xrechnung_3.0.2_2024-10-31.zip | 8468086983fa57f08681ddd4e5b7ccafca46def76d02ec146eae254065c93334 |

Die Prüfsummen wurden aus dem tatsächlich über den Agent-Proxy (mit CA-Bundle, TLS-Prüfung aktiv) geladenen Download berechnet. Sie belegen die geladene Datei, nicht eine vom Herausgeber veröffentlichte Prüfsumme; vor Übernahme als Pin sollten sie mit der Herausgeberseite abgeglichen werden. Ob diese Konfiguration zum Zeitpunkt der Nutzung noch die gültige ist, ist zu prüfen (P05, AA02-03). Lizenzen: Validator Apache License 2.0 (Datei LICENSE in der Distribution); Lizenz der Konfiguration vor produktiver Weitergabe prüfen.

## Lokaler Lauf

1. Java ab Version 11 bereitstellen (`java -version`; getestet mit OpenJDK 21.0.10).
2. Verzeichnis anlegen und entpacken:
   - `mkdir -p kosit/cfg && unzip validator-1.5.0-distribution.zip -d kosit && unzip validator-configuration-xrechnung_3.0.2_2024-10-31.zip -d kosit/cfg`
   - Danach liegen `kosit/validationtool-1.5.0-standalone.jar` und `kosit/cfg/scenarios.xml` vor.
3. Test starten: `export MHVP_KOSIT_DIR=$PWD/kosit && cd apps/api && uv run pytest tests/unit/test_aa02_kosit_validator.py -q -rs --no-cov`
4. Einzelne Dateien: `MHVP_KOSIT_DIR=... scripts/kosit_validate.sh datei.xml`. Berichte liegen in `$MHVP_KOSIT_DIR/report`. Exit-Code 0 heißt: alle Dateien angenommen.

Hinter einem Proxy: Download mit `curl --cacert <CA-Bundle>` und gesetztem `HTTPS_PROXY`; die TLS-Prüfung wird nie abgeschaltet.

## CI

Job `xrechnung-kosit` in `.github/workflows/ci.yml` (optional, `continue-on-error`). Aktivierung durch Repository-Variablen:

- `MHVP_KOSIT_ENABLED=true`
- `KOSIT_JAR_URL` = `https://github.com/itplr-kosit/validator/releases/download/v1.5.0/validator-1.5.0-distribution.zip`, `KOSIT_JAR_SHA256` = Wert aus der Tabelle
- `KOSIT_CFG_URL` = `https://github.com/itplr-kosit/validator-configuration-xrechnung/releases/download/release-2024-10-31/validator-configuration-xrechnung_3.0.2_2024-10-31.zip`, `KOSIT_CFG_SHA256` = Wert aus der Tabelle

Der Job entpackt beide Archive wie in Schritt 2 (Struktur am 01.10.2026 geprüft: Jar im Wurzelverzeichnis der Distribution, `scenarios.xml` im Wurzelverzeichnis der Konfiguration). Das Setzen der Variablen ist Betreiberentscheidung (AA02-03); der Workflow selbst wurde nicht geändert.

## Fehlerbilder

- `no validationtool-*-standalone.jar`: Distribution nicht entpackt oder falsches Verzeichnis (Exit 2).
- `no cfg/scenarios.xml`: Konfiguration nicht nach `cfg/` entpackt (Exit 2).
- Download scheitert mit 403/407: Proxy-Status prüfen (`curl -sS "$HTTPS_PROXY/__agentproxy/status"`), Host muss freigegeben sein.
- Test wird übersprungen: `MHVP_KOSIT_DIR` oder `java` fehlt; das gilt als nicht ausgeführt, nicht als bestanden.
- Befund `reject`: Bericht im Verzeichnis `report` lesen, Regel-ID (BR-..., BR-DE-...) dem Generator zuordnen.
