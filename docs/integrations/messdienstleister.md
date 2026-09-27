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

Recherchestand 26.09.2026 aus den vom Betreiber genannten offiziellen Quellen Q1 bis Q11. Vor Implementierung eines Adapters ist jede Angabe erneut an der Quelle zu prüfen. Fehlende Dokumentation ist kein Nachweis einer fehlenden API; daher "Ungeklärt" oder "Dokumentation erforderlich", nie "Nein".

| Anbieter | Dokumentierter Stand (Quelle) | Adapter im CRM | Offene Blockade |
| --- | --- | --- | --- |
| ista | Entwicklerportal mit Stammdaten- und Ordnungsbegriffsabgleich (Billing Unit Data, asynchron, Q8), Rollen (On-Site Roles 2.0, Q10), Billing Input (finale Übertragung kann eine Abrechnung auslösen, Q11), Billing Result, Dokumente und monatliche Verbrauchsdaten (Q1). Authentifizierung je API-Familie unterschiedlich, mTLS im Test- und Produktionszugang verschieden (Q9) | lesende Adapter implementiert (Abschnitt 7) | Endpunkte, Token-URL, Zugangsdaten und Zertifikate werden erst bei der Einrichtung durch ista übermittelt (Q9); ohne Testzugang keine End-to-End-Prüfung (OPEN_QUESTIONS M40-01) |
| Techem | DXS und DXS Dynamic API werden angeboten (Q2); die Angebotsseite ersetzt keine technische Endpunktdokumentation | nicht implementiert | Technische Dokumentation und Vertragsfreischaltung beim Anbieter anfordern (M40-02) |
| KALO / Kalorimeta | Entwicklerportal für Nutzerwechsel zur uVI, Verbrauchsdaten, uVI-Dokumente und DTA-Datenaustausch (Q3); Unterstützung neuer Billing-APIs daraus nicht ableitbar | lesende Adapter für Verbrauchsdaten und Dokumente implementiert (Abschnitt 7) | Kundenfreischaltung, Zugangsdaten und ein Testsystem (nicht dokumentiert) fehlen (M40-01) |
| Brunata Minol | Cloud-to-Cloud-Verbrauchsdaten über den bved-/ARGE-Webservice (Q4); Bereitstellung und Voraussetzungen müssen vereinbart sein; Versionsstand anbieterspezifisch (Q6, Q7) | nicht implementiert | Vereinbarung mit dem Anbieter, Versionsnachweis (M40-02) |
| BRUNATA-METRONA | Dokumenten- und Verbrauchsdaten-Webservices für uVI bestätigt (Q5); weitere Fähigkeiten nur nach dokumentiertem Nachweis | nicht implementiert | Technische Dokumentation und Freischaltung (M40-02) |
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
| Billing Unit Data (Ordnungsbegriffsabgleich) | Ja (Q1, Q8: asynchron, Status OPEN, IN_PROGRESS, COMPLETED, Filter from, status, limit, offset, höchstens 100) | lesend: Liste, Status, Ergebnis je Abrechnungseinheit; Übermittlung (POST setup) nur als gesperrte Adaptermethode | bved billing-unit-data 1.0.2 | OAuth 2 Client Credentials (Q9: bved 2026) | Endpunkt und Token-URL erst bei Einrichtung (Q9); Übermittlung nicht per Endpunkt angeboten (M40-03) |
| Billing Result | Ja (Q1) | lesend: verfügbare Perioden, Ergebnis je Periode, ein prüfbarer Datensatz je Empfänger und Kostenblock (Bruttobetrag, Saldo und Vorauszahlungen im Payload) | bved billing-result 1.0.3 | OAuth 2 Client Credentials (Q9) | Währung ist in der Spezifikation nicht enthalten; Vertragswährung je Verbindung (`currency`, Standard EUR) |
| Monatliche Verbrauchsdaten | Ja (Q1: ARGE EED Consumption) | lesend: Perioden je Abrechnungseinheit, Werte je Nutzeinheit, Verbrauchsart, Maßeinheit, tatsächlich, geschätzt, fehlend; umgerechnete kWh getrennt (`KWH_CONVERTED`) | ARGE consumption-data 1.2.1 | Basic Auth (Q9: ältere ARGE-Familie), alternativ OAuth 2 wenn von ista bestätigt (`consumption_auth`) | Endpunkt erst bei Einrichtung |
| Dokumente | Ja (Q1: ARGE Document Webservices, E898) | lesend: Liste mit Pagination, Download, Quittung nach sicherer Speicherung | bved documents 1.3 (Q1 nennt ARGE documents 3.10) | Basic Auth (Q9), alternativ OAuth 2 (`documents_auth`) | Versionsstand 1.3 gegenüber 3.10 durch ista bestätigen lassen |
| Rollen (On-Site Roles 2.0) | Ja (Q1, Q10) | nicht implementiert (schreibend) | bved on-site-roles 2.0.2 veröffentlicht | OAuth 2 | M40-03 |
| Billing Input | Ja (Q1, Q11) | nicht implementiert (schreibend, kann Abrechnung auslösen) | bved billing-input 1.0.3 veröffentlicht | OAuth 2 | M40-03 |

Testzugang: Client-Zertifikat (mTLS) erforderlich, Produktivzugang der neuen bved-APIs ohne Zertifikat (Q9). Keine Rate Limits dokumentiert (Q9). Zugang über datahub@ista.com.

### 7.2 KALO / Kalorimeta

| Funktion | Dokumentiert (Quelle) | Adapter | Geprüfte Version | Authentifizierung laut Quelle | Blockade / Hinweis |
| --- | --- | --- | --- | --- | --- |
| Monatliche Verbrauchsdaten (uVI) | Ja (Q3, Unterseite Verbrauchsdaten-API: `https://api.kalo.de/arge/consumptions/v1/`, `GET /billingunits/{mscnumber}/consumptions/periods[/{period}]`, 9-stellige Liegenschaftsnummer mit führenden Nullen) | lesend | KALO v1, Payload nach bved consumption-data 1.2.1 (KALO verweist auf bved) | OpenID Connect Client Credentials über `https://meine.kalo.de/auth/realms/arge-api/protocol/openid-connect/token` oder Basic Auth (`consumption_auth`) | Kein Testsystem dokumentiert; Testverbindung braucht `base_url` und `token_url` von KALO und darf nicht auf Produktionshosts zeigen |
| Dokumente (uVI) | Ja (Q3, Unterseite Dokumenten-API: `https://api.kalo.de/arge/documents/v1/`, `GET /documents/out`, `/count`, `/{documentid}/data`, `PUT /{documentid}/status`) | lesend: Liste, Download, Quittung | KALO v1, bved documents 1.3 | wie oben | Body der Statusquittung auf der KALO-Seite nicht dokumentiert (bved 1.3 verwendet); Zuordnung von `resident`-Referenzen zur Liegenschaft nicht dokumentiert, solche Dokumente landen im Klärungsbereich |
| Rollen / Nutzerwechsel | Ja (Q3) | nicht implementiert (schreibend) | bved on-site-roles | wie oben | M40-03 |
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

### 7.4 Verhalten des Abrufs (Abschnitte 10 und 11)

- Aufträge: Sperre gegen Doppelstart auf Datenbankebene, Wiederholung eines abgeschlossenen Auftrags ist wirkungslos (`skipped`), identische Werte werden nie doppelt gespeichert, Cursor (Billing Unit Data `from`, Billing Result `updatedsince`) wird nur nach vollständig erfolgreichem Lauf fortgeschrieben.
- Lesende Aufrufe: Wiederholung mit exponentiellem Backoff bei Verbindungsfehlern, Zeitüberschreitungen und 5xx; Pagination mit höchstens 100 Einträgen; Folgeverweise nur auf dem konfigurierten Host; keine Weiterleitungen; Größenlimit für Antworten.
- Schreibende Aufrufe (Übermittlung Ordnungsbegriffsabgleich, Dokumentquittung): genau ein Versuch; nach einer Zeitüberschreitung "Ergebnis unklar" und manuelle Klärung, nie blinde Wiederholung (Abnahmefall 11).
- Teilweise fehlerhafte Abrufe: Status "teilweise erfolgreich" mit Fehler je Abrechnungseinheit im Teilvorgang `fetch`; abgelaufene Zugangsdaten und fehlende Freischaltung werden im Verbindungstest als "Authentifizierung fehlgeschlagen" (HTTP 401 oder 403 je Familie) ausgewiesen; der letzte erfolgreiche Abruf bleibt erhalten.
- Dokumente: Zuordnung vor dem Download, unbekannte Kennungen in den Klärungsbereich, Wiederabruf ohne Dublette, geänderte Abrechnung als neue Version, Quittung erst nach dem Commit der Speicherung, bei Speicherfehler keine Quittung; Sichtbarkeit nur Mandant, keine Portalfreigabe durch den Import.
