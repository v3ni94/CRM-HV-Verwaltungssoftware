# Versionsverlauf MH Verwaltungsplattform

Schema MAJOR.MINOR.PATCH: erste Stelle (2.0, 3.0) für grundlegende Umbauten, zweite Stelle
(1.1, 1.2) für neue Funktionen oder Module, dritte Stelle (1.2.1, 1.2.2) für kleine
Korrekturen. Die aktuelle Nummer steht in `VERSION`, die Oberfläche zeigt sie im Footer und
unter `/version` (Quelle `apps/web-crm/src/lib/changelog.ts`). Neue Einträge oben anfügen.

## 1.10.0 (25.09.2026) Tickets mit Sammelstatus und Vorlagen, Start-Auswertungen, Handy-Oberfläche, KI-Stückelung

- Tickets: Sammelauswahl mit Statuswechsel (Mitarbeiter höchstens 10 gleichzeitig, Administratoren unbegrenzt), Ticketvorlagen mit Checklisten und Pflichtfeldern (z. B. IBAN beim Kautionsticket) unter Einstellungen
- Start: Auswertungen mit Kennzahlen und Grafik (Tickets offen, neu und erledigt je Tag, Woche, Monat, Quartal, Jahr), Filter je Benutzer und Vergleich zweier Benutzer
- Menü: Mail und Tickets unter Übersicht, eigene Gruppe Makler (Anzeigen, FLOW-Import, Übergabeprotokoll), WEG-Objekte und WEG-Verwaltung als ein Eintrag, Importassistent ohne Zusatz
- Handy und Tablet: Menü im Vordergrund, Mail-Ansicht ohne seitlichen Überlauf und lesbar auf dem Handy, Chat mit Fortschrittsanzeige und eigener Farbgebung
- KI: Umlaute aus Windows-kodierten CSV-Dateien korrekt, große Listen werden in Teilen verarbeitet statt gesperrt, automatische Wahl des großen Modells bei Umfang, Fortschritt je Teil, Zeichenstatistik je Datei im Lauf
- Buchhaltung: Auswertungen je Buchungskreis (Liquiditätsvorschau 90 Tage, Zahlungen je Debitor, Erträge je Erlöskonto)
- Makler: Anzeigenformulare in Gruppen (Objekt, Adresse und Freigabe, Preise mit Warmmiete, Energieausweis, Ausstattung, Vermarktung)
- Tests: Integrationstests für DMS-Anzeige und Immoware-Spiegel

## 1.9.2 (25.09.2026) OIDC-Anbieter für die Statusseite zusammengeführt

- Das CRM stellt eine OpenID-Connect-Anmeldung für angebundene Dienste bereit, zuerst genutzt von der Statusseite status.mueller-holding.ag
- Zweig für die Statusseiten-Anmeldung in den Hauptstand übernommen, damit spätere Deploys die Funktion behalten (Runbook docs/runbooks/oidc-relying-parties.md)

## 1.9.1 (25.09.2026) Google Drive per OAuth verbinden

- Auf der DMS-Seite verbindet ein Klick auf Mit Google verbinden das Drive-Konto, Client-Secret und Refresh-Token werden automatisch hinterlegt
- Manuelle Eingabe bleibt als Alternative erhalten

## 1.9.0 (25.09.2026) Immoware24-Lesezugriff per DAV

- Neues Paket `mhvp.immoware`: Spiegel von Immoware24 per WebDAV, CardDAV und CalDAV, strikt lesend (kein Schreibpfad, es gibt keine Immoware24-REST-API)
- Anbindung je Tenant mit Verbindungstest (PROPFIND Depth 0), manueller und automatischer Abholung (Celery-Beat alle 15 Minuten, `poll_minutes` je Tenant)
- Dokumentbaum (Ordner und Dateien mit geratener Objektnummer), Adressbuch (Kontakte mit Zuordnung zu oder Anlage als CRM-Kontakt) und Kalender (Termine) als durchsuchbare Spiegeltabellen
- Backend-Endpunkte `/api/v1/immoware/...`; Frontend-Einstellungsseite und Übersichtsseite folgen in einem weiteren Schritt

## 1.8.0 (25.09.2026) Gehilfenzugang für Übergabeprotokolle über das Portal

- Makler, Übergabeprotokolle: Portalzugang je Beteiligtem mit CRM-Kontakt einrichten und beenden; Portalkonto wird bei Bedarf angelegt, Einladungscode einmalig angezeigt
- Portal (apps/web-portal): Anmeldung mit Passwort und zweitem Faktor, Liste der eigenen Übergabeprotokolle, Ausfüllen der Abschnitte, Fotos, Unterschrift, Abschluss; interne Vermerke der Verwaltung bleiben verborgen
- Nach dem Abschluss durch den Beteiligten bleibt das PDF im Portal 14 Tage lesbar, danach erlischt der Zugang; Zustellung weiterhin nur über den Postausgang
- Portal-API `/api/v1/portal/handover`, Regel M30-01 ergänzt, offene Fragen M30-01 (Einladungscode) und M30-05 (zweiter Faktor für Gehilfen)

## 1.7.0 (25.09.2026) Übergabeprotokolle im Bereich Makler

- Neuer Unterpunkt Makler, Übergabeprotokolle: Anlage mit Vorbelegung aus Objekt und Einheit, Beteiligte aus den Kontakten, Zähler, Räume, Mängel, Schlüssel, Gegenstände, Bemerkungen, Fotos und Anhänge als Dokumente
- Unterschriften per Canvas mit Prüfsumme, Hinweise vor dem Abschluss, Abschluss mit PDF auf dem Briefbogen, Festschreibung, neue Versionen ohne Dateiduplikate, Stornierung, Archivierung
- Zustellung an die Beteiligten als E-Mail-Entwurf im Postausgang (Vier-Augen-Freigabe), kein automatischer Versand
- Protokollnummern UP-JJJJMMTT-NNN aus der Nummernfolge je Mandant und Tag
- Migration 0043 (Tabellen handover_*), Regel M30-01, Plan docs/plans/M30-uebergabeprotokoll.md, offene Fragen M30-01 bis M30-04 (Gehilfenzugang über das Portal folgt als Stufe 3)

## 1.6.1 (25.09.2026) Google Drive auf der DMS-Seite einrichtbar

- Google-Drive-Anbindung wird auf der Seite DMS-Anbindung eingerichtet: Wurzelordner, OAuth-Client, Zugangsdaten

## 1.6.0 (25.09.2026) Einstellungsseite DMS-Anbindung

- Neue Einstellungsseite DMS-Anbindung: Paperless-Basis-URL, API-Token und die Feld-IDs Objektnummer und Gesellschaft im Browser pflegbar
- Google Drive wird auf derselben Seite nur lesend angezeigt (aktiv, Basis-URL, Token hinterlegt)
- Karte DMS-Anbindung in den Einstellungen, sichtbar mit dem Recht tenant_settings:update

## 1.5.1 (25.09.2026) Korrektur Migration SLA

- Migration 0042 verwendet den vorhandenen Typ ticket_priority statt ihn erneut anzulegen (Enum sla_alert_channel ebenfalls nur einmal), der Deploy brach bisher mit DuplicateObject ab

## 1.5.0 (25.09.2026) Paperless-Dokumente in Ticket und Objekt

- Abschnitt Dokumente (Paperless) in der Ticketansicht und in der Objektansicht mit Vorschau und Download
- Suche in Paperless über die Objektnummer (Custom Field) und die Ticketnummer im Volltext, Treffer werden zusammengeführt
- Dateien werden über das CRM durchgereicht, der Paperless-Zugang bleibt serverseitig
- Feld-IDs für Objektnummer und Gesellschaft je Mandant in der DMS-Anbindung einstellbar (Optionen object_field_id, company_field_id)
- Versionsnummer im Footer mit Verlauf unter /version
- Plan docs/plans/M31-paperless-view.md, keine Migration

## 1.4.0 (25.09.2026) SLA, Notfallkette und Bereitschaft

- SLA-Regeln je Ticketpriorität mit Reaktions- und Lösungszeit, Uhren laufen nur in der Geschäftszeit
- Arbeitskalender mit Feiertagen, Uhren lassen sich pausieren und fortsetzen
- Eskalationsstufen mit Benachrichtigung an Zuständige und Bereitschaft
- Bereitschaftsplan mit aktueller Bereitschaft und Alarmen zum Quittieren
- Einstellungsseite SLA und Bereitschaft, SLA-Ampel im Ticket
- Erste Antwort per freigegebener Mail stoppt die Reaktionsuhr
- Migration 0042, Plan docs/plans/M30-sla.md

## 1.3.0 (25.09.2026) KI-Vorschläge und Playbooks für Mails

- KI-Antwortvorschlag je eingehender Mail im Ticket
- Playbooks werden aus abgeschlossenen Tickets gelernt und beim nächsten gleichartigen Vorgang angeboten
- Tickets zusammenführen zu einem neuen Ticket mit neuer Nummer, Verlauf bleibt erhalten
- Migrationen 0037 und 0041

## 1.2.0 (24.09.2026) Postfach im CRM

- Gmail-Abruf je Postfach, jede Mail wird einem Ticket zugeordnet oder eröffnet ein neues
- Google-OAuth-Einstellungen, Standardpostfach und Zugriff je Benutzer
- Mail-Reiter im Ticket mit Vier-Augen-Freigabe vor dem Versand über Gmail
- Fehlerhafte Einzelmails brechen den Abruf nicht mehr ab und werden gemeldet
- Migrationen 0035, 0036, 0039, 0040

## 1.1.0 (24.09.2026) Makler, DMS-Bereich und neue Oberfläche

- Maklerbereich mit Miet- und Kaufangeboten, Felder nach FLOW-Datenvertrag, FLOW-Import
- DMS-Bereich mit Anbindung der Objektübernahme (objektakte)
- Überarbeitetes Design mit dunkler Navigationsleiste, Seitenköpfen und Dashboard-Kacheln, mobile Ansicht
- Einstellungsbereich mit Benutzerverwaltung, Rollen, Mandant, Profil
- KI-Assistent auf jeder Seite mit Seitenkontext, Auswertung aller Chats für Revisionsleser
- Mehrkern-Auslegung für API, Celery und PostgreSQL im Produktivbetrieb

## 1.0.0 (23.09.2026) Marktreife der Grundplattform

- Mandantenfähige Plattform mit Rollen, Rechten und Revisionsprotokoll (M1, M2)
- Kontakte, Objekte, Einheiten, Verträge (M3 bis M5)
- Dokumente mit Aufbewahrung, DMS-Spiegel (Paperless, Google Drive), Briefe und Serienbriefe (M6)
- KI-Gateway, Onboarding-Chat, Immoware24-Import, Oberfläche und Betrieb (M7 bis M9)
- Buchungskreis, Bankanbindung, Matching mit KI-Kontierung, Sollstellung, Verwalterhonorar (M10 bis M13)
- Belegeingang, Kreditoren, Zahlläufe, Mahnwesen, Mietabrechnung, Auswertungen und Exporte (M14 bis M18)
- Tickets und Aufträge, Postfach, Portale für Mieter, Eigentümer und Dienstleister, Kommunikation (M19 bis M23)
- WEG-Wirtschaftsplan und Abrechnung, Versammlung, Beiratsprüfung, Mieterhöhung und Vermietung, Marktreife (M24 bis M27)

## 1.4.0 (24.09.2026) Rückwirkend: Stand vom 24.09.2026 vor Einführung des Versionsverlaufs

- Mietrecht: Regelwerk und Kappungsgebiete NRW, Mieterhöhungsprüfung mit Begründungsmitteln
- Betrieb: Produktivstack auf dem Betreiberserver mit Traefik, Let's Encrypt, Backup-Timer, Wiederherstellungstest, Health-Check, Mehrkern-Einstellungen für API, Celery und PostgreSQL
- Oberfläche: CI der Müller Holding AG, dunkle Seitenleiste mit Icons, Seitenköpfe, Kennzahlen-Kacheln, Anmeldeseite, Dunkelmodus, Bedienung auf Handy und Tablet
- KI: OpenAI als zweiter Anbieter, Anbieterreihenfolge mit automatischem Wechsel, Wiederholung bei Ratenlimit, Chatblase auf jeder Seite mit geführten Importen, Assistent als Protokollseite aller Chats
- Verwaltung: Filter Mietverwaltung, WEG und SEV, Objektebereich, Benutzerverwaltung mit Rollen, Passwort zurücksetzen und Sperren, Benutzermenü, Einstellungen, Mandanten anlegen
- Makler: Anzeigen für Vermietung und Verkauf je Einheit, Felder aus dem FLOW-Datenvertrag, Import des FLOW-Datenbankexports mit Vorschau und Übernahme
- DMS: Bereich mit Absprung in die Objektübernahme je Objektnummer
- Postfach: Gmail-Abruf mit Ticket je Mail, Fehler je Nachricht isoliert
