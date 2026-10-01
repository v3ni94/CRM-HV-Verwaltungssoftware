# Messdienstleister (Heizkosten, Wasser, Rauchwarnmelder)

Stand 26.09.2026, Stufe 1 und Stufe 2 (lesende Adapter ista und KALO) des Moduls `mhvp.metering` (Regel `docs/rules/M40-01.md`, Masterprompt Messdienstleister des Betreibers). Diese Datei ist das Betreiberdokument: Anbieterstand, was das CRM heute kann, was blockiert ist und welche Zugänge oder Unterlagen fehlen.

## 1. Was Stufe 1 leistet

- Zentrale Verbindungen je Mandant unter Einstellungen, Schnittstellen, Messdienstleister: Anzeigename, Anbieter, gegebenenfalls regionale Vertragsgesellschaft, Kunden- und Vertragsnummern als Text, Umgebung Test oder Produktion, aktiv oder pausiert, technische Konfiguration, verschlüsselte Zugangsdaten (nur setzen, nie auslesen), Freischaltungsstand je Funktion, letzter Verbindungstest mit Veraltet-Kennzeichen, letzte Synchronisation je Datenart.
- Reiter Messdienstleister am Objekt und zentrale Zuordnungsübersicht auf denselben Datensätzen: externe Abrechnungseinheit, Leistungsbereich (Heizung, Warmwasser, Kaltwasser, Rauchwarnmelder, Sonstiges), Gültigkeit, Prüfstatus (offen, vorgeschlagen, bestätigt, Konflikt, archiviert), Herkunft, bestätigender Benutzer, technische Bestätigung getrennt von der menschlichen, Gruppierung objektübergreifender Abrechnungseinheiten mit Einheitenumfang, Anbieterwechsel mit Historie, Versionsprüfung bei gleichzeitigen Änderungen.
- Einheitenzuordnung zur externen Nutzeinheit mit Gültigkeit, getrennten Empfängern (Abrechnung, Verbrauchsinformation) und Belegungsstatus (belegt, leer, Eigennutzung, ungeklärt).
- Manueller Abruf "Jetzt abrufen" als persistenter Auftrag mit Status je Teilvorgang, Klärungsbereich für nicht zuordenbare Daten, Verbrauchswerte und Abrechnungsergebnisse als prüfbare Fremddaten (keine Buchung).
- CSV-Vorlage, Vorschau, Übernahme und Export der Zuordnungen mit Dublettenschutz.
- Mandantenschalter `metering_module_enabled` (Standard aus) sperrt alle schreibenden Endpunkte.

## 2. Anbieter und Recherchestand

Recherchestand 26.09.2026 aus den vom Betreiber genannten offiziellen Quellen Q1 bis Q11, ergänzt am 27.09.2026 um Q12 (Minol Datenaustausch), Q13 (Techem Data Exchange Services) und Q14 (bved Standard-Datenaustausch 3.10, PDF). Vor Implementierung eines Adapters ist jede Angabe erneut an der Quelle zu prüfen. Fehlende Dokumentation ist kein Nachweis einer fehlenden API; daher "Ungeklärt" oder "Dokumentation erforderlich", nie "Nein".

| Anbieter | Dokumentierter Stand (Quelle) | Adapter im CRM | Offene Blockade |
| --- | --- | --- | --- |
| ista | Entwicklerportal mit Stammdaten- und Ordnungsbegriffsabgleich (Billing Unit Data, asynchron, Q8), Rollen (On-Site Roles 2.0, Q10), Billing Input (finale Übertragung kann eine Abrechnung auslösen, Q11), Billing Result, Dokumente und monatliche Verbrauchsdaten (Q1). Authentifizierung je API-Familie unterschiedlich, mTLS im Test- und Produktionszugang verschieden (Q9) | lesende Adapter implementiert (Abschnitt 7) | Endpunkte, Token-URL, Zugangsdaten und Zertifikate werden erst bei der Einrichtung durch ista übermittelt (Q9); ohne Testzugang keine End-to-End-Prüfung (OPEN_QUESTIONS M40-01) |
| Techem | DXS und DXS Dynamic API werden angeboten (Q2, Q13): Dateiaustausch nach bved-Standard mit E898, LM- und BK-Sätzen über DXS Connector und DXS Filetransfer Service; keine technische Endpunkt- oder Übertragungsdokumentation | Dateiadapter bved 3.10 (Abschnitt 7.7), kein Online-Zugang | Technische Dokumentation, Zugang zum DXS Filetransfer Service und Beispieldateien anfordern (M40-02) |
| KALO / Kalorimeta | Entwicklerportal für Nutzerwechsel zur uVI, Verbrauchsdaten, uVI-Dokumente und DTA-Datenaustausch (Q3); Unterstützung neuer Billing-APIs daraus nicht ableitbar | lesende Adapter für Verbrauchsdaten und Dokumente implementiert (Abschnitt 7) | Kundenfreischaltung, Zugangsdaten und ein Testsystem (nicht dokumentiert) fehlen (M40-01) |
| Brunata Minol | Cloud-to-Cloud-Verbrauchsdaten über den bved-/ARGE-Webservice (Q4); Datenaustausch nach bved 3.10 mit L/M-, B/K-, D- und E898-Sätzen, Bereitstellung über Softwareintegrationen und das Kundenportal Minol direct (Q12); Versionsstand anbieterspezifisch (Q6, Q7) | Dateiadapter bved 3.10 (Abschnitt 7.7), kein Online-Zugang | Vereinbarung mit dem Anbieter, Versionsnachweis, Portalzugang und Beispieldateien (M40-02) |
| BRUNATA-METRONA | Dokumenten- und Verbrauchsdaten-Webservices für uVI bestätigt (Q5); ein Dateiaustausch nach bved 3.10 ist auf der geprüften Seite nicht belegt | Dateiadapter bved 3.10 (Abschnitt 7.7, Satzarten für diesen Anbieter als "nicht belegt" gekennzeichnet), kein Online-Zugang | Technische Dokumentation, Freischaltung und Bestätigung des Dateiaustauschs (M40-02) |
| Sonstiger Messdienstleister / manuelle Verwaltung | keine API | manueller Adapter (keine Verbindung) | keine |

Minol und BRUNATA-METRONA bleiben getrennte Anbieter. Gemeinsame bved-Clients werden nur für tatsächlich kompatible Versionen genutzt; keine Annahme, dass jeder Anbieter die neueste bved-Version unterstützt.

## 3. Ehrliche Funktionsanzeige

Je Verbindung und Funktion zeigt das CRM vier Dimensionen: dokumentierte Unterstützung (Katalog), Adapter implementiert mit geprüfter Version, Freischaltung des Kundenkontos (vom Mandanten gepflegt) und letzter Verbindungstest (Ergebnis, Zeitpunkt, veraltet nach Konfigurationsänderung). Anzeigetexte: "Ja, API vorhanden", "Ja, Freischaltung ausstehend", "Dokumentation erforderlich", "Verbindung erfolgreich geprüft", "Ungeklärt", "Nein, keine API vorhanden" nur bei bestätigter Abwesenheit. Eine Aktion wird nur angeboten, wenn alle Voraussetzungen erfüllt sind; schreibende Funktionen (Rollen, Billing Input) sind in Stufe 1 grundsätzlich deaktiviert.

## 4. Sicherheit

- Zugangsdaten werden mit dem vorhandenen Feldverschlüsselungsverfahren (Mandantenschlüssel, ADR 0006) gespeichert, nur gesetzt oder ersetzt und nie an das Frontend zurückgegeben. Keine Geheimnisse in Protokollen.
- Ein Verbindungstest meldet unterscheidbar: erfolgreich, Authentifizierung fehlgeschlagen, nicht freigeschaltet, Zugangsdaten fehlen, kein Adapter. Ein erfolgreicher Login ist kein Nachweis für Zugriff auf alle Objekte.
- Test- und Produktionsumgebung sind je Verbindung getrennt; das Testdouble der automatischen Tests läuft nie in einer Produktionsverbindung.
- Reale Adapter müssen ausgehende Ziele über die vorhandene SSRF-Sicherung (`pin_target`) prüfen und die TLS-Prüfung eingeschaltet lassen.
- Rechte getrennt: Zugangspflege (`metering_connections:manage`), Zuordnungen (`metering_assignments:update`), Abruf (`metering_sync:run`), Dateneinsicht (`metering_data:read`), Nutzerübermittlung (`metering_users:submit`) und verbindliche Abrechnungsbeauftragung (`metering_billing:order`). Standardrollen: Administratoren alles; Standard und Sachbearbeiter Zuordnungen, Abruf und Einsicht; Nur Lesezugriff Einsicht.

## 5. Einrichtung (Stufe 1)

1. Einstellungen, Mandant: Schalter Messdienstleister-Modul einschalten.
2. Einstellungen, Schnittstellen, Messdienstleister: Verbindung anlegen (Anbieter, Name, Umgebung, Kundennummern), Zugangsdaten setzen, Freischaltung je Funktion nach Anbieterbestätigung eintragen, Verbindungstest ausführen. Ohne Adapter meldet der Test "kein Adapter"; das ist keine Fehlfunktion, sondern der dokumentierte Stand.
3. Objekt, Reiter Messdienstleister oder zentrale Übersicht: externe Abrechnungseinheit mit Leistungsbereich und Gültigkeit zuordnen, Einheiten der externen Nutzeinheit zuordnen, Zuordnung nach Prüfung bestätigen (Prüfgrundlage angeben).
4. Alternativ CSV-Vorlage laden, füllen, Vorschau prüfen, übernehmen.
5. "Jetzt abrufen" erst nach erfolgreichem Verbindungstest und Freischaltung. Für ista und KALO sind die Konfigurationsschlüssel in Abschnitt 7.3 beschrieben; ohne reale Zugangsdaten bleibt nur das Testdouble in Testverbindungen.

## 6. Nicht ausgeführte Prüfungen

Es liegen keine realen Zugangsdaten, Testsysteme oder Zertifikate vor. Alle automatischen Tests laufen mit künstlichen Daten: die Adapter ista und KALO gegen einen gescripteten HTTP-Transport (`httpx.MockTransport`, `apps/api/tests/unit/test_m40_metering_adapters.py`), der Abruf- und Dokumentenprozess gegen das Testdouble `FakeAdapter` und einen simulierten Objektspeicher (`apps/api/tests/integration/test_m40_metering_stage2.py`). End-to-End-Prüfungen gegen Sandbox- oder Produktivsysteme wurden nicht durchgeführt. Die Abnahmefälle 7, 10, 11 und 12 des Masterprompts sind damit nur gegen Mocks nachgewiesen; der Nachweis gegen die Anbietersysteme steht aus (M40-01).

## 7. Fähigkeitsmatrix der Adapter (Stufe 2, Recherchestand 26.09.2026)

Grundlage sind die öffentlich abrufbaren Seiten Q1, Q3, Q8, Q9 und die vom bved veröffentlichten OpenAPI-Dateien (Q6, Q7): billing-unit-data 1.0.2, billing-result 1.0.3, consumption-data 1.2.1, documents 1.3. Die Dateien wurden am 26.09.2026 heruntergeladen und ausgewertet; die Basis-URLs sind laut Spezifikation anbieter- und kundenspezifisch ("The actual URLs are provided by each MSC") und werden nie erfunden. Vor der Produktivnutzung ist jede Zeile erneut an der Quelle zu prüfen.

### 7.1 ista

| Funktion | Dokumentiert (Quelle) | Adapter | Geprüfte Version | Authentifizierung laut Quelle | Blockade / Hinweis |
| --- | --- | --- | --- | --- | --- |
| Billing Unit Data (Ordnungsbegriffsabgleich) | Ja (Q1, Q8: asynchron, Status OPEN, IN_PROGRESS, COMPLETED, Filter from, status, limit, offset, höchstens 100) | lesend: Liste, Status, Ergebnis je Abrechnungseinheit; Übermittlung (`POST .../setup/{billingunit}`, sendSetup) nur über den kontrollierten Übermittlungsablauf als eigene Art `billing_unit_setup` (Abschnitt 7.6) | bved billing-unit-data 1.0.2 | OAuth 2 Client Credentials (Q9: bved 2026) | Endpunkt und Token-URL erst bei Einrichtung (Q9); Freigabe je Verbindung (`write_sync_enabled`) und Recht `metering_assignments:update` (M40-03) |
| Billing Result | Ja (Q1) | lesend: verfügbare Perioden, Ergebnis je Periode, ein prüfbarer Datensatz je Empfänger und Kostenblock (Bruttobetrag, Saldo und Vorauszahlungen im Payload) | bved billing-result 1.0.3 | OAuth 2 Client Credentials (Q9) | Währung ist in der Spezifikation nicht enthalten; Vertragswährung je Verbindung (`currency`, Standard EUR) |
| Monatliche Verbrauchsdaten | Ja (Q1: ARGE EED Consumption) | lesend: Perioden je Abrechnungseinheit, Werte je Nutzeinheit, Verbrauchsart, Maßeinheit, tatsächlich, geschätzt, fehlend; umgerechnete kWh getrennt (`KWH_CONVERTED`) | ARGE consumption-data 1.2.1 | Basic Auth (Q9: ältere ARGE-Familie), alternativ OAuth 2 wenn von ista bestätigt (`consumption_auth`) | Endpunkt erst bei Einrichtung |
| Dokumente | Ja (Q1: ARGE Document Webservices, E898) | lesend: Liste mit Pagination, Download, Quittung nach sicherer Speicherung | bved documents 1.3 (Q1 nennt ARGE documents 3.10) | Basic Auth (Q9), alternativ OAuth 2 (`documents_auth`) | Versionsstand 1.3 gegenüber 3.10 durch ista bestätigen lassen |
| Rollen (On-Site Roles 2.0) | Ja (Q1, Q10; bved-Zip vom 27.09.2026: `POST /onsiteroles/v2/billingunits/{billingunit}/residentialunits/{unit}/on-site-roles`, vollständiger Datensatz je Nutzeinheit, `terminateallbillingcontracts` mit Datum) | schreibend, nur über den kontrollierten Übermittlungsablauf (Abschnitt 7.5); kein Prüfmodus in der API, Prüfung lokal | bved on-site-roles 2.0.2 | OAuth 2 | Basis-URL `base_urls.roles` erst bei Einrichtung (Q9); Freigabe je Verbindung (`write_sync_enabled`) und Recht `metering_users:submit` (M40-03) |
| Billing Input | Ja (Q1, Q11; bved-Zip vom 27.09.2026: `GET .../billingperiods`, `GET .../billingperiods/{bis}` Vorlage, `POST .../billingperiods/{bis}?action=VALIDATE|SEND|SEND_AND_IGNORE_WARNINGS`; die finale Übertragung beauftragt die Abrechnung) | schreibend, nur über den kontrollierten Übermittlungsablauf: Vorlage laden, `VALIDATE` bei "Daten prüfen", `SEND` erst nach Freigabe | bved billing-input 1.0.3 | OAuth 2 | Basis-URL `base_urls.billing_input` erst bei Einrichtung (Q9); Freigabe je Verbindung und Recht `metering_billing:order`; Kostenschlüssel laut bved-Anlage (M40-03) |

Testzugang: Client-Zertifikat (mTLS) erforderlich, Produktivzugang der neuen bved-APIs ohne Zertifikat (Q9). Keine Rate Limits dokumentiert (Q9). Zugang über datahub@ista.com.

### 7.2 KALO / Kalorimeta

| Funktion | Dokumentiert (Quelle) | Adapter | Geprüfte Version | Authentifizierung laut Quelle | Blockade / Hinweis |
| --- | --- | --- | --- | --- | --- |
| Monatliche Verbrauchsdaten (uVI) | Ja (Q3, Unterseite Verbrauchsdaten-API: `https://api.kalo.de/arge/consumptions/v1/`, `GET /billingunits/{mscnumber}/consumptions/periods[/{period}]`, 9-stellige Liegenschaftsnummer mit führenden Nullen) | lesend | KALO v1, Payload nach bved consumption-data 1.2.1 (KALO verweist auf bved) | OpenID Connect Client Credentials über `https://meine.kalo.de/auth/realms/arge-api/protocol/openid-connect/token` oder Basic Auth (`consumption_auth`) | Kein Testsystem dokumentiert; Testverbindung braucht `base_url` und `token_url` von KALO und darf nicht auf Produktionshosts zeigen |
| Dokumente (uVI) | Ja (Q3, Unterseite Dokumenten-API: `https://api.kalo.de/arge/documents/v1/`, `GET /documents/out`, `/count`, `/{documentid}/data`, `PUT /{documentid}/status`) | lesend: Liste, Download, Quittung | KALO v1, bved documents 1.3 | wie oben | Body der Statusquittung auf der KALO-Seite nicht dokumentiert (bved 1.3 verwendet); Zuordnung von `resident`-Referenzen zur Liegenschaft nicht dokumentiert, solche Dokumente landen im Klärungsbereich |
| Rollen / Nutzerwechsel | Ja (Q3) | nicht implementiert (Q3 nennt keinen Endpunkt; Ablauf bleibt bei der lokalen Prüfung, Beauftragung gesperrt) | bved on-site-roles | wie oben | Dokumentation erforderlich (M40-03) |
| DTA-Datenaustausch | Ja (Q3, Dokumenten-API bved-DTA) | nicht implementiert | nicht geprüft | wie oben | Dokumentation erforderlich |
| Billing Unit Data, Billing Input, Billing Result | Ungeklärt (Q3 nennt sie nicht) | nicht implementiert | keine | keine | Dokumentation erforderlich |

Feste Produktionsadressen laut Q3 sind im Adapter hinterlegt und können nicht durch Konfiguration überschrieben werden; statische Quell-IP 193.102.14.238 laut KALO (für Firewall-Freigaben, Änderung vorbehalten).

### 7.3 Konfiguration je Verbindung (technische Konfiguration, keine Geheimnisse)

| Schlüssel | ista | KALO | Bedeutung |
| --- | --- | --- | --- |
| `config_environment` | Pflicht | Pflicht | Muss der Umgebung der Verbindung entsprechen (`test` oder `production`); eine Konfiguration läuft nie in der anderen Umgebung |
| `base_urls` | Pflicht, Objekt mit `billing_unit_data`, `billing_result`, `consumption`, `documents` (nur https) | nicht verwendet | Von ista bei der Einrichtung übermittelte Endpunkte je API-Familie |
| `token_url` | Pflicht für OAuth 2 | nur Testumgebung | OAuth 2 Token-Endpunkt |
| `base_url` | nicht verwendet | nur Testumgebung | Basis des KALO-Testsystems (von KALO zu nennen) |
| `consumption_auth`, `documents_auth` | `basic` (Standard) oder `oauth2` | `oauth2` (Standard) oder `basic` | Verfahren je Familie laut Anbieterbestätigung |
| `currency` | optional, Standard EUR | nicht verwendet | Vertragswährung der Abrechnungsergebnisse |
| `max_parallel` (1 bis 4, Standard 2), `timeout_seconds` (30), `retries` (2), `backoff_seconds` (0,5) | optional | optional | Begrenzte Parallelität, Timeouts und Wiederholungen mit Backoff (nur lesende Aufrufe) |

Geheimnisse (verschlüsselt, nur setzen): `client_id`, `client_secret` (OAuth 2), `basic_username`, `basic_password` (Basic Auth), `client_cert_pem`, `client_key_pem` (ista Testzugang, mTLS). Kein Geheimnis erscheint in Antworten, Auftragsprotokollen oder Fehlertexten.

### 7.5 Kontrollierte schreibende Vorgänge (Abschnitt 12, Abnahmefälle 11 und 12)

- Zwei getrennte Abläufe mit getrennten Rechten: Nutzer- und Rollenübermittlung (`metering_users:submit`) und Abrechnungsdaten (`metering_billing:order`). Beide setzen den Mandantenschalter, eine aktive Verbindung und für die verbindliche Übermittlung die Freigabe je Verbindung ("Schreibende Vorgänge freigeben", `write_sync_enabled`, Standard aus) sowie einen dokumentierten und implementierten Adapter voraus.
- Schritte im Objektreiter: "Daten prüfen" (Aufbau des vollständigen Datensatzes aus dem CRM, lokale Validierung, bei Billing Input Anbietervorlage und Anbieterprüfung mit `VALIDATE`, nichts wird gespeichert oder beauftragt), Anzeige von Fehlern, Warnungen und Unterschieden zur letzten beauftragten Übertragung, "Freigeben" (Warnungen müssen ausdrücklich bestätigt werden), danach "Abrechnung verbindlich beauftragen" beziehungsweise "Nutzer und Rollen verbindlich übermitteln" mit Sicherheitsabfrage. Die Buttons sind getrennt und sprechen getrennte Endpunkte an.
- On-Site Roles 2.0: je Nutzeinheit wird der vollständige Datensatz gesendet (Partner aus den Kontaktverweisen, Abrechnungsvertrag mit ausdrücklichem Leerstandskennzeichen, Beendigungskennzeichen mit Datum bei beendeter Einheitenzuordnung). Fehlende Einheitenzuordnungen, ungeklärte Belegung und fehlende Empfänger sind Fehler; es wird nie nur ein einzelner geänderter Datensatz gesendet.
- Datenversion: jede Prüfung erhält einen Fingerabdruck aus Payload und Versionsständen der Zuordnungen. Freigabe und Beauftragung berechnen ihn neu; jede Änderung an Objekt- oder Einheitenzuordnungen (auch Anbieterwechsel) entwertet Prüfung und Freigabe (Status "entwertet", Fehler MHVP-METR-0012), die Daten sind erneut zu prüfen.
- Protokoll: jeder Schritt mit Benutzer, Zeitpunkt, Datenversion und Anbieterantwort (Vorgangsnummer, Meldungen) am Datensatz und als Ereignis `metering.transmission.<status>`.
- Zeitüberschreitung bei der verbindlichen Übertragung: Status "Ergebnis unklar", keine automatische Wiederholung, Klärung beim Anbieter vor jedem erneuten Senden. Abgewiesene Übertragungen (HTTP 400 mit Meldungen, HTTP 409 bereits angenommen) werden mit den Meldungen des Anbieters gezeigt.
- Nicht ausgelöst: In Entwicklung und Tests wurde keine echte Abrechnung, Nutzeränderung oder Montage beauftragt (Testdouble und `httpx.MockTransport`). Montage- und Reparaturaufträge sind nicht Teil dieser Ausbaustufe.

### 7.6 Ordnungsbegriffsabgleich als eigener Ablauf (Abschnitt 6, Q8)

- Eigene Übermittlungsart `billing_unit_setup` mit denselben Schritten wie Abschnitt 7.5 (Vorschau erstellen, Freigeben, verbindlich übermitteln, Recht `metering_assignments:update`), im Objektreiter und in der zentralen Übersicht der Schnittstellen-Einstellungen (Statusanzeige, Abruf des Bearbeitungsstatus).
- Vorschau: interne Kennungen (Objektnummer, Einheitennummern des CRM) neben den externen Kennungen (Abrechnungseinheit, Nutzeinheit des Anbieters) je Einheitenzuordnung, dazu Abrechnungsempfänger (nur Namen), Kundennummer beim Anbieter (erste `customer_reference` der Verbindung oder Eingabe) und das zuletzt abgerufene Anbieterergebnis (beim Anbieter bekannte und zusätzlich geführte Nutzeinheiten). Fehlende Zuordnungen, doppelte Nutzeinheiten und eine fehlende Kundennummer sind Fehler; abweichende Stellenzahlen (bved: neun Stellen Abrechnungseinheit, vier Stellen Nutzeinheit) sind Warnungen.
- Die Übermittlung (`sendSetup`) wird genau einmal gesendet. Die Annahme durch den Anbieter ergibt den Status "beim Anbieter in Bearbeitung" (`waiting_provider`), nie "vollständig zugeordnet". Erst "Status beim Anbieter abrufen" (nur lesend, wiederholbar) holt den Bearbeitungsstatus: `IN_PROGRESS` bleibt in Bearbeitung, `COMPLETED` speichert das Ergebnis (`matched`, `additional`) an der Übermittlung und an der externen Abrechnungseinheit und bestätigt die Zuordnung technisch (`remote_confirmed`, Verifikationsbasis mit Vorgangsnummer und Abrufzeitpunkt) nur dann, wenn jede gesendete Nutzeinheit im Anbieterergebnis zugeordnet ist. Nicht zugeordnete Nutzeinheiten werden angezeigt, die Zuordnung bleibt unbestätigt; es wird nichts automatisch zugeordnet.
- Anbieter ohne dokumentierte Übermittlung (Techem, Brunata Minol, BRUNATA-METRONA, KALO): die Vorschau bleibt lokal mit dem Hinweis "Dokumentation erforderlich", die Übermittlung wird abgewiesen (MHVP-METR-0004). Prüfung: `apps/api/tests/integration/test_m40_metering_setup.py`, Einheitentest der ista-Aufrufe in `test_m40_metering_adapters.py`, Oberfläche `TransmissionWorkflow.test.tsx` und `TransmissionsOverview.test.tsx`.

### 7.4 Verhalten des Abrufs (Abschnitte 10 und 11)

- Aufträge: Sperre gegen Doppelstart auf Datenbankebene, Wiederholung eines abgeschlossenen Auftrags ist wirkungslos (`skipped`), identische Werte werden nie doppelt gespeichert, Cursor (Billing Unit Data `from`, Billing Result `updatedsince`) wird nur nach vollständig erfolgreichem Lauf fortgeschrieben.
- Lesende Aufrufe: Wiederholung mit exponentiellem Backoff bei Verbindungsfehlern, Zeitüberschreitungen und 5xx; Pagination mit höchstens 100 Einträgen; Folgeverweise nur auf dem konfigurierten Host; keine Weiterleitungen; Größenlimit für Antworten.
- Schreibende Aufrufe (Übermittlung Ordnungsbegriffsabgleich, Dokumentquittung, Rollen, Billing Input): genau ein Versuch; nach einer Zeitüberschreitung "Ergebnis unklar" und manuelle Klärung, nie blinde Wiederholung (Abnahmefall 11).
- Teilweise fehlerhafte Abrufe: Status "teilweise erfolgreich" mit Fehler je Abrechnungseinheit im Teilvorgang `fetch`; abgelaufene Zugangsdaten und fehlende Freischaltung werden im Verbindungstest als "Authentifizierung fehlgeschlagen" (HTTP 401 oder 403 je Familie) ausgewiesen; der letzte erfolgreiche Abruf bleibt erhalten.
- Dokumente: Zuordnung vor dem Download, unbekannte Kennungen in den Klärungsbereich, Wiederabruf ohne Dublette, geänderte Abrechnung als neue Version, Quittung erst nach dem Commit der Speicherung, bei Speicherfehler keine Quittung; Sichtbarkeit nur Mandant, keine Portalfreigabe durch den Import.

### 7.7 Dateiaustausch nach bved 3.10 für Techem, Brunata Minol und BRUNATA-METRONA (M40-02, Stand 27.09.2026)

Quellen: Q13 (Techem: "Techem Data Exchange Services entsprechen dem offenen Standard des bved", Dateitypen "Abrechnungsdokumente (E898), Datentauschdateien (LM- und BK-Sätze), EED-Verbrauchsinformation", Übertragung über "DXS Connector" und "Techem DXS Filetransfer Service" oder "DXS Dynamic API"), Q12 (Brunata Minol: "bved 3.10" beziehungsweise "ARGE 3.10" mit L/M-, B/K-, D- und E898-Sätzen, Kundenportal "Minol direct"), Q5 (BRUNATA-METRONA: nur ARGE-Webservices "documents" und "consumption" für uVI), Q14 (bved, "Standard-Datenaustausch zwischen Software der Wohnungswirtschaft und Abrechnungsunternehmen für Heiz-, Warm- und Kaltwasserkosten", Version 3.10 dritte Erweiterung, September 2025; heruntergeladen und ausgewertet am 27.09.2026).

Keine der drei Anbieterseiten nennt Host, Protokoll (SFTP oder anderes), Port, Schlüsselverfahren, Anmeldung oder Endpunkte. Deshalb bauen die Adapter `techem_file`, `brunata_minol_file` und `brunata_metrona_file` (`apps/api/src/mhvp/metering/adapters_heiwako.py`) keine Verbindung auf und bieten keine SFTP-Konfiguration an; eine solche würde nur erfunden. Sie verarbeiten die vom Betreiber aus dem Anbieterportal oder dem Übertragungsclient heruntergeladenen Austauschdateien. Verbindungstest, Abruf, Übermittlung und Ordnungsbegriffsabgleich antworten weiterhin "Dokumentation erforderlich" (`setup_submission` leer, Fähigkeitsmatrix "Adapter nicht implementiert").

Umgesetzter Parser (`apps/api/src/mhvp/metering/heiwako.py`, Feldpositionen aus Q14):

| Datei (Q14, Seite 6) | Satzart | Satzlänge | Inhalt | Verwendung im CRM |
| --- | --- | --- | --- | --- |
| `DTA310_JJJJMMTThhmmssSSS.DAT` | A | 128 | Zuordnung der Ordnungsbegriffe (Kundennummer, Ordnungsbegriff des Abrechnungsunternehmens 9 plus 4 Stellen, Ordnungsbegriff des Auftraggebers) | Vorschau, Abgleich mit Zuordnungen manuell |
| `DTM310_JJJJMMTThhmmssSSS.DAT` | L, M | 2048 | Liegenschaft (Abrechnungszeitraum, Währung, MwSt-Kennzeichen, WEG-Kennzeichen, Fläche) und Nutzer (Name und Anschrift Nutzer und Eigentümer, Wohnzeitraum, Grundanteile, Vorauszahlungen, Leerstand, Umlageschlüssel) | Vorschau; liefert den Beginn des Abrechnungszeitraums je Liegenschaft für die D-Sätze |
| `DTD310_JJJJMMTThhmmssSSS.DAT` | D | 1024 | Abrechnungsergebnis je Nutzer und Kostenart (Tabelle K): Gesamtkosten, Vorauszahlung, neue monatliche Vorauszahlung, Umlageausfallwagnis, Saldo (positiv Nachzahlung, negativ Guthaben), Verbrauchsanteile, CO2-Anteile, Währung | Vorschau als Abrechnungsergebnisdatensätze (Betrag = Gesamtkosten Brutto der Kostenart wie beim bved Billing Result; Saldo und Vorauszahlungen im Payload) |
| `DTE898_JJJJMMTThhmmssSSS.DAT` | E898 | 120 | Index auf die Bilddatei (PDF) der Einzelabrechnung je Nutzer (Pfad, Seite, Dokumentenart HKA, BKA, VDA) | Vorschau; die Bilddateien selbst werden nicht importiert |

Nicht verarbeitet: B- und K-Sätze (Brennstoffe und Kosten, Richtung Wohnungswirtschaft zum Abrechnungsunternehmen), E835 (steuerliche Leistungsarten) und P (Preisbremse). Regeln aus Q14, Seite 7: Zeichensatz ISO 8859-15, Zeilenende CR LF, nicht belegte Felder sind Blank und werden nie als Null gelesen, numerische Felder rechtsbündig mit führenden Nullen und Minuszeichen in der ersten Stelle, Beträge mit zwei impliziten Nachkommastellen, Verbrauchsanteile mit drei. Fehlerhafte Zeilen (Länge, Satzende, Version außerhalb 03.00 bis 99.99, nicht numerische Felder, Satzart passt nicht zum Dateinamen) werden mit Zeilennummer gemeldet und übersprungen.

Prüfung im CRM: `POST /api/v1/metering/connections/{id}/heiwako-import/preview` (Recht `metering_sync:run`, bis zu zehn Dateien je Aufruf, optional `period_from` für D-Sätze ohne begleitende DTM-Datei) liefert je Datei die Satzanzahl, Fehler und die für den Anbieter öffentlich nicht belegten Satzarten (Techem nennt LM und E898, nicht D; BRUNATA-METRONA nennt keinen Dateiaustausch), dazu die Abrechnungsergebnisse und Nutzer als Vorschau. Es wird nichts gespeichert: die Übernahme in `metering_billing_result` (mit Zuordnung über Abrechnungseinheit und Zeitraum wie beim Online-Abruf, Klärungsbereich bei unklarer Zuordnung) wird erst freigeschaltet, wenn der Betreiber je Anbieter eine echte Beispieldatei beigebracht hat und der Parser daran bestätigt wurde. Tests mit synthetischen Dateien: `apps/api/tests/unit/test_m40_metering_heiwako.py`.

Zu prüfen (Betreiber, M40-02): Zugang zum Techem DXS Filetransfer Service beziehungsweise DXS Connector, Zugang zu Minol direct, Bestätigung durch BRUNATA-METRONA, ob Dateien nach bved 3.10 geliefert werden; je Anbieter mindestens eine Beispieldatei DTD310 und DTM310 (und, falls geliefert, DTA310 und DTE898) einer bereits abgerechneten Liegenschaft; Bestätigung des Versionsstands (3.10 oder älter, dann abweichende Satzlängen möglich); Tabellen K, E, S und U des bved (Kostenarten, Einheiten, Ablesekennzeichen, Abrechnungsunternehmen) für die Anzeige der Schlüssel im CRM; Jahrhundertregel für zweistellige Jahre (ASSUMPTIONS A-062).

### 7.8 Stammdatenexport im HeiWaKo-Format (GA09-01, Stand 01.10.2026)

`write_a_records` (`apps/api/src/mhvp/metering/heiwako.py`) schreibt die Satzart A (128 Byte,
`DTA310_*.DAT`, ISO 8859-15, CR LF) mit den belegten Feldern 1 bis 6 und 7 bis 31 aus Q14.
Alle übrigen Stellen bleiben leer. Seit 01.10.2026 (AB14) schreiben `write_l_records` und
`write_m_records` zusätzlich die Satzarten L und M (je 2048 Byte, `DTM310_*.DAT`), und zwar
ausschließlich die Positionen, die der Lesepfad aus Q14 auswertet: bei L die Felder 1 bis 18 und
die fünf Kennzeichen 159 bis 165, bei M Nutzer, Eigentümer, Belegungszeitraum, Anteile, Vorauszahlungen,
drei Umlageschlüssel und die Felder 67 bis 70. Offen bleiben, weil im Repo nicht belegt: die
CO2-Felder ab Position 166 der Satzart L, die Umlagezeilen 4 bis 6 (Felder 36 bis 41) sowie die
Dienstleister- und Empfängerblöcke (Felder 42 bis 66) der Satzart M, die bewusst nicht geschrieben
werden (Kontodaten des Dienstleisters), und die Satzarten B und K. Roundtrip-Tests Export gegen
Parser in `tests/unit/test_m40_metering_heiwako.py`. Der Writer ist an keine Übermittlung angebunden. Ob die Messdienste eine
Stammdatenlieferung in diesem Format erwarten, ist offen (AA16-01 in `docs/OPEN_QUESTIONS.md`);
bis dahin bleibt der CSV-Export der Zuordnungen und die Rollenübermittlung per bved-API der
Stammdatenweg. Roundtrip-Test: `apps/api/tests/unit/test_m40_metering_heiwako.py`.
