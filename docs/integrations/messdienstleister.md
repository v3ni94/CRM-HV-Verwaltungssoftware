# Messdienstleister (Heizkosten, Wasser, Rauchwarnmelder)

Stand 26.09.2026, Stufe 1 des Moduls `mhvp.metering` (Regel `docs/rules/M40-01.md`, Masterprompt Messdienstleister des Betreibers). Diese Datei ist das Betreiberdokument: Anbieterstand, was das CRM heute kann, was blockiert ist und welche Zugänge oder Unterlagen fehlen.

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
| ista | Entwicklerportal mit Stammdaten- und Ordnungsbegriffsabgleich (Billing Unit Data, asynchron, Q8), Rollen (On-Site Roles 2.0, Q10), Billing Input (finale Übertragung kann eine Abrechnung auslösen, Q11), Billing Result, Dokumente und monatliche Verbrauchsdaten (Q1). Authentifizierung je API-Familie unterschiedlich, mTLS im Test- und Produktionszugang verschieden (Q9) | nicht implementiert (Stufe 2, erster Kandidat) | Entwicklerzugang, Testsystem, Zertifikate und die technische Spezifikation der freigegebenen Version müssen vorliegen (OPEN_QUESTIONS M40-01) |
| Techem | DXS und DXS Dynamic API werden angeboten (Q2); die Angebotsseite ersetzt keine technische Endpunktdokumentation | nicht implementiert | Technische Dokumentation und Vertragsfreischaltung beim Anbieter anfordern (M40-02) |
| KALO / Kalorimeta | Entwicklerportal für Nutzerwechsel zur uVI, Verbrauchsdaten, uVI-Dokumente und DTA-Datenaustausch (Q3); Unterstützung neuer Billing-APIs daraus nicht ableitbar | nicht implementiert (Stufe 2, zweiter Kandidat) | Zugang zum Entwicklerportal und Kundenfreischaltung (M40-01) |
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
5. "Jetzt abrufen" erst nach erfolgreichem Verbindungstest und Freischaltung; in Stufe 1 nur mit dem Testdouble in Testumgebungen möglich.

## 6. Nicht ausgeführte Prüfungen

Es liegen keine realen Zugangsdaten, Testsysteme oder technischen Spezifikationen vor. Alle automatischen Tests laufen mit künstlichen Daten gegen ein Testdouble (`FakeAdapter`). End-to-End-Prüfungen gegen Sandbox- oder Produktivsysteme wurden nicht durchgeführt; die Abnahmefälle 7, 10 und 11 des Masterprompts sind erst mit einem dokumentierten Adapter prüfbar.
