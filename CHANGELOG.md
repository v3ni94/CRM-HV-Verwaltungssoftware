# Versionsverlauf MH Verwaltungsplattform

Schema MAJOR.MINOR.PATCH: erste Stelle (2.0, 3.0) für grundlegende Umbauten, zweite Stelle
(1.1, 1.2) für neue Funktionen oder Module, dritte Stelle (1.2.1, 1.2.2) für kleine
Korrekturen. Die aktuelle Nummer steht in `VERSION`, die Oberfläche zeigt sie im Footer und
unter `/version` (Quelle `apps/web-crm/src/lib/changelog.ts`). Neue Einträge oben anfügen.

## 1.30.1 (27.09.2026) Betrieb: Migrationssperre, Objektspeicher lokal als Standard

- CI-Prüfung und Skript `scripts/check-migrations.sh`: bereits gemergte Alembic-Migrationen dürfen nicht mehr umbenannt, gelöscht oder in Revision und down_revision geändert werden. Neue Migrationen fortlaufend ab dem bisherigen Head. Runbook `docs/runbooks/migrationen.md`.
- Objektspeicher: SeaweedFS-Container ohne Profil dauerhaft aktiv, Migrationsjob wartet auf den Dienst, S3-Variablen standardmäßig lokal. Backup des Volumes `mhvp_objectstore-data` als Vorgabe in `env.backup.example`. Runbooks und ADR 0005 ergänzt (Entscheidung 27.09.2026).

## 1.30.0 (27.09.2026) Masterprompt-Ergänzung Welle B: Inline-Bearbeitung, Objekt- und Gebäudeseiten, Kataloge, Messdienstleister Stufe 3

- Stammdaten direkt bearbeiten (ADR 0012): Objekt, Gebäude, Einheit und Kontakt werden an Ort und Stelle mit Stift oder Bearbeiten je Abschnitt geändert, Speichern je Feld beim Verlassen mit sichtbarem Speicherstatus, Feldfehlern, Versionsprüfung und Konflikthinweis; beim Vertrag Bemerkungen und Mahnsperre mit Begründungspflicht, alles Übrige bleibt versioniert über das Vertragsformular; PATCH-Endpunkte für Objekt, Gebäude, Einheit, Kontakt und Vertragsbemerkungen mit Ereignisprotokoll und Änderungsdiff
- Objekt-, Gebäude- und Einheitenseiten: neue Gebäudeseite mit Energieausweis, Anzeige von Eigentümerdetails (Verrechnungskonto, Vollmacht, Steuerberater), Abrechnungszeiträumen, Untergemeinschaften, Objektmappe, Dienstleistern mit Freistellungsbescheinigung, Leerstandswerten und Zählerwechseln; Verknüpfungsleiste und Ereignisprotokoll auf Objekt, Gebäude, Einheit, Kontakt und Vertrag
- Kataloge und benutzerdefinierte Felder (4.11, Anhang B): alle Auswahllisten je Mandant als Systemeinträge mit Erweiterung und Deaktivierung, Zusatzfelder mit Gruppe, Gültigkeit, Eindeutigkeit, Min und Max, Standardwert und Feldtypen, neue Einstellungsseiten Kataloge und Felder (Migration 0152)
- Messdienstleister Stufe 3: kontrollierte schreibende Vorgänge mit getrennten Schritten Daten prüfen, Freigeben und Abrechnung verbindlich beauftragen beziehungsweise Nutzer und Rollen verbindlich übermitteln (On-Site Roles 2.0 mit vollständigem Datensatz je Nutzeinheit, Billing Input mit Anbietervorlage und Anbieterprüfung), Datenversion entwertet Freigaben bei jeder Änderung, Protokoll je Schritt, Zeitüberschreitung ohne Wiederholung; Freigabe je Verbindung, Modulschalter in den Mandanteneinstellungen, Anbieterwechsel und Einheitenbearbeitung im Objektreiter (Migration 0153)

## 1.29.0 (27.09.2026) Masterprompt-Ergänzung Welle A: Kontakt, Objekt und Einheit, Vertrag, Suche und Verknüpfungen, Kalender aus Datumsfeldern, Messdienstleister Stufe 2

- Kontakt nach Abschnitt 4.1 erweitert: Briefanrede, Bundesland, Landesvorwahl, Vorwahl und Notiz je Telefon, Datumsfelder, Kontotyp und Standardkonto je Bankverbindung, Sperrdatum, Löschprofil mit vorgemerktem Löschdatum (Löschung weiterhin manuell im Vier-Augen-Prinzip), Sperrliste, Notizen mit Titel und Wiedervorlage sowie die Reiter Beziehungen, Dokumente, Portal-Freigaben und Ereignisprotokoll (Migration 0147)
- Objekte, Gebäude und Einheiten nach Abschnitt 4.2 bis 4.4 erweitert: Energieausweis vollständig und ausschließlich am Gebäude (Migration übernimmt Objektwerte), Gebäude und Einheit mit Versionsprüfung (ETag), Abrechnungszeiträume je Art, Untergemeinschaften, Objektmappe, Eigentümer mit Verrechnungskonto, Vollmacht und Steuerberater, Bankkonto mit Sachkonto, Dienstleister mit Kundennummer, Freistellungsbescheinigung und Kreditorenkonto, Einheit mit Provision, Kautionsbetrag und Leerstands-Umlagewerten, Zählerwechsel (Migrationen 0148, 0149)
- Verträge: vertragsbezogene Umlagewerte mit Zeitraum, SEPA-Mandate mit Ertragsarten und Sonderumlage-Ausschluss, Einzugs- und Auszugsdatum, Vertragsbeendigung mit Zählerständen, Listen beendeter Verträge, Kautionen und Leerstand zum Stichtag; Vertragsseite mit Abschnitten Eigenschaften, Mandate und Debitorenkonto (Migration 0150)
- Globale Suche findet jetzt auch Gebäude, Tickets (auch als #Nummer) und Buchungen mit Berechtigung je Trefferart; Verknüpfungsleiste und Ereignisprotokoll mit CSV-Export je Datensatz, zunächst im Ticketdetail; Änderungsprotokoll filtert nach Entitätstyp
- Kalender und Fristen vereinheitlicht: Termine entstehen deterministisch aus Datumsfeldern (Eichdatum, Energieausweis, Vertragsende, Ein- und Auszug, Sanierung, Wiedervorlage, Versammlung), tragen Quelle, Kategorie und Erinnerungen und verlinken zur Quelle (Migration 0151)
- Messdienstleister Stufe 2: Oberfläche unter Einstellungen, Schnittstellen (Verbindungen, Einrichtungsassistent mit ehrlichem Funktionsstand, zentrale Zuordnungsübersicht mit Sammelfreigabe, CSV) und Reiter am Objekt (Zuordnungen, Einheiten, Abruf je Datenart, Verbrauch, Abrechnungsergebnisse, Klärung); lesende Adapter für ista und KALO nach bved-Spezifikationen, Dokumentenübernahme ohne Dubletten und mit Versionierung, Auftragsausführung mit Sperre, Cursor und Wiederholungen; Fähigkeitsmatrix im Betreiberdokument
- Betrieb: Migration 0146 idempotent, damit der Produktionsstand mit vorab eingespielter Vertragsfreigabe durchläuft

## 1.28.0 (26.09.2026) Betreiberentscheidungen vom 26.09.2026 umgesetzt: Gmail-Push und Vollabruf, Ticketampel und Auswertung, Kaution, Bank finAPI, Messdienstleister Stufe 1, Betrieb

- Messdienstleister (neues Modul `mhvp.metering`, Stufe 1 Backend, Regel M40-01, Migration 0145): Anbieterkatalog ista, Techem, KALO, Brunata Minol, BRUNATA-METRONA und Sonstige mit ehrlicher Funktionsanzeige in vier Dimensionen (dokumentiert, Adapter, Kontofreigabe, Verbindungstest) und Recherchestand 26.09.2026 (Quellen Q1 bis Q11, vor Implementierung erneut prüfen); zentrale Verbindungen je Mandant mit verschlüsselten Geheimnissen (nur setzen, nie auslesen), Test und Produktion getrennt, Verbindungstest nur lesend; Objektzuordnung zu externen Abrechnungseinheiten mit Leistungsbereich, Gültigkeit, Prüfstatus, Gruppierung, Konfliktprüfung, Versionsprüfung (409) und Anbieterwechsel mit Historie; Einheitenzuordnung mit getrennten Empfängern und Belegungsstatus; manueller Abruf als persistenter Auftrag, Klärungsbereich, Verbrauchswerte und Abrechnungsergebnisse versioniert ohne Buchung; CSV-Vorlage, Vorschau, Übernahme und Export; Rechte metering_connections:manage, metering_assignments:update, metering_sync:run, metering_data:read, metering_users:submit, metering_billing:order; Mandantenschalter metering_module_enabled (Standard aus); Endpunkte unter /metering; keine Anbieteradapter (Stufe 2, OPEN_QUESTIONS M40-01 bis M40-03); Oberfläche folgt
- Tickets: Ampel je Ticketzeile nach Zeit ohne Reaktion unsererseits (gelb neu, orange ab 24 Stunden, rot ab 96 Stunden, grün erledigt), serverseitig berechnet in derselben Abfrage (Felder last_staff_activity_at, last_inbound_at, last_activity_at, attention in GET /tickets und auf der Startseite), nur Handlungen von Mitarbeitern zählen (Statuswechsel, Zuweisung, Kommentar, gesendete Mail, Arbeitsauftrag), eingehende Mails und Portalkommentare setzen die Uhr nicht zurück; Standardsortierung Dringlichkeit (sort=urgency, Erledigte zuletzt), Filterhaken Nach Eingang (sort=created_desc); Legende, Textmarke mit Dauer und farbiger Rand in Übersicht, Meine Tickets, Startseite und Reiter Tickets; Reiter Tickets der Kontakt-, Objekt- und Einheitenseite blendet Erledigte standardmäßig aus (Umschalter Erledigte anzeigen); Regel M19-09, Handbuch Tickets
- Buchhaltung: Kostenkonten der Kontenrahmen-Vorlage als Entwurf nach der Betriebskostenverordnung vorbelegt (M10-02, Betreiberentscheidung 26.09.2026): Konten der Betriebskostenarten des Katalogs umlagefähig mit Abrechnungsart Betriebskosten und Schlüsselvorschlag (Wohnfläche, Verbrauch für Heizung, Warmwasser und Wasser), Heizungsreparaturen nicht umlagefähig, Rauchwarnmelder ohne Einordnung, Umsatzsteueroption bleibt offen; je Zeile Prüfkennzeichen Entwurf mit Vermerk "Freigabe durch Steuerberatung offen"; Seed füllt nur unbesetzte Felder und verändert eigene Einträge und bestehende Buchungskreise nicht; Zuordnungstabelle in Regel M10-02, Handbuch Buchhaltung
- Dokumente: Löschung gespiegelter Dokumente nach Betreiberentscheidung M6-03 vom 26.09.2026: Drive-Kopie wird gelöscht (endgültig, ersatzweise Papierkorb, im Journal vermerkt), Paperless-Dokument bleibt erhalten und erhält das Schlagwort "gelöscht" (wird angelegt, falls es fehlt), beide Schritte im Löschjournal mit Erfolg oder Fehler, Löschung "offen" bis beide Schritte gelungen sind, Wiederholung per Task, neue Endpunkte GET /documents/deletions und POST /documents/deletions/{id}/retry (Migration 0143), Sperre gespiegelter Dokumente entfällt, Restore-Wiederanwendung behandelt gespiegelte Dokumente gleich
- Bank: finAPI (M11-01, Betreiberentscheidung 26.09.2026: Aggregator finAPI zuerst, Datei-Import bleibt, EBICS später): Konten- und Umsatzabruf hinter der bestehenden Aggregator-Schnittstelle, OAuth2 Client-Token plus technischer finAPI-Benutzer und Benutzer-Token je Bankverbindung (verschlüsselt, kein Auto-Update durch den Anbieter), WebForm-Import ohne Bankzugangsdaten, inkrementeller Umsatzabruf je Konto mit Cursor und Überlappung, idempotenter Upsert nach Transaktions-ID, Beträge als NUMERIC, Standard-Basis-URL je Rechenzentrum (Sandbox oder Live, Einstellungen MHVP_FINAPI_BASE_URL_SANDBOX und _LIVE), Fehlercodes MHVP-BANK-0005 (Zugangsdaten abgelehnt) und MHVP-BANK-0006 (Ratenlimit, ohne automatische Wiederholung), Migration 0141; keine Zahlungsauslösung, G2 bleibt geschlossen; Doku docs/integrations/finapi.md
- KI: Einbettungen und Ähnlichkeitssuche (M7-03, Betreiberentscheidung 26.09.2026): OpenAI text-embedding-3-small über den vorhandenen Adapter (EU-Endpunkt bei Region eu), Speicherung in pgvector je Mandant mit RLS (Tabelle ai_embedding, Migration 0142), Indexlauf als Celery-Aufgabe in Stapeln mit Budgetzählung (Aufgabe embed) und maskierter Eingabe, answer_question und Wissensbasis der Mail-Vorbereitung suchen per Ähnlichkeit mit Schlüsselwort-Rückfall, neue Endpunkte POST /ai/embeddings/reindex und GET /ai/embeddings/status
- Betrieb: Lesezugang der Überwachung auf die Betriebskennzahlen (M9-04a, Betreiberentscheidung 26.09.2026): neues Recht platform:metrics:read, das nur ein von einem Plattformadministrator erzeugter API-Schlüssel trägt (POST, GET, DELETE /platform/ops/metrics-keys, Geheimnis einmalig, Ereignisse api_key.created und api_key.revoked, Ratenlimit wie jeder Schlüssel), GET /platform/ops/metrics (JSON und Prometheus) nimmt Plattformadministrator-Sitzung oder diesen Schlüssel an, jeder andere Endpunkt weist den Schlüssel ab, keine Migration; Runbook monitoring.md 3.1 mit Anleitung für Uptime Kuma
- Benachrichtigungen: jede Benachrichtigung trägt ein Ziel (target_type, target_id) und einen vom Server abgeleiteten Link (href) zum Betreff; ein Klick im CRM öffnet Ticket, Auftrag, Mail, Dokument, Vertrag, Objektakte, Fristenliste oder den Kalender mit geöffnetem Termin (/kalender?termin=...) und markiert nur diesen Eintrag als gelesen; Portal: neue Endpunkte GET /portal/notifications und POST /portal/notifications/read mit Portalrouten (Meldung, Auftrag, Übergabe) und Liste auf der Übersicht
- Dokumente: Standard-Aufbewahrungsprofile je Mandant als Entwurf (Entwurf, Prüfung Steuerberatung offen; Betreiberentscheidung M6-04 vom 26.09.2026: Belege, Journale, Abrechnungen 10 Jahre; Geschäftsbriefe, Vorgänge, Mails 6 Jahre; Verträge 10 Jahre nach Ende; Portal- und Bewerberdaten 6 Monate nach Zweckende; WEG-Protokolle und Beschlüsse dauerhaft), Seed idempotent ohne Überschreiben eigener Änderungen, Löschung bleibt bis zur Freigabe gesperrt, Freigabe nur mit Recht Mandanteneinstellungen im Vier-Augen-Prinzip und protokolliert, Felder retention_months, permanent, review_note, status (Migration 0139), noch keine Einstellungsseite (nur API)
- Buchhaltung: Ausgleich offener Posten nach gesetzlicher Reihenfolge als Vorschlag (M10-03, Betreiberentscheidung 26.09.2026): POST /accounting/ledgers/{id}/open-items/settlement-proposal berechnet deterministisch (fällig vor nicht fällig, geringere Sicherheit, größere Last, ältere zuerst, Kosten vor Zinsen vor Hauptforderung), Bestimmung des Zahlers aus Verwendungszweck oder Liste geht vor (D39), Überzahlung bleibt Guthaben; Bestätigung über .../confirm erzeugt einen Buchungsentwurf mit Ausgleichsplan und protokolliert Regelversion und Fingerabdruck, sofortiges Buchen nur mit G1; Karte auf der Buchungskreisseite; Vermerk „Rechtsprüfung vor G1 offen“, Regel M10-03, Handbuch Buchhaltung
- Anmeldung (Betreiberentscheidung M2-01 vom 26.09.2026): Mindestlänge des Passworts 6 Zeichen (Kontosperre nach 10 Fehlversuchen für 15 Minuten unverändert; Hinweis auf die längere BSI-Empfehlung nur in der Dokumentation), zweiter Faktor für CRM und Portal nicht mehr Pflicht (auch nicht für Administratoren), Einrichten und Ausschalten unter Einstellungen, Meine Daten (CRM) und Sicherheit (Portal, neue Seite) mit neuen Endpunkten POST /auth/totp/setup, /confirm, /disable und totp_enabled in GET /auth/me, Anmeldeschritt mfa_setup_required und POST /auth/mfa/setup entfallen; gemerkte Geräte 90 statt 180 Tage (Dieses Gerät 90 Tage merken), jetzt auch im Portal, Liste und Abmelden in den Einstellungen; Regel M2-01, ADR 0006 zweiter Nachtrag, offene Frage M2-09 (Prüfung gegen kompromittierte Passwörter nicht vorhanden)
- Tickets und Mail: Gmail-Push per Pub/Sub (Nachrichten erscheinen sofort, Abruf alle fünf Minuten als Sicherheitsnetz, Watch-Erneuerung täglich), Vollabruf des gesamten Posteingangs beim Verknüpfen und manuell je Postfach (Button und Serverbefehl python -m mhvp.communication.backfill), Mail auf erledigt archiviert sofort in Gmail und schließt das Ticket automatisch mit Auskunft erteilt, wenn keine Mail und kein Arbeitsauftrag mehr offen ist (Migration 0144)
- Tickets: Erledigungsarten um Zahlung geklärt, Termin vereinbart, Mangel behoben, Vertrag geändert erweitert und je Mandant pflegbar (Migration 0136, Einstellungen Mandant); Freigeben und antworten der Telefonassistenz legt keinen Entwurf ohne Empfänger an; Ticketsuche findet auch Mailinhalt und interne Beschreibung
- Auswertung Tickets: neue Seite mit Durchsatz je Tag, Woche, Monat, Quartal und Jahr, erledigte Tickets je Stunde und Minute, Erstreaktion und Bearbeitungsdauer (Median, 90. Perzentil), Rückstand, Tabellen je Mitarbeiter und je Postfach (persönlich oder Standardpostfach), CSV-Export
- Kontakte: Mehrpersonen-Parteien aus dem Immoware24-Adressbuch als eine Partei mit Mitgliedern, Bevollmächtigte mit Zustellregel (beide, nur Bevollmächtigter, nur Eigentümer) für Serienbriefe, Serienversand und WEG-Einladungen (Migration 0140)
- Verträge: Kautionsabrechnung als Entwurf mit Zinsart je Abrechnung (individuell je Jahr, Referenzzinssatz je Jahr aus den Einstellungen, ohne Zins), Freigabe hinter G3 (Migration 0138, Regel M5-02)
- Buchhaltung: Erlöskonten der Mietverwaltung 060300 bis 060800 als Vorschlag mit Prüfkennzeichen Entwurf (Migration 0137, M10-01)
- KI: Lernbeispiele nur bei aktivem Mandantenschalter, Löschung bei Kontaktlöschung (Migration 0134, ADR 0010); zweiter Anbieter mit Wechsel bei Fehler oder Budget, Endpunktregion wird an den Anbieter durchgereicht (M7-02, M7-07)
- Plattform: Superadmin-Kennzeichen und Schalter gate_superadmin_bypass für Gate-Freigaben ohne zweite Person, Standard aus (ADR 0011, Migration 0135); Anmeldung ohne Pflicht zum zweiten Faktor, gemerkte Geräte 90 Tage auch im Portal
- Automatisierung: Regel-Webhooks mit Wiederholung nach Stufenplan, Zustellprotokoll und erneuter Zustellung (A82, Migration 0133)
- Portal: HEIC-Fotos vom iPhone werden angenommen und in JPEG gewandelt (A72); QR-Code im Einladungs-PDF (A86); Kontaktereignisse auch aus Staging- und Objektakte-Import (A87)
- Betrieb: IONOS S3 Object Storage als Produktionsspeicher (make check-s3), Images aus der GitHub Container Registry, Uptime Kuma im Produktions-Compose, Off-site-Backup nach Hetzner Object Storage mit age-Verschlüsselung und Aufbewahrung 14/8/12 (scripts/backup-offsite.sh)
- Oberfläche: Immoware24 nur noch unter Einstellungen erreichbar, nicht mehr im Hauptmenü
## 1.27.1 (26.09.2026) Erledigungsnotiz für Administratoren optional

- Tickets: Mandantenadministratoren schließen Tickets ohne Erledigungsnotiz (einzeln, Sammelaktion), der Abschlussdialog erscheint bei ihnen nicht. Für alle anderen bleibt die Notiz Pflicht.

## 1.27.0 (26.09.2026) Zuordnung im Bericht, Objekteigentümer, Freigabe der Importverträge

- Import: Offene Zuordnungen (nicht gefunden, mehrdeutig, Vermieter fehlt) stehen im Bericht als Tabelle und werden per Kontaktauswahl direkt zugeordnet (POST /imports/immoware24/lists/zuordnung/manuell), bei fehlendem Vermieter mit Auswahl des Objekteigentümers. Der letzte Bericht bleibt im Browser erhalten.
- Objekte: "Eigentümer festlegen" auf der Objektseite für Mietverwaltungsobjekte (Kontakt, seit, Anteil, Ersetzen mit Datum), Reiter "Ohne Eigentümer" und Kennzeichen "Eigentümer fehlt" in der Objektliste (POST /properties/{id}/owner, GET /properties?without_owner=true). WEG-Objekte führen Eigentum je Einheit.
- Verträge: Importverträge tragen Herkunft und Freigabestatus (Migration 0133). Die Sollstellung überspringt nicht freigegebene Verträge und weist das aus. Neue Seite Verträge, Freigabe mit Filter, Summen, Mehrfachauswahl, "Alle freigeben" mit Bestätigung und "Ablehnen" je Vertrag (beendet ihn zum Beginn). Berechtigung contracts:approve (Administratoren). Kennzeichen "Freigabe ausstehend" in Liste und Detail.

## 1.26.1 (26.09.2026) Mail: Aktionen oben, Mehrfachauswahl, Erledigt archiviert

- Mail: Die Aktionen Antworten, Ticket anlegen und Erledigt stehen zusätzlich als feste Leiste oberhalb der Nachricht.
- Mail: Mehrfachauswahl in der Liste (Kontrollkästchen, Strg bzw. Cmd plus Klick, Shift für Bereiche, Alle auswählen, Escape hebt auf) mit Sammelaktion "Als erledigt markieren" (POST /mail/messages/bulk, bis 200 Nachrichten, Postfachzugriff je Nachricht geprüft).
- Mail: "Erledigt" in der Mailansicht archiviert die Gmail-Nachricht wie der Ticketabschluss (Postfacheinstellung "Erledigt archiviert Mail"), einzeln und als Sammelaktion.

## 1.26.0 (26.09.2026) Portalzugang am Kontakt, IBAN-Ablehnungsgrund, Importereignisse, Dokumentliste, Telefonassistenz-Korrekturen

- Kontakte: Abschnitt Portalzugang auf der Kontaktakte mit Status (kein Zugang, eingeladen, aktiv, gesperrt), Einladung mit QR-Code und neuem Leseendpunkt GET /portal-admin/accounts?contact_id (A86, CRM-Teil)
- Kontakte: Ablehnungsgrund der IBAN-Freigabe wird gespeichert und angezeigt (rejected_reason, rejected_by, rejected_at, Migration 0132), Kontaktliste zeigt den Hinweis IBAN wartet auf Freigabe ohne N+1
- Importe: Listen- und Zuordnungsimporte lösen dieselben Ereignisse contact.created und contact.updated aus wie die manuelle Pflege (Regelwerk und Webhooks greifen, A87 teilweise)
- Dienstleisterverträge: Anzeigename des Dienstleisters in Liste und Detail statt Kennung
- Dokumente: neue Dokumentliste im CRM mit Volltextsuche und Entwurfsfilter (is_draft), Upload bei fehlendem oder nicht erreichbarem Dokumentenspeicher antwortet mit 503 MHVP-DOC-0007 statt 500, keine halben Dokumentzeilen
- Tickets: Freigeben und antworten der Telefonassistenz legt keinen Entwurf ohne Empfänger mehr an (422 mit Hinweis), Zusammenführen protokolliert je Quellticket Statusereignis mit Erledigungsnotiz und Lernbeispiel
- Abnahme: Playwright gegen den Stack 12 CRM und 11 Portal grün, zwei Specs an die neue Anzeige angepasst (Bruttobetrag formatiert, Anhangsliste der Meldung), spezifische Spec-Läufe über MHVP_E2E_PW_ARGS
- Dokumentation: Handbuch für Erledigungsnotiz, Telefonassistenz, ausgeblendete erledigte Vorgänge, Objektbezüge und Wissen; Regeln M19-07 bis M19-09, ADR 0010 Lernbeispiele (Betreiberentscheidung), offene Fragen M19-03 und M19-04, Lückenliste A90 bis A99
- Offen (Betreiber): Datenschutzregel für Lernbeispiele (M7-04, ADR 0010), AVV und Anbieterfreigabe Telefonassistenz (M19-03), Erledigungsartenliste (M19-04), QR-Code im Einladungs-PDF (M21-08)

## 1.25.1 (26.09.2026) Adressen nachtragen, Einheitenliste und Einheitenseite

- Importe: Abschnitt "1a. Adressen nachtragen" auf der Listenimport-Seite: Straße und Hausnummer aus den Objektnamen ableiten oder eine Adressliste (Objektnummer, Straße, Hausnummer, PLZ, Ort; CSV oder XLSX) hochladen. Füllt nur leere Felder, meldet Abweichungen als Konflikt.
- Objekte: Einheiten natürlich sortiert (1, 2, 10 statt 1, 10, 2), bei rein numerischen Nummern dreistellige Anzeige. Nummer und Bezeichnung verlinken auf die Einheitenseite. Neue Spalten Eigentümer, Mieter ("kein Mieter") und Fläche.
- Einheitenseite: alle Stammdaten (Typ, Lage, Fläche, Miteigentumsanteile, Umlageschlüssel, Zusatzfelder, Altsystem-Notizen), Karten Eigentümer und Mieter mit Kontaktlink, seit, Anteil und Miete, beendete Verträge aufklappbar. Neue Endpunkte GET /units/{id}/occupants und /properties/{id}/units?with_occupants=true.

## 1.25.0 (26.09.2026) Zusammenführung mit 1.24.0 und Fix- und Abschlusswelle: Vier-Augen nach Betreiberentscheidung, Review-Befunde Tickets und Mail, Sicherheit, Performance, Bedienbarkeit, Vertragsformular, Import-Robustheit, Anhang D 54 von 58

- Tickets und Mail: Betreiberentscheidung M20-03 umgesetzt: Vier-Augen-Freigabe nur für Mitarbeiter mit Kennzeichen Azubi oder neuer Mitarbeiter (Einstellungen, Benutzer, optional befristet), alle anderen senden Ticketantworten direkt; Verfasser und Freigeber mit Zeitpunkt als Ticketereignisse und im Mailverlauf sichtbar; Notbremse alle Antworten mit Freigabe (Standard aus); Freigabeberechtigte werden benachrichtigt (Migration 0129, Regel M20-06)
- Prüfung Tickets und Mail: 31 von 34 Befunden behoben, darunter Doppelversand bei Verbindungsfehler ausgeschlossen (zweiphasiger Versand mit Nachweis), Rechnungsweiterleitung nach Commit, Postfach löschen als Deaktivierung ohne Sichtbarkeitsverlust, Mailliste mit Vorschau statt Volltext, Thread-Zuordnung über References und Gmail-Thread, abgewiesene Anhänge sichtbar, Kommentare mit Autor, interne Beschreibung, Zuweisungsereignis, Archivierung nach Commit, Arbeitsaufträge mit Terminvorschlägen im Ticket (Migration 0126)
- Sicherheit: Review 1.22 ohne hohe Befunde, 5 mittlere und 12 niedrige behoben (Ratenbegrenzung bei gefälschtem API-Key, Größenlimit Paperless-Webhook, Rechtsträgerbereich in WEG-Finanzen, Prüfung, Beirat und Mehrheitsregeln, Aushang-Sichtbarkeit je Zielgruppe, Webhook-Ziel mit gebundener Adresse gegen DNS-Umlenkung, Geheimnisse nur serverseitig, Paketgröße Einsicht, Telefonie-Antwort ohne Trefferstatus)
- Performance: Listen Verträge, Einheiten, Parteien, Journal, Rechnungen, Lastschriftläufe, Dokumenteingang und Startseite ohne N+1 (bis zu 57 auf 11 Abfragen), 18 neue Indizes (Migration 0127), Paginierung Verträge, Mandate, Journal, Rechnungen, Berechtigungskontext je Prozess 30 Sekunden zwischengespeichert mit sofortiger Wirkung von Sperre und Rollenentzug im selben Prozess
- Bedienbarkeit CRM und Portal: 63 Befunde behoben, darunter zwei Seitenabstürze (WEG Prüfauftrag, Objektseite), Kennzahlenkarte Bankabgleich lud im Betrieb nie, Lastschriftläufe haben jetzt eine Seite mit Vier-Augen-Freigabe hinter G2, Rohwerte statt Beträge und Daten in Exposé, Belegeingang und Automatisierung, Fehler- und Ladezustände, mobile Kartenansicht Hausgeldkonto, einklappbares Portalmenü, deutsche Fehler- und 404-Seiten im Portal
- Neue Funktionen: Vertragsformular im CRM für Miet-, Eigentums- und SEV-Verträge mit Zahlungsplan und Kaution; Webhook-Abonnements unter Einstellungen mit Zustellprotokoll; Prüfauftrag Beirat im CRM anlegen mit Positionsfilter und Beiratsstellungnahme (CRM und Portal); Formular-Einreichungen je Vorlage; Terminvorschläge der Dienstleister im CRM; Ratenplan Darlehen als Orientierung, Beschlussbezug am Versicherungsfall, Überleitung im Übernahmejahr (Migration 0128); Regel-Engine mit Bedingungen auf Objekt, Einheit, Kontakt und Vertrag, automatisch erzeugte Briefe als Entwurf gekennzeichnet; OpenImmo-Schemaprüfung mit hinterlegter XSD; Namensmaskierung im Belegeingang für Einzelunternehmer
- Import Immoware24: Listenimport liest Windows-1252, BOM, Semikolon, Komma, Tab, eingebettete Trennzeichen, wiederholte Kopfzeilen und Spalten in beliebiger Reihenfolge; Pflichtspalten mit klarer Meldung; Duplikate gemeldet statt still übernommen; Nummernzuordnung mit führenden Nullen; Telefon und E-Mail in allen Schreibweisen; IBAN nur als maskierter Hinweis; Checkliste im Handbuch
- Abnahme und Tests: Anhang D jetzt 54 von 58 technisch bestanden (offen nur D24 bis D27 wegen fehlender Betreiberregeln); Playwright gegen den Stack 12 CRM und 11 Portal grün inklusive Fototest; 66 neue Abdeckungstests; Ergebnisbuchung nach Eigentümerwechsel repariert, Versionsvergleich der WEG-Abrechnung als Endpunkt und Anzeige; Seed-Skript und Test-Datenbankaufbau stabil
- Dokumentation: Entscheidungsvorlage für den Betreiber (docs/reviews/2026-09-26-entscheidungsvorlage-betreiber.md), Handbuchkapitel für alle Funktionen seit 1.20, Lückenliste konsolidiert (A72 bis A89), Plan-Dokumente mit Stand 26.09.2026, Reviews Performance, Sicherheit 1.22, Bedienbarkeit CRM und Portal
- Offen (Betreiber): OpenImmo-XSD beschaffen (M26-02), Zins und Tilgung in der Jahresabrechnung (M24-03), Heizkosten und Verbrauchsinformation (D24 bis D27), Freigabestufen G1 bis G5 mit Steuerberatung, Rechtsberatung und Bank, Serverhärtung (M9-05)
- Zusammenführung: Stände 1.23.0 bis 1.24.0 der parallelen Sitzung übernommen (Migrationen Erledigungsnotiz und Hallo Heidi laufen jetzt als 0130 und 0131 hinter 0126 bis 0129)

## 1.24.0 (26.09.2026) Ticketfilter, Erledigungsnotiz, Hallo Heidi, Wissensdatenbank, Assistent-Rolle

- Tickets und Mail: Umschalter "Erledigte anzeigen" in den Übersichten, erledigte Vorgänge sind standardmäßig ausgeblendet. Kontakt-, Objekt- und Einheitenseite zeigen die volle Historie. Statusauswahl im Ticket nach Rolle: Administratoren wählen jeden Status, andere nur die erlaubten Folgestatus.
- Tickets: Erledigungsnotiz beim Abschluss (Art aus fester Liste plus Freitext, auch in der Bulk-Aktion und beim Zusammenführen). Jeder Abschluss wird als Lernbeispiel gespeichert, gelernte Playbooks erhalten den Schritt "Erledigung", Vorschläge zeigen "Bei ähnlichen Vorgängen wurde".
- Tickets: Anruf-Mails der KI-Telefonassistenz (Hallo Heidi) werden erkannt, Anrufer über Objekt plus Name, sonst Name oder Rufnummer zugeordnet, Objekt und Einheit am Ticket gesetzt. Eine unbekannte Rufnummer erzeugt automatisch den Vorschlag "Telefonnummer ergänzen" mit Antwortentwurf; "Freigeben und antworten" übernimmt die Nummer und legt die Antwort als Entwurf an. Einstellungen je Mandant unter Postfächer.
- Einstellungen: neue Seite "Wissen" mit gelernten Playbooks (Trefferzahl, letzte Nutzung, Deaktivieren) und Lernbeispielen mit Filter.
- Assistent: Eine Rolle aus der Chatanweisung ("Rolle bank") wird beim Tabellenimport auf alle Kontakte gesetzt, die Werte bank und verwalter sind neu. Ohne erkennbare Rolle fragt der Assistent nach. Rolle nachträglich für einen Importlauf setzbar (Importverlauf und POST /ai/import-runs/{id}/apply-role).
- Migrationen 0126 (Erledigungsnotiz, playbook.last_used_at, KI-Aufgabe ticket_resolution) und 0127 (Anrufassistenz, KI-Aufgabe call_summary).

## 1.23.1 (26.09.2026) Upload-Seite für Immoware24-Listen

- Importe: neue Seite "Immoware24 Listenimport" (/importe/immoware24-listen) mit Upload im Browser für Objektdaten, Kontaktlisten (Rolle je Datei, auch Dienstleister) und die Zuordnung von Eigentümern und Mietern zu Einheiten. Je Abschnitt Testlauf und Übernehmen mit Bestätigung, Bericht mit Zählern, nicht gefundenen und mehrdeutigen Namen sowie Konflikten. Neuer Endpunkt POST /imports/immoware24/lists/zuordnung.

## 1.23.0 (26.09.2026) Objektbezüge im Kontakt, CSV-Zuordnung, Gmail-Archivierung, Ticketfilter

- Kontakte: Abschnitt "Beziehungen zu Objekten und Einheiten" (Mieter, Eigentümer, Kategorie, Zeitraum, Status) unten auf der Kontaktseite, neuer Reiter "Tickets" mit allen personenbezogenen Tickets. Rollen Mieter und Eigentümer werden aus Verträgen, Eigentümerzuordnungen und Objektakte-Zuordnungen automatisch abgeleitet, Backfill über POST /contacts/roles/recompute.
- Import: neues CLI `python -m mhvp.imports.zuordnung` verknüpft Eigentümer und Mieter aus den Objektdaten mit den importierten Kontakten und legt Verträge mit vereinbartem Zahlbetrag an (idempotent, Testlauf als Standard, Bericht zu Leerstand, mehrdeutigen Namen und Konflikten). Kontaktimport speichert Briefanrede, Bundesland und Exportnamen; Rolle Dienstleister auch über die API. Handbuch `docs/handbuch/import-zuordnung.md`.
- Immoware24: "Alle unverknüpften Kontakte übernehmen" scheiterte mit internem Fehler (Telefon ohne Pflichtfeld Label), behoben.
- Gmail: Beim Abruf wird die Gmail-Kennung jeder Nachricht gespeichert, fehlende Kennungen der letzten 90 Tage werden beim nächsten Abruf nachgetragen. Damit greift "Erledigt archiviert Mail" bei done, closed und rejected.
- Tickets: Übersichten blenden done, closed und rejected standardmäßig aus (`include_closed=true` zeigt sie), Mailübersicht analog. Mandantenadministratoren dürfen jeden Status in jeden anderen setzen, ohne Zwischenschritte (Ereignis mit Kennzeichen admin_override). Suche "beinhaltet" jetzt auch über Betreff und Absender verknüpfter Mails sowie Kontakt-E-Mail.
- Server: Runbook um vertrauenswürdige Betreiber-IP (fail2ban ignoreip, sshd Match Address) und den zweiten Teil des Vorfalls vom 26.09.2026 ergänzt.

## 1.22.1 (26.09.2026) SSH-Härtung: Passwortanmeldung bleibt aktiv

- Server: `scripts/server/harden-ssh.sh` lässt die Passwortanmeldung standardmäßig aktiv und schaltet sie nur mit `--nur-schluessel` ab. Drop-in heißt jetzt `00-mhvp-ssh.conf` und hat Vorrang vor fremden Drop-ins.
- Runbook Server-Recovery: Vorfall 26.09.2026 (Drop-in `90-hardening.conf` sperrte Passwort-Login nach cloud-init-Reset) dokumentiert.

## 1.22.0 (26.09.2026) Master-Prompt-Umsetzung Welle 6: Ticket-Mails mit TNR#, Regel-Engine Stufe 2, Portal (Eigentümer, Beirat, Formulare, Schwarzes Brett, PWA), WEG (Darlehen, Versicherung, Überleitung, Protokoll, Einsicht), Telefonie, Abgleichbericht

- Tickets und Mail: Mailverlauf im Ticket als Thread mit Anhängen (Vorschau Bild und PDF, Download, Als Beleg erfassen), Antwortformular im Ticket (An, Kopie, Betreff, Text, Anhänge) mit Vier-Augen-Freigabe wie bisher; jede Antwort trägt die Ticketnummer im Betreff (TNR#412), eingehende Mails mit TNR# werden dem Ticket nur zugeordnet, wenn der Absender am Ticket beteiligt ist, sonst als Vorschlag angezeigt; Antwort auf ein erledigtes Ticket öffnet es wieder und benachrichtigt den Bearbeiter; Postfachzugriff wird auch bei Einzelmails geprüft (Regel M19-06, Migration 0119)
- Behobene Befunde aus der Prüfung Tickets und Mail (docs/reviews/2026-09-26-review-tickets-mail.md): Gmail-Abruf verlor Mails bei mehr als 50 neuen Nachrichten oder bei Einzelfehlern (jetzt seitenweise mit Nachlauf), Rechnungsweiterleitung ohne Anhänge, SLA-Uhr für Tickets aus Mail und Portal, Ticketliste mit Seitensteuerung, Indizes und eindeutige Mail-Deduplizierung (Migration 0120)
- Automatisierung: Regel-Engine Stufe 2 mit Aktionen Webhook (signiert), E-Mail-Entwurf aus Vorlage, Brief-Entwurf, KI-Aufgabe; Zeitplan als Auslöser (täglich, wöchentlich, monatlich, genau ein Lauf je Termin); strukturiertes Regelformular mit Vorschau statt JSON (Migration 0110)
- Portal: Eigentümerseiten Beschlüsse, Ansprechpartner und Hausgeldkonto (nur gebuchte Werte, ohne Rechtsfolge); Portalrolle Beirat mit Prüfungsraum (Prüfauftrag, Belege, Vermerke, Rückfragen, keine Freigabe, Migration 0109); Schwarzes Brett je Objekt im CRM pflegbar und im Portal sichtbar; Lesebestätigungen am Dokument im CRM als Indiz mit Test D34; Fotos an Schadensmeldungen als Dokumentverknüpfung mit Metadatenbereinigung; Dienstleister-Terminvorschläge mit Bestätigung durch den Bewohner und Fotos der Ausführung (Migration 0111); konfigurierbare Formulare je Mandant mit Einreichung als Ticket (Migration 0115); QR-Code zur Einladung im CRM; Portal als PWA installierbar mit Offline-Startseite
- WEG: Darlehen, Versicherungsfälle und größere Maßnahmen mit Positionen aus gebuchten Buchungen (Migration 0116); Überleitungsrechnung Gesamtgeldfluss im Abrechnungspaket mit erklärten Differenzen, unerklärte Differenz sperrt die interne Freigabe (Regeln W04, W10); Protokollentwurf der Versammlung als PDF im Mandanten-CI; Einsichtsanfragen außerhalb des Portals mit Verlauf und Bereitstellungspaket mit Prüfsummen (Migration 0117); neue Berechtigungsressource hoa
- Vermietung: Energieausweisdaten am Objekt und Angebotsmiete an der Anzeige, Vollständigkeitsprüfung von OpenImmo-Export und Exposé darauf gestützt (Migration 0112)
- Kommunikation und Betrieb: Telefonie-Webhook anbieterneutral mit Signatur, Zuordnung über Rufnummer, Anrufliste am Kontakt und Rückrufvorschlag (Migration 0118); täglicher Abgleichbericht Parallelbetrieb je Objekt aus Immoware24-Rohzeilen mit Differenzliste und CSV; Backup-Prüfjob 02:00 mit Kennzahl; ausgehende Webhooks contact.updated und invoice.issued; Namensmaskierung im Belegeingang auch ohne Anrede
- API: Versionsregel als ADR 0009 mit Deprecation-Headern, Drift-Prüfung meldet Entfernung von Pfaden ohne Deprecation; Handbuchkapitel Objekte, Verträge, Dokumente, Buchhaltung, WEG und Abrechnung
- Technik: Seed-Skript registriert alle Modelle (Abbruch bei membership.contact_id behoben), Migrationskette 0108 bis 0120 linear, Downgrades 0110 und 0112 unter erzwungener RLS lauffähig, eindeutige Schemanamen im OpenAPI-Dokument, Testnutzer je Modul eindeutig
- Aus der parallelen Sitzung: Kontakte: neue oder geänderte Bankverbindungen (IBAN) brauchen die Freigabe einer zweiten Person (contacts:approve), der Ersteller darf nicht selbst freigeben; nicht freigegebene Konten werden in Lastschrift, Zahlung, SEPA-Mandat und Rechnungsabgleich nicht verwendet. Bestandskonten gelten mit Migration 0121 als freigegeben
- Aus der parallelen Sitzung: Verträge: Dienstleisterverträge mit Laufzeit, Kündigungsfrist und automatischer Verlängerung; Kündigungstermin als Orientierung in der Fristenliste mit 14 Tagen Vorfrist (Migration 0122)
- Aus der parallelen Sitzung: WEG: Beschlussfrist virtueller Versammlungen mit Quellenangabe, in der Fristenliste mit 7 Tagen Vorfrist (Migration 0123)
- Aus der parallelen Sitzung: Bankabgleich: Tilgungsbestimmung aus dem Verwendungszweck (Rechnungs- und Sollstellungsnummern, Monate, Quartale) setzt den passenden offenen Posten nach vorn, jede Zuordnung trägt eine Begründung
- Aus der parallelen Sitzung: Mahnwesen: Zahlungserinnerung (Stufe 1) immer ohne Gebühr und Zinsen, Validierung in den Einstellungen und Schutz im Mahnlauf; Standard-Zahlungsfristen 14, 10 und 7 Tage je Stufe mit Hinweis im Formular
- Aus der parallelen Sitzung: KI-Kontierung (propose_posting): Ausgabeschema, Prompt mit Datenminimierung und Sperre, aktiv nur mit Mandantenschalter und freigegebenem Anbieter mit AVV; Ergebnis nur als Vorschlag, nichts wird gebucht (Migration 0124)
- Aus der parallelen Sitzung: WEG: Mehrheitsregeln je Beschlussgegenstand mit Fundstelle und Freigabe durch zweite Person, Prüfung "erreicht / nicht erreicht / nicht prüfbar" am Beschluss ohne Statusänderung (Migration 0125)
- Oberfläche: Die obere Menüleiste des CRM ist jetzt deckend; der fixierte Tabellenkopf (Name, Art, Rolle) der Kontaktliste schien beim Scrollen durch die halbtransparente Leiste hindurch
- Offen (Betreiberentscheidungen in docs/OPEN_QUESTIONS.md): Direktversand einfacher Ticketantworten ohne Vier-Augen-Freigabe (M20-03), Wiederholungsplan für Regel-Webhooks (M9-08), Verteilung von Zins und Tilgung in der Jahresabrechnung (M24-03), Fristen und Umfang der Einsicht (M25-05), Telefonieanbieter (M23-06), QR-Bibliothek für Einladungs-PDF (M21-08)

## 1.21.0 (26.09.2026) Master-Prompt-Umsetzung Welle 5: Abnahmefälle Anhang D, Lastschrift, XRechnung, E-Rechnung, Eigentümerabrechnung, Prüfexport, Regel-Engine, Tagesjobs, Portal und Importassistent

- Abnahme Anhang D: 43 von 58 Fällen technisch bestanden (Protokoll docs/acceptance/PROTOKOLL-2026-09-26.md), darunter Konkurrenz und Wiederholung des Sollstellungslaufs (D48), historische Stichtage (D49), Berechtigungen aller 38 Massenendpunkte (D50), Zahlungsfreigabe und Bankrückmeldung (D35 bis D38), Aufbewahrungssperre und Import-Rücknahme (D43, D46), Prompt-Injection ohne Wirkung (D57), WEG-Fälle (D18 bis D20, D54), Beirat (D32, D33, D53), Portalzugriff über alle Pfade (D29 bis D31), Betriebskosten (D21 bis D23, D28), Restore mit Löschjournal (D47); fachliche Bestätigung bleibt offen (V16)
- Behobene Produktfehler aus den Abnahmen: Idempotenzschlüssel blockierte den Neulauf nach Storno des Sollstellungslaufs; Verwalterhonorar belastete SEV-Eigentümer mit allen Einheiten des Objekts; SEV-Abrechnung enthielt Einheiten fremder Eigentümer; KI-Kontext hatte keinen Dokumentfilter je Portalnutzer; Ablehnungsereignis der Löschsperre ging im Rollback verloren; Vier-Augen-Prinzip prüfte nur die Benutzerkennung; Bankabstimmung meldete fremde Konten nicht als unbekannt
- Buchhaltung: SEPA-Lastschriftdatei pain.008 mit Mandatsprüfung, Sequenztyp und Vorabinformation als Entwurf (Datei hinter G2); XRechnung UBL 2.1 für Verwalterhonorare, mit KoSIT-Validator geprüft; E-Rechnung lesen (XRechnung, ZUGFeRD) im Belegeingang mit Widerspruchsanzeige; Eigentümerabrechnung Miete und SEV als Entwurf (Regel A06); Prüfexport nach Abschnitt 7.7 als ZIP mit Prüfsummen; DATEV-Kontenzuordnung je Mandant mit Sperre bei fehlender Zuordnung; Steuerberaterzugang je Rechtsträger; Rechtsträger der verwaltenden Gesellschaft per Einrichtungsschritt; MT940-Import; Kennzahlen Abdeckungsgrad und Fehlerquote des Bankabgleichs
- Mahnwesen und Abrechnung: Textbausteine je Mahnstufe mit Forderungsaufstellung, Mahnbescheid-Vorbereitung als PDF mit Hinweis auf anwaltliche Prüfung, Anschreiben Guthaben und Nachzahlung je Mieter aus dem Snapshot (Regel A07), KI-Plausibilität des Abrechnungsentwurfs (check_statement, 24 Evaluationsfälle)
- Automatisierung und Jobs: Regel-Engine Stufe 1 (Auslöser, Bedingungen, Aktionen Ticket, Benachrichtigung, Feld setzen, Testlauf, Protokoll), Tagesübersicht 07:00 und Fristenliste 20:00 mit Vorfrist, Dokumenteingang 06:30 mit Zuordnungsvorschlägen, protokollierte Spiegellöschung, Erinnerung vor Ablauf der finAPI-Zustimmung, Paperless-Webhook mit Signaturprüfung, Idempotency-Key für alle schreibenden Endpunkte, Ratenbegrenzung mit X-RateLimit-Headern
- Übergabe und Portal: Versionsverknüpfung beim U-Protokoll-Import, Lesebestätigung als Indiz beim Dokumentabruf (Datenmodell), Schwarzes Brett (Datenmodell)
- Importassistent: Immoware24-Listen (Objektdaten, Kontakte) über die Oberfläche mit Testlauf und Übernahme; Schnellpfad für Eigentümer- und Mieterlisten mit deterministischer Zeilenumsetzung; Evaluationsdatensätze für alle KI-Aufgaben mit mindestens 20 Fällen
- KI-Chat: Freitext-Kontakte aus eingefügtem Text, Verbindungstest je Modellstufe, Ausgabegrenze je Stufe; Tickets: Erkennungskorpus für Stammdatenänderungen (100 Prozent Trefferquote im Korpus), Antwortentwürfe je Änderungsart; objektakte: Synchronisationsstand, Benutzerabbildung, KI-Kostenauswertung, Listenablage als Dokument, Eigentümer- und Mieterlisten; Anzeigen: Bilder je Anzeige für den OpenImmo-Export
- Sicherheit: Review der 1.19.0-Endpunkte (docs/reviews/2026-09-26-sicherheitsreview-1.19.0.md), acht Befunde behoben (Dump-Pfad auf Exportverzeichnis begrenzt, Größenlimits, Postfachprüfung bei Ticketantworten, LIKE-Escaping, CSV-Formelschutz); englische Übersetzungen vollständig mit Prüfskript im Lint
- Technik: Migration 0108 (Fremdschlüssel admin_fee_invoice.tenant_id mit ON DELETE RESTRICT), Modelle und Migrationen ohne Abweichung im Autogenerate-Vergleich, Ratenbegrenzung in der Testkonfiguration abgeschaltet und nur im eigenen Test aktiv, Celery-Testisolation (D50)
- Offen: Regel-Engine Stufe 2, Portal Eigentümer (Beschlüsse, Ansprechpartner, Hausgeldkonto), Portalrolle Beirat, Fotoanhang an Portaltickets, CRM-Anzeige der Lesebestätigungen und Pflege des Schwarzen Bretts; Betreiberentscheidungen in docs/OPEN_QUESTIONS.md (unter anderem M10-05, M12-03, M16-14, M7-08, M15-01, M18-01)

## 1.20.1 (26.09.2026) Pflege: Plan-Dokumente, Formatierung, Typprüfung

- Plan-Dokumente M30-sla, M31 und M32: veraltete Abschnitte "Nicht umgesetzt" auf den tatsächlichen Stand gebracht
- Drei ältere Migrationen formatiert, Typfehler in Testdateien behoben, mypy über das ganze Backend ohne Befund

## 1.20.0 (26.09.2026) Übergabeprotokoll, Portal, Belegeingang, Betrieb

- Übergabeprotokoll: Fotos werden beim Hochladen von EXIF- und GPS-Daten befreit und auf höchstens 2000 px Kantenlänge verkleinert (Einstellung handover_image_max_edge); nicht lesbare Bilder werden abgelehnt
- Übergabeprotokoll: Einladungscode für Gehilfen als E-Mail-Entwurf (Vier-Augen-Freigabe, kein Versand) oder als PDF-Anschreiben auf dem Briefbogen; jede Zustellung erzeugt einen neuen Code, aktivierte Zugänge sind gesperrt
- Übergabeprotokoll: Termin anlegen mit Vorbelegung von Titel, Objektadresse als Ort und Beteiligten mit E-Mail als Teilnehmer, danach Link in den Kalender
- Portal: Mitarbeiter mit Portalzugang sehen Übergabeprotokolle ihrer Objekte (GET /portal/handovers), Rollenwechsel in eine ausgenommene Rolle entzieht den Mitarbeiterzugang sofort, Rückwechsel stellt ihn wieder her
- Belegeingang: Mandantenschalter für den automatischen Eingang (Einstellungen, DMS), standardmäßig aus; bei Aktivierung wird je neuem PDF-Anhang mit Rechnungsmerkmal genau eine KI-Extraktion als Vorschlag gestartet, nichts wird gebucht (Migration 0086)
- Tickets: Integrationstest für die Zusammenführung in ein Zielticket; dabei behoben: Zuweiser und Sammelstatus umgingen die Sperre zusammengeführter Tickets, sehr lange Ziffernfolgen in der Suche führten zu einem Datenbankfehler
- Betrieb: Runbook docs/runbooks/server-recovery-und-haertung.md (Zugang wiederherstellen, Ursache prüfen, SSH nur mit Schlüssel, cloud-init stilllegen, Backup) und Skript scripts/server/harden-ssh.sh

## 1.19.0 (26.09.2026) Tickets: Antwortvorlagen, lernende Stammdatenänderung, Links von der Startseite; Belegeingang; Bankkontenauswahl; Mahnwesen je Objekt mit PDF-Entwurf; OpenImmo-Prüfung; objektakte Stufen 4 und 5; Objekt- und Kontaktimport aus Immoware24-Listen; KI-Chat-Fehlerbehandlung

- Tickets: offene Tickets auf der Startseite mit Link ins Ticket; lange Betreffs und Texte laufen nicht mehr über die Seitenbreite hinaus (Ticket #404); Antwortvorlagen mit Platzhaltern (Anrede, Name, Objekt, Einheit, Ticketnummer) und Standardanhängen unter Einstellungen, im Ticket Vorschau, Bearbeiten und Senden zur Vier-Augen-Freigabe, Anhänge werden beim Versand beigefügt
- Tickets lernen: Mails mit Namens- oder Adressänderung (zum Beispiel Kampmeier zu Müller) erzeugen den Vorschlag Stammdatenänderung mit Akzeptieren, Korrigieren, Ablehnen und einem Antwortentwurf; jede Entscheidung fließt als Beispiel in künftige Vorschläge ein; IBAN wird nie vorgeschlagen (Regel M19-05)
- Belegeingang (M14): KI-Extraktion von Rechnungen aus Upload, Mail-Anhang oder Paperless als Entwurf mit Wert, Sicherheit und Quelle je Feld; Maskierung vor dem Anbieteraufruf; Bestätigung legt nur eine offene, ungebuchte Rechnung an; IBAN nur nach ausdrücklicher Bestätigung
- Bankkonten: Auswahlliste je Objekt und Rechtsträger mit Kontostand und letzten Umsätzen, Zuordnung von Konten zu Objekten, Standardkonto je Zweck (Hausgeld, Miete) und je Rechtsträger; WEG-Konten nie für fremde Objekte
- Mahnwesen: Mahnstufen, Mahngrenze, Gebühr und Zins je Objekt mit Vererbung vom Mandanten, Zahlungsfrist und Brieftext je Stufe; Mahnschreiben als PDF-Entwurf nach DIN 5008 mit Ablage als Dokument; Versand bleibt gesperrt (Gate G1)
- Anzeigen: OpenImmo-Export je Anzeige mit Vollständigkeitsprüfung (Adresse, Preis, Fläche, Energieausweis, Kontakt), Exportsperre mit bewusstem Übersteuern, ZIP mit Bildern
- objektakte Stufe 4: Listengenerierung (Anforderungsliste je Objekt, Dokumentenübersicht je Kategorie, CSV-Export), Berechtigungsschlüssel objektakte je Rolle, Benutzerabbildung als Bericht ohne automatische Anlage, Protokoll der KI-Aufrufe je Dokument
- objektakte Stufe 5: Differenzimport aus dem Dump (nur geänderte Zeilen seit dem letzten Lauf, Löschmarkierungen statt Löschung), täglicher Lauf je Mandant abschaltbar, manueller Lauf über die API
- Datenübernahme aus Immoware24-Listen: Befehl für Objekte und Einheiten aus der Objektliste (Verwaltungsart, Gebäude, Lage, Einheitenart abgeleitet, Eigentümer und Mieter nur als Herkunftsnotiz) und Befehl für Kontakte aus den Listen Eigentümer, Mieter, Bank und Sonstige (Rolle aus der Datei, Personen und Firmen getrennt, Telefon und E-Mail geprüft, keine Dubletten über die Immoware24-Nummer); Testlauf ohne Speichern ist Standard; Handbuchkapitel import-objektdaten und import-kontakte
- KI-Chat: Anbieterfehler werden mit Begründung angezeigt und protokolliert (bisher nur HTTP-Code), abgestürzte Läufe gelten nach dem Fehler als fehlgeschlagen statt endlos zu laufen, Zeitlimit von 10 Minuten im Chat, Chip Nur neue nennt die übersprungenen unvollständigen Zeilen; offene Frage M7-07: EU-Endpunkt wird derzeit nicht an den Anbieter übergeben
- Runbook Update einspielen korrigiert: das Produktions-Compose baut keine Images, die drei Images werden mit docker build unter dem Tag aus VERSION gebaut und der Tag in .env.prod gesetzt; exportierte Shell-Variablen überstimmen .env.prod

## 1.18.0 (25.09.2026) Große Sammelversion: Mitarbeiter und Portalrechte, Kalender, Ticketfilter, Open Banking, Mahnwesen, Rechnungseinstellungen, KI-Schnellimport, Immoware-Diagnose, WhatsApp, objektakte

- Mitarbeiter: beim Einladen entsteht automatisch der Kontakt mit Rolle Verwalter und ein sofort aktiver Portalzugang; Portalrechte je CRM-Rolle unter Einstellungen, Rollen einstellbar mit Nachziehen bestehender Zugänge; Löschen nur noch für Administratoren (Regel M2-07)
- Kalender: Termine aus Tickets, Übergabeprotokollen und der Kalenderseite mit Ort und Teilnehmern aus den Kontakten; Einladungen an Externe nur nach ausdrücklicher Bestätigung; Änderungen auf Google-Seite werden angezeigt und nie still überschrieben; Postfächer einmal neu verbinden
- Tickets: Suche über Nummer, Titel, Beschreibung, Kontakt und Adresse, Filter nach Bearbeiter, Objekt, Einheit, Kontaktrolle (Eigentümer, Mieter), Status, Priorität, Kategorie, Team und Zeitraum, Meine Tickets, Filter in der Adresszeile
- Banking: Open Banking über finAPI als Hauptweg für beliebig viele Banken (Bank per IBAN, BIC oder Name, Login im Bankfenster, Konten importieren und Buchungskreisen zuordnen, Umsätze manuell und rückwirkend abrufen, täglicher Abruf je Mandant abschaltbar), Rechnung-zu-Umsatz-Abgleich, Zahlung nur als Vorschlag (Gate G2), Ticket als Rechnung mit Ablage im Drive-Jahresordner, Beleg hinter der Buchung im Portal; finAPI-Einstellungsseite war bisher am Proxy vorbei nicht erreichbar
- Mahnwesen (V7): Vorschlagswerte für die Mahnleiter, Erinnerung kostenlos, Gebühr ab 1. Mahnung nur mit gepflegtem Betrag, Verzugszins nach gesetzlicher Regel nur mit gepflegtem Basiszinssatz, Gebühr als Sollstellung auf dem Debitorenkonto und Rechnungsentwurf der HVM an WEG bzw. Vermieter, Versandmarkierung, Vorbereitung Mahnbescheid (Prüfung durch Rechtsanwalt)
- Rechnungsstellung und Steuer je Mandant: Nummernkreis KUERZEL-JJJJ-000001 lückenlos, Umsatzsteuerstatus, XRechnung nur mit gepflegten Steuerdaten, DATEV-Buchungsstapel-Kopf nur mit Beraterdaten (Kontenzuordnung zu prüfen)
- KI-Import: Tabellen (CSV, Excel) werden deterministisch verarbeitet, die KI liefert nur die Spaltenzuordnung und bearbeitet Restzeilen; 864 Zeilen in Sekunden statt Minuten
- Immoware24: standardbasierte Erkennung von Adressbuch, Kalender und Dokumentwurzel, Diagnose mit Schritttabelle (zeigt, ob das DAV-Modul freigeschaltet ist), Sammelübernahme der Kontakte, Übernahme von Dokumenten einzeln und je Ordner
- WhatsApp als Eskalationskanal (Meta Cloud API, nur freigegebene Vorlagen, Einwilligung für Kontakte, SMS-Rückfall, Zustellstatus per Webhook, Testnachricht); Meta-Konto und Vorlagen sind vom Betreiber einzurichten
- objektakte-Übernahme Stufen 1 bis 3: Datenmodell, Stammdaten- und Dokumentimport aus dem Datenbank-Dump (Drive-Verweise ohne Kopie, OCR-Text per ZIP, IBAN nie im Klartext), Regelklassifikation, KI-Klassifikation mit Maskierung, Review-Center, Vollständigkeitsprüfung mit Nachforderungsentwurf, Menüpunkt Objektakte
- Übergabeprotokoll: Termin anlegen; Portal: Mitarbeiter sehen alle Protokolle; Portal-Anmeldung ohne zweiten Faktor führte in eine Schleife, behoben
- Sicherheit: Review der neuen Endpunkte (docs/reviews), Mitarbeiterzugang nie auf externem Portalkonto, Größenprüfung beim OCR-ZIP, eindeutige Quellkennungen, strengere Rückleitung
- Handbuch (elf Kapitel) und Runbooks (Update einspielen, Ressourcengrenzen); Playwright-Kernpfade mit neuen Rauchtests
- Dashboard: Tagesbalken der Ticketstatistik ordnen Buchungen nach Ortszeit Europa/Berlin zu (bisher nach UTC, dadurch nach 22 Uhr falscher Tag); Schemaabgleich der Tabellen Mahnwesen, Rechnungseinstellungen und Objektakte-Pflichtdokumente
- Tickets: Kontaktrollenfilter erkennt Eigentümer auch über die Objektzuordnung und prüft je Ticket (bisher leer oder zu weit); Dokumentspiegelung bricht bei fehlender Datei nicht mehr für alle Mandanten ab

## 1.17.5 (25.09.2026) SLA: Kanäle je Eskalationsstufe in der Oberfläche

- SLA-Einstellungen: je Regel Tabelle Stufe 1 bis 3 mit Intern, E-Mail und SMS, vorbelegt mit dem Standard (M35), Speichern über die bestehende Regeländerung; Hinweis, dass SMS nur mit aktivem Gateway und Mobilnummer greift
- Korrektur: Bearbeiten einer Regel im Formular setzt channels_by_level nicht mehr auf Standard zurück

## 1.17.4 (25.09.2026) Google-Verbindung ohne Abmeldung

- Google-Verbindung (DMS und Postfächer): die Rückleitung von Google landet auf einer same-site Zwischenseite, damit die Sitzung erhalten bleibt; bisher erschien nach dem Google-Login die Anmeldeseite des CRM, obwohl die Verbindung gespeichert war

## 1.17.3 (25.09.2026) Datenschutz: Ticket-Vorschau lädt nur den Kontaktnamen

- Neuer Endpunkt GET /contacts/{id}/name liefert nur Anzeigename statt des vollständigen Kontakts; die Vorschau beim Zusammenführen von Tickets nutzt ihn (Datenminimierung)

## 1.17.2 (25.09.2026) Worker: KI-Clients sauber schließen

- Die HTTP-Clients der KI-Anbieter (OpenAI, Anthropic) werden nach jedem Anbieterschritt geschlossen. Bisher meldete der Worker nach jedem KI-Lauf "Event loop is closed", weil die SDKs das Schließen erst beim Aufräumen nach Ende der Ereignisschleife anstießen

## 1.17.1 (25.09.2026) KI-Import: parallele Verarbeitung der Teile

- KI: Teile großer Listen werden parallel verarbeitet (vier gleichzeitige Anfragen an den Anbieter statt nacheinander); ein Import mit 11 Teilen braucht damit statt 5 bis 10 Minuten etwa ein Viertel der Zeit. Fortschrittsanzeige und Aufteilung zu großer Teile bleiben erhalten
## 1.17.0 (25.09.2026) Tickets zusammenführen in der Oberfläche

- Tickets: Aktion Zusammenführen im Ticketdetail mit Suche nach Zielticket (Nummer oder Titel), Vorschau beider Tickets und Bestätigung, danach Weiterleitung zum Zielticket
- Tickets: zusammengeführte Quelltickets zeigen einen Hinweis mit Link zum Zielticket und sind für Bearbeitung, Checkliste und Kommentare gesperrt (auch in der API)
- Tickets: Zielticket zeigt Enthält Ticket mit allen Quelltickets
- Ticketliste: zusammengeführte Tickets standardmäßig ausgeblendet, Filter Zusammengeführte anzeigen
- API: Zusammenführen in ein bestehendes Ticket über target_ticket_id; Verlauf des Ziels vermerkt die Herkunft je Quelle mit Anzahl verschobener Einträge
- API: SLA-Uhren der Quelltickets werden erledigt, Zuweiser der Quellen am Ziel ergänzt, Ticketliste mit Suche q, include_merged und merged_into, Ticketdetail mit message_count

## 1.16.0 (25.09.2026) SLA-Eskalation per E-Mail und SMS

- SLA-Eskalation: Kanäle je Stufe (Standard Stufe 1 intern, Stufe 2 intern und E-Mail, Stufe 3 intern, E-Mail und SMS), je Regel über channels_by_level anpassbar
- SLA-Eskalation: E-Mail wird als Systemmail ohne Freigabeprozess über das Standardpostfach versendet (Gmail oder SMTP), mit Objekt, Priorität, Fälligkeit und Link zum Ticket
- SLA-Eskalation: neuer Kanal SMS über ein anbieterneutrales HTTP-Gateway je Mandant, Einstellungen unter SLA, Reiter SMS-Gateway, mit Testnachricht
- Notfallalarme zeigen Zustellung und Fehlerhinweis (delivered_at, delivery_error); fehlt Postfach oder Gateway, wird der Alarm mit Hinweis protokolliert
- Mitglieder: Mobilnummer je Mitglied pflegbar, genutzt für SMS an die Bereitschaft
- Mailversand nach Vier-Augen-Freigabe nutzt denselben gemeinsamen Transport (communication/transport.py); SMTP-Fehler nennen nur noch die Fehlerart

## 1.15.1 (25.09.2026) KI-Chat: Fehlermeldungen mit Schritt und Status

- KI-Chat: Fehlermeldungen nennen jetzt den Schritt (Unterhaltung anlegen, Nachricht senden, Lauf abfragen) und den HTTP-Status, damit Abbrüche wie Datensatz nicht gefunden zuzuordnen sind

## 1.15.0 (25.09.2026) Belegeingang mit KI, OpenImmo, Übergabeprotokoll mit Gehilfen und U-Protokoll-Übernahme

- Belegeingang (M14): KI-Extraktion von Rechnungen als Vorschlag (Aussteller, Nummern, Daten, Beträge, Skonto, Objektbezug) mit serverseitigen Warnungen bei IBAN-Abweichung und Dublette; Übernahme nur als Entwurf mit Vier-Augen-Prüfung, IBAN wird maskiert angezeigt und muss aus dem Original bestätigt werden; Fremdwährung wird gesperrt
- Belegeingang: Erfassung aus Mail-Anhängen (Schaltfläche Als Rechnung erfassen) und aus Paperless per Dokumentnummer; automatische Erfassung bleibt zurückgestellt (M14-05)
- Anzeigen (M26): OpenImmo-Export je Anzeige und als Sammelexport mit vorheriger Vollständigkeitsprüfung, Adresse nur bei Freigabe, kein Portalupload
- Übergabeprotokoll: Objekt und Einheit auch manuell erfassbar (Adresse, Etage, Einheit, externe Objektnummer, Eigentümername), Umschalter Bestand oder manuell
- Übergabeprotokoll: Gehilfenzugang über den bestehenden Portalzugang (Art Gehilfe, Mieter, Eigentümer, 30 Tage gültig), Einladung als Entwurf im Postausgang, Abschluss mit Rückfrage, PDF und Durchschrift an alle Beteiligten als Zustellentwürfe, Verwaltung der Zugänge im CRM
- Übergabeprotokoll: Datenübernahme aus U-Protokoll (MariaDB-Dump mit Vorschau und Übernahme, Dateien per ZIP mit Prüfsummenabgleich), idempotent je Quelldatensatz
- Planung: objektakte wird vollständig ins CRM überführt (docs/plans/M35-objektakte-uebernahme.md, sechs Stufen, offene Entscheidungen M35-01 bis M35-07)

## 1.14.2 (25.09.2026) Mail-Archivierung bei jedem Ticketabschluss

- Tickets: jeder Abschlussstatus (erledigt, abgeschlossen, abgelehnt) archiviert die zugehörigen Mails im Postfach; bisher nur erledigt und abgeschlossen. Die Postfach-Einstellung zur Archivierung bleibt maßgeblich

## 1.14.1 (25.09.2026) Abschaltplan Immoware Hub

- Runbook `docs/runbooks/hub-abschaltung.md`: vierstufige Abschaltung des Immoware Hub mit Rückweg je Schritt, Voraussetzungen, Aufbewahrungsfristen und Hinweis zur Domain mail.mueller-holding.ag
- Zusatzdatei `infra/compose.hub-redirect.yaml`: dauerhafte Weiterleitung der alten Hub-Hostnamen immoware.muellerhv.de und mail.muellerhv.de auf das CRM über Traefik

## 1.14.0 (25.09.2026) KI-Wissensbasis und Mail-Vorbereitung

- KI-Wissensbasis je Mandant und Objekt unter Einstellungen, KI: Ablageregeln, Arbeitsweisen, Fakten und gelernte Korrekturen, filterbar je Objekt
- Mail-Vorbereitung: eingehende Mail wird dem Kontakt, der Einheit und dem Objekt zugeordnet, passende Objektdokumente (z. B. Teilungserklärung) werden gezielt aus Paperless und Google Drive nur im Ordner bzw. unter der Objektnummer des Objekts gesucht, ein Antwortentwurf wird als Vorschlag erzeugt; nichts wird versendet
- Mail: Panel Vorbereitung in der Mail-Ansicht mit Übernehmen (Entwurf) und Korrigieren; Korrekturen werden als gelernte Wissenseinträge gespeichert
- Regel M20-05: Dokumentsuche der KI ist strikt auf das jeweilige Objekt beschränkt, keine Kontoauflistung
## 1.13.0 (25.09.2026) Lernphase Immoware24

- Neue Lernphase (M33) für den Immoware24-Spiegel: WebDAV-, CardDAV- und CalDAV-Läufe erkunden lesend Ordnerstruktur und Feldnutzung der bereits gespiegelten Daten, Übernahme des Moduls Learning aus dem stillgelegten Immoware Hub
- Jeder Lauf vergleicht sich mit dem letzten erfolgreichen Lauf gleicher Art und liefert lesbare Änderungssätze (neue Ordner, neu oder nicht mehr genutzte Felder, geänderte Anzahl gespiegelter Datensätze)
- Neue Seite Immoware24 – Lernphase mit Artauswahl, Lauflisten und Detailansicht der Fakten; Endpunkte `/api/v1/immoware/learning/runs`, kein Schreibpfad Richtung Immoware24

## 1.12.0 (25.09.2026) Portal für Mieter, Eigentümer und Dienstleister

- Portal portal.mueller-holding.ag: Startseite je Rolle nach der Anmeldung; Mieter und Eigentümer sehen Dokumente mit Download, Meldungen mit Verlauf, Foto und Kommentar, Kontoauszug, Zählerstand und Datenänderung; Dienstleister sehen ihre Aufträge mit Ablehnen, Angebot, Termin, Ausführungsbericht und Rechnungseinreichung
- Portal: alle Angaben mit Geld- oder Vertragsbezug sind Vorschläge und werden von der Verwaltung geprüft, nichts wird automatisch übernommen
- Portal: Menü je Rolle, auf Handy und Tablet nutzbar; vertrauenswürdige Geräte gibt es im Portal bewusst nicht, der zweite Faktor bleibt bei jeder Anmeldung

## 1.11.1 (25.09.2026) Immoware24-Kalender werden automatisch erkannt

- Immoware24-Kalender: der Abgleich ermittelt die Kalender unter der eingetragenen Adresse selbst (PROPFIND auf die Kalender-Heimat des Benutzers) und fragt jeden Kalender einzeln ab; eine Heimatadresse wie .../calendars/users/<Login>/ führt nicht mehr zu REPORT 404
- Immoware24-DAV: abgeleitete Adressen für Kalender und Adressbuch nutzen den hinterlegten Login (.../users/<Login>/), wenn keine eigene Adresse eingetragen ist

## 1.11.0 (25.09.2026) Zwei-Faktor für Administratoren, Google-Kalender, Kontakttypen mit SEPA-Mandat, Banking über finAPI, Bearbeiterzuweisung

- Anmeldung: Zwei-Faktor-Pflicht nur noch für Administratoren, vertrauenswürdige Geräte 180 Tage ohne erneuten zweiten Faktor
- Kalender: Google-Kalender je Postfach, Vorgabe ist das Standardpostfach des Mandanten (info@), zusätzlich das dem Benutzer zugewiesene Postfach; Postfächer müssen dafür einmal neu verbunden werden
- Kontakte: Kontakttypen (Eigentümer, Mieter, Verwalter, Dienstleister, Bank, Sonstiges), SEPA-Freigabe je Bankverbindung mit Mandat als PDF oder Erteilung per Telefon, Brief oder E-Mail mit Datum
- Banking: Kontoanbindung über finAPI (Lesezugriff, WebForm) neben dem Dateiupload, Konten werden Objekten und Buchungskreisen zugeordnet; Zahlungsauslösung bleibt hinter Gate G2 gesperrt
- Tickets: automatische Bearbeiterzuweisung nach Postfach, Anrede oder Signatur, Kompetenzen je Benutzer (Katalog unter Einstellungen, Benutzer) und bisheriger Zuordnung; mehrere Bearbeiter je Ticket
- Tickets: Erledigen archiviert die zugehörige Gmail-Nachricht; Tickets werden am Kontakt, Objekt und an der Einheit angezeigt
- Mail: Weiterleitung von Firmenrechnungen (nicht Objektrechnungen) an die Buchhaltungsadresse mit Lernen aus Korrekturen, jede Weiterleitung nur nach Freigabe
- SLA: Schaltfläche Vorschlagswerte laden legt fehlende Regeln je Priorität und den Geschäftszeitenkalender als Vorschlag an (Produktschutz, keine Rechtsvorschrift)
- Oberfläche: Favicon und App-Symbol im CRM

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

## 1.2.1 (24.09.2026) Rückwirkend: Stand vom 24.09.2026 vor Einführung des Versionsverlaufs

- Mietrecht: Regelwerk und Kappungsgebiete NRW, Mieterhöhungsprüfung mit Begründungsmitteln
- Betrieb: Produktivstack auf dem Betreiberserver mit Traefik, Let's Encrypt, Backup-Timer, Wiederherstellungstest, Health-Check, Mehrkern-Einstellungen für API, Celery und PostgreSQL
- Oberfläche: CI der Müller Holding AG, dunkle Seitenleiste mit Icons, Seitenköpfe, Kennzahlen-Kacheln, Anmeldeseite, Dunkelmodus, Bedienung auf Handy und Tablet
- KI: OpenAI als zweiter Anbieter, Anbieterreihenfolge mit automatischem Wechsel, Wiederholung bei Ratenlimit, Chatblase auf jeder Seite mit geführten Importen, Assistent als Protokollseite aller Chats
- Verwaltung: Filter Mietverwaltung, WEG und SEV, Objektebereich, Benutzerverwaltung mit Rollen, Passwort zurücksetzen und Sperren, Benutzermenü, Einstellungen, Mandanten anlegen
- Makler: Anzeigen für Vermietung und Verkauf je Einheit, Felder aus dem FLOW-Datenvertrag, Import des FLOW-Datenbankexports mit Vorschau und Übernahme
- DMS: Bereich mit Absprung in die Objektübernahme je Objektnummer
- Postfach: Gmail-Abruf mit Ticket je Mail, Fehler je Nachricht isoliert

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
