/** Versionsverlauf der MH Verwaltungsplattform (CRM).
 *
 *  Schema: MAJOR.MINOR.PATCH
 *  - MAJOR (2.0, 3.0): grundlegender Umbau oder Bruch bestehender Abläufe
 *  - MINOR (1.1, 1.2): neue Funktion oder neues Modul
 *  - PATCH (1.2.1, 1.2.2): kleine Korrektur ohne neue Funktion
 *
 *  Der erste Eintrag ist die aktuelle Version. Jede Auslieferung erhält hier einen Eintrag
 *  und die gleiche Nummer in der Datei VERSION im Repository sowie in CHANGELOG.md.
 */
export type ChangelogEntry = {
  version: string;
  date: string; // TT.MM.JJJJ
  title: string;
  changes: string[];
};

export const CHANGELOG: ChangelogEntry[] = [
  {
    version: "1.30.0",
    date: "26.09.2026",
    title: "Upload im CRM mit Ablage über objektakte in Drive und Paperless",
    changes: [
      "Dokumente: hochgeladene Dokumente mit genau einem Objekt werden über objektakte in Drive (mit Eigentümer- und Mieterakten) und in Paperless abgelegt, ohne doppelte Spiegelung",
      "Dokumente: Ablagestand je Dokument abrufbar, fehlgeschlagene Uploads lassen sich erneut anstoßen",
      "DMS: Meldungen von objektakte verknüpfen das vorhandene CRM-Dokument statt ein zweites anzulegen",
      "DMS: neue Dokumentsuche im Paperless-Archiv mit Vorschau, Download und Upload direkt im CRM",
    ],
  },
  {
    version: "1.29.0",
    date: "26.09.2026",
    title: "DMS-Seite mit Daten der Objektübernahme, Paperless-Objektsuche und Gesellschaftsfilter",
    changes: [
      "DMS: Kachel je Objekt mit Übernahmestatus, Prüffällen, Vollständigkeit und fehlenden Dokumenten, Detailseite mit Dokumentliste, Sprung nach Google Drive und Nachholen der Verknüpfung",
      "DMS: neue Dokumente aus der Objektübernahme werden über einen gesicherten Webhook automatisch am Objekt abgelegt",
      "DMS: Eigentümer- und Mieterlisten aus der Objektübernahme als Importvorschlag mit Testlauf und Freigabe",
      "Dokumente: Paperless-Suche nach Objektnummer ohne Teiltreffer und Filter nach Gesellschaft, Gesellschaftsoptionen in den DMS-Einstellungen",
      "Dokumente: vertauschte Fehlertexte bei nicht erreichbarem oder nicht eingerichtetem Paperless korrigiert",
    ],
  },
  {
    version: "1.28.0",
    date: "26.09.2026",
    title:
      "Betreiberentscheidungen vom 26.09.2026 umgesetzt: Gmail-Push und Vollabruf, Ticketampel und Auswertung, Kaution, Bank finAPI, Messdienstleister Stufe 1, Betrieb",
    changes: [
      "Messdienstleister (neues Modul mhvp.metering, Stufe 1 Backend, Regel M40-01, Migration 0145): Anbieterkatalog ista, Techem, KALO, Brunata Minol, BRUNATA-METRONA und Sonstige mit ehrlicher Funktionsanzeige in vier Dimensionen (dokumentiert, Adapter, Kontofreigabe, Verbindungstest) und Recherchestand 26.09.2026 (Quellen Q1 bis Q11, vor Implementierung erneut prüfen); zentrale Verbindungen je Mandant mit verschlüsselten Geheimnissen (nur setzen, nie auslesen), Test und Produktion getrennt, Verbindungstest nur lesend; Objektzuordnung zu externen Abrechnungseinheiten mit Leistungsbereich, Gültigkeit, Prüfstatus, Gruppierung, Konfliktprüfung, Versionsprüfung (409) und Anbieterwechsel mit Historie; Einheitenzuordnung mit getrennten Empfängern und Belegungsstatus; manueller Abruf als persistenter Auftrag, Klärungsbereich, Verbrauchswerte und Abrechnungsergebnisse versioniert ohne Buchung; CSV-Vorlage, Vorschau, Übernahme und Export; Rechte metering_connections:manage, metering_assignments:update, metering_sync:run, metering_data:read, metering_users:submit, metering_billing:order; Mandantenschalter metering_module_enabled (Standard aus); Endpunkte unter /metering; keine Anbieteradapter (Stufe 2, OPEN_QUESTIONS M40-01 bis M40-03); Oberfläche folgt",
      "Tickets: Ampel je Ticketzeile nach Zeit ohne Reaktion unsererseits (gelb neu, orange ab 24 Stunden, rot ab 96 Stunden, grün erledigt), serverseitig berechnet (last_staff_activity_at, last_inbound_at, last_activity_at, attention), nur Handlungen von Mitarbeitern zählen, eingehende Mails und Portalkommentare setzen die Uhr nicht zurück; Standardsortierung Dringlichkeit (Erledigte zuletzt), Filterhaken Nach Eingang; Legende, Textmarke mit Dauer und farbiger Rand in Übersicht, Meine Tickets, Startseite und Reiter Tickets; Reiter Tickets blendet Erledigte standardmäßig aus (Umschalter Erledigte anzeigen); Regel M19-09, Handbuch Tickets",
      "Buchhaltung: Kostenkonten der Kontenrahmen-Vorlage als Entwurf nach der Betriebskostenverordnung vorbelegt (M10-02, Betreiberentscheidung 26.09.2026): Konten der Betriebskostenarten des Katalogs umlagefähig mit Abrechnungsart Betriebskosten und Schlüsselvorschlag (Wohnfläche, Verbrauch für Heizung, Warmwasser und Wasser), Heizungsreparaturen nicht umlagefähig, Rauchwarnmelder ohne Einordnung, Umsatzsteueroption bleibt offen; je Zeile Prüfkennzeichen Entwurf mit Vermerk \"Freigabe durch Steuerberatung offen\"; Seed füllt nur unbesetzte Felder und verändert eigene Einträge und bestehende Buchungskreise nicht; Zuordnungstabelle in Regel M10-02, Handbuch Buchhaltung",
      "Dokumente: Löschung gespiegelter Dokumente nach Betreiberentscheidung M6-03 vom 26.09.2026: Drive-Kopie wird gelöscht (endgültig, ersatzweise Papierkorb, im Journal vermerkt), Paperless-Dokument bleibt erhalten und erhält das Schlagwort \"gelöscht\" (wird angelegt, falls es fehlt), beide Schritte im Löschjournal mit Erfolg oder Fehler, Löschung \"offen\" bis beide Schritte gelungen sind, Wiederholung per Task, neue Endpunkte GET /documents/deletions und POST /documents/deletions/{id}/retry (Migration 0143), Sperre gespiegelter Dokumente entfällt, Restore-Wiederanwendung behandelt gespiegelte Dokumente gleich",
      "Bank: finAPI (M11-01, Betreiberentscheidung 26.09.2026: Aggregator finAPI zuerst, Datei-Import bleibt, EBICS später): Konten- und Umsatzabruf hinter der bestehenden Aggregator-Schnittstelle, OAuth2 Client-Token plus technischer finAPI-Benutzer und Benutzer-Token je Bankverbindung (verschlüsselt, kein Auto-Update durch den Anbieter), WebForm-Import ohne Bankzugangsdaten, inkrementeller Umsatzabruf je Konto mit Cursor und Überlappung, idempotenter Upsert nach Transaktions-ID, Beträge als NUMERIC, Standard-Basis-URL je Rechenzentrum (Sandbox oder Live, Einstellungen MHVP_FINAPI_BASE_URL_SANDBOX und _LIVE), Fehlercodes MHVP-BANK-0005 (Zugangsdaten abgelehnt) und MHVP-BANK-0006 (Ratenlimit, ohne automatische Wiederholung), Migration 0141; keine Zahlungsauslösung, G2 bleibt geschlossen; Doku docs/integrations/finapi.md",
      "KI: Einbettungen und Ähnlichkeitssuche (M7-03, Betreiberentscheidung 26.09.2026): OpenAI text-embedding-3-small über den vorhandenen Adapter (EU-Endpunkt bei Region eu), Speicherung in pgvector je Mandant mit RLS (Tabelle ai_embedding, Migration 0142), Indexlauf als Celery-Aufgabe in Stapeln mit Budgetzählung (Aufgabe embed) und maskierter Eingabe, answer_question und Wissensbasis der Mail-Vorbereitung suchen per Ähnlichkeit mit Schlüsselwort-Rückfall, neue Endpunkte POST /ai/embeddings/reindex und GET /ai/embeddings/status",
      "Betrieb: Lesezugang der Überwachung auf die Betriebskennzahlen (M9-04a, Betreiberentscheidung 26.09.2026): neues Recht platform:metrics:read, das nur ein von einem Plattformadministrator erzeugter API-Schlüssel trägt (POST, GET, DELETE /platform/ops/metrics-keys, Geheimnis einmalig, Ereignisse api_key.created und api_key.revoked, Ratenlimit wie jeder Schlüssel), GET /platform/ops/metrics (JSON und Prometheus) nimmt Plattformadministrator-Sitzung oder diesen Schlüssel an, jeder andere Endpunkt weist den Schlüssel ab, keine Migration; Runbook monitoring.md 3.1 mit Anleitung für Uptime Kuma",
      "Benachrichtigungen: jede Benachrichtigung trägt ein Ziel (target_type, target_id) und einen vom Server abgeleiteten Link (href) zum Betreff; ein Klick im CRM öffnet Ticket, Auftrag, Mail, Dokument, Vertrag, Objektakte, Fristenliste oder den Kalender mit geöffnetem Termin (/kalender?termin=...) und markiert nur diesen Eintrag als gelesen; Portal: neue Endpunkte GET /portal/notifications und POST /portal/notifications/read mit Portalrouten (Meldung, Auftrag, Übergabe) und Liste auf der Übersicht",
      "Dokumente: Standard-Aufbewahrungsprofile je Mandant als Entwurf (Entwurf, Prüfung Steuerberatung offen; Betreiberentscheidung M6-04 vom 26.09.2026: Belege, Journale, Abrechnungen 10 Jahre; Geschäftsbriefe, Vorgänge, Mails 6 Jahre; Verträge 10 Jahre nach Ende; Portal- und Bewerberdaten 6 Monate nach Zweckende; WEG-Protokolle und Beschlüsse dauerhaft), Seed idempotent ohne Überschreiben eigener Änderungen, Löschung bleibt bis zur Freigabe gesperrt, Freigabe nur mit Recht Mandanteneinstellungen im Vier-Augen-Prinzip und protokolliert, Felder retention_months, permanent, review_note, status (Migration 0139), noch keine Einstellungsseite (nur API)",
      "Buchhaltung: Ausgleich offener Posten nach gesetzlicher Reihenfolge als Vorschlag (M10-03, Betreiberentscheidung 26.09.2026): Vorschlag deterministisch (fällig vor nicht fällig, geringere Sicherheit, größere Last, ältere zuerst, Kosten vor Zinsen vor Hauptforderung), Bestimmung des Zahlers geht vor (D39), Überzahlung bleibt Guthaben; Bestätigung erzeugt Buchungsentwurf mit Ausgleichsplan und protokolliert die Regelversion, sofortiges Buchen nur mit G1; Karte auf der Buchungskreisseite, Vermerk Rechtsprüfung vor G1 offen",
      "Anmeldung (Betreiberentscheidung M2-01 vom 26.09.2026): Mindestlänge des Passworts 6 Zeichen (Kontosperre nach 10 Fehlversuchen für 15 Minuten unverändert; Hinweis auf die längere BSI-Empfehlung nur in der Dokumentation), zweiter Faktor für CRM und Portal nicht mehr Pflicht (auch nicht für Administratoren), Einrichten und Ausschalten unter Einstellungen, Meine Daten (CRM) und Sicherheit (Portal, neue Seite) mit neuen Endpunkten POST /auth/totp/setup, /confirm, /disable und totp_enabled in GET /auth/me, Anmeldeschritt mfa_setup_required und POST /auth/mfa/setup entfallen; gemerkte Geräte 90 statt 180 Tage (Dieses Gerät 90 Tage merken), jetzt auch im Portal, Liste und Abmelden in den Einstellungen; Regel M2-01, ADR 0006 zweiter Nachtrag, offene Frage M2-09 (Prüfung gegen kompromittierte Passwörter nicht vorhanden)",
      "Tickets und Mail: Gmail-Push per Pub/Sub (Nachrichten erscheinen sofort, Abruf alle fünf Minuten als Sicherheitsnetz, Watch-Erneuerung täglich), Vollabruf des gesamten Posteingangs beim Verknüpfen und manuell je Postfach (Button und Serverbefehl python -m mhvp.communication.backfill), Mail auf erledigt archiviert sofort in Gmail und schließt das Ticket automatisch mit Auskunft erteilt, wenn keine Mail und kein Arbeitsauftrag mehr offen ist (Migration 0144)",
      "Tickets: Erledigungsarten um Zahlung geklärt, Termin vereinbart, Mangel behoben, Vertrag geändert erweitert und je Mandant pflegbar (Migration 0136, Einstellungen Mandant); Freigeben und antworten der Telefonassistenz legt keinen Entwurf ohne Empfänger an; Ticketsuche findet auch Mailinhalt und interne Beschreibung",
      "Auswertung Tickets: neue Seite mit Durchsatz je Tag, Woche, Monat, Quartal und Jahr, erledigte Tickets je Stunde und Minute, Erstreaktion und Bearbeitungsdauer (Median, 90. Perzentil), Rückstand, Tabellen je Mitarbeiter und je Postfach (persönlich oder Standardpostfach), CSV-Export",
      "Kontakte: Mehrpersonen-Parteien aus dem Immoware24-Adressbuch als eine Partei mit Mitgliedern, Bevollmächtigte mit Zustellregel (beide, nur Bevollmächtigter, nur Eigentümer) für Serienbriefe, Serienversand und WEG-Einladungen (Migration 0140)",
      "Verträge: Kautionsabrechnung als Entwurf mit Zinsart je Abrechnung (individuell je Jahr, Referenzzinssatz je Jahr aus den Einstellungen, ohne Zins), Freigabe hinter G3 (Migration 0138, Regel M5-02)",
      "Buchhaltung: Erlöskonten der Mietverwaltung 060300 bis 060800 als Vorschlag mit Prüfkennzeichen Entwurf (Migration 0137, M10-01)",
      "KI: Lernbeispiele nur bei aktivem Mandantenschalter, Löschung bei Kontaktlöschung (Migration 0134, ADR 0010); zweiter Anbieter mit Wechsel bei Fehler oder Budget, Endpunktregion wird an den Anbieter durchgereicht (M7-02, M7-07)",
      "Plattform: Superadmin-Kennzeichen und Schalter gate_superadmin_bypass für Gate-Freigaben ohne zweite Person, Standard aus (ADR 0011, Migration 0135); Anmeldung ohne Pflicht zum zweiten Faktor, gemerkte Geräte 90 Tage auch im Portal",
      "Automatisierung: Regel-Webhooks mit Wiederholung nach Stufenplan, Zustellprotokoll und erneuter Zustellung (A82, Migration 0133)",
      "Portal: HEIC-Fotos vom iPhone werden angenommen und in JPEG gewandelt (A72); QR-Code im Einladungs-PDF (A86); Kontaktereignisse auch aus Staging- und Objektakte-Import (A87)",
      "Betrieb: IONOS S3 Object Storage als Produktionsspeicher (make check-s3), Images aus der GitHub Container Registry, Uptime Kuma im Produktions-Compose, Off-site-Backup nach Hetzner Object Storage mit age-Verschlüsselung und Aufbewahrung 14/8/12 (scripts/backup-offsite.sh)",
      "Oberfläche: Immoware24 nur noch unter Einstellungen erreichbar, nicht mehr im Hauptmenü",
    ],
  },
  {
    version: "1.27.1",
    date: "26.09.2026",
    title: "Erledigungsnotiz für Administratoren optional",
    changes: ["Tickets: Administratoren schließen ohne Erledigungsnotiz, für alle anderen bleibt sie Pflicht"],
  },
  {
    version: "1.27.0",
    date: "26.09.2026",
    title: "Zuordnung im Bericht, Objekteigentümer, Freigabe der Importverträge",
    changes: [
      "Import: offene Zuordnungen direkt im Bericht per Kontaktauswahl abschließen, Vermieter dabei festlegen",
      "Objekte: Eigentümer festlegen auf der Objektseite, Reiter Ohne Eigentümer",
      "Verträge: Freigabe der Importverträge vor der Sollstellung, Seite Verträge, Freigabe mit Sammelfreigabe und Ablehnen",
    ],
  },
  {
    version: "1.26.1",
    date: "26.09.2026",
    title: "Mail: Aktionen oben, Mehrfachauswahl, Erledigt archiviert",
    changes: [
      "Mail: Antworten, Ticket anlegen und Erledigt auch oberhalb der Nachricht",
      "Mail: Mehrfachauswahl mit Strg, Shift und Alle auswählen, Sammelaktion Als erledigt markieren",
      "Mail: Erledigt archiviert die Nachricht in Gmail, einzeln und als Sammelaktion",
    ],
  },
  {
    version: "1.26.0",
    date: "26.09.2026",
    title: "Portalzugang am Kontakt, IBAN-Ablehnungsgrund, Importereignisse, Dokumentliste, Telefonassistenz-Korrekturen",
    changes: [
      "Kontakte: Abschnitt Portalzugang auf der Kontaktakte mit Status (kein Zugang, eingeladen, aktiv, gesperrt), Einladung mit QR-Code und neuem Leseendpunkt GET /portal-admin/accounts?contact_id (A86, CRM-Teil)",
      "Kontakte: Ablehnungsgrund der IBAN-Freigabe wird gespeichert und angezeigt (rejected_reason, rejected_by, rejected_at, Migration 0132), Kontaktliste zeigt den Hinweis IBAN wartet auf Freigabe ohne N+1",
      "Importe: Listen- und Zuordnungsimporte lösen dieselben Ereignisse contact.created und contact.updated aus wie die manuelle Pflege (Regelwerk und Webhooks greifen, A87 teilweise)",
      "Dienstleisterverträge: Anzeigename des Dienstleisters in Liste und Detail statt Kennung",
      "Dokumente: neue Dokumentliste im CRM mit Volltextsuche und Entwurfsfilter (is_draft), Upload bei fehlendem oder nicht erreichbarem Dokumentenspeicher antwortet mit 503 MHVP-DOC-0007 statt 500, keine halben Dokumentzeilen",
      "Tickets: Freigeben und antworten der Telefonassistenz legt keinen Entwurf ohne Empfänger mehr an (422 mit Hinweis), Zusammenführen protokolliert je Quellticket Statusereignis mit Erledigungsnotiz und Lernbeispiel",
      "Abnahme: Playwright gegen den Stack 12 CRM und 11 Portal grün, zwei Specs an die neue Anzeige angepasst (Bruttobetrag formatiert, Anhangsliste der Meldung), spezifische Spec-Läufe über MHVP_E2E_PW_ARGS",
      "Dokumentation: Handbuch für Erledigungsnotiz, Telefonassistenz, ausgeblendete erledigte Vorgänge, Objektbezüge und Wissen; Regeln M19-07 bis M19-09, ADR 0010 Lernbeispiele (Betreiberentscheidung), offene Fragen M19-03 und M19-04, Lückenliste A90 bis A99",
      "Offen (Betreiber): Datenschutzregel für Lernbeispiele (M7-04, ADR 0010), AVV und Anbieterfreigabe Telefonassistenz (M19-03), Erledigungsartenliste (M19-04), QR-Code im Einladungs-PDF (M21-08)",
    ],
  },
  {
    version: "1.25.1",
    date: "26.09.2026",
    title: "Adressen nachtragen, Einheitenliste und Einheitenseite",
    changes: [
      "Importe: Adressen der Objekte aus den Namen ableiten oder per Adressliste nachtragen",
      "Objekte: Einheiten natürlich sortiert, Nummer und Bezeichnung verlinkt, Spalten Eigentümer, Mieter und Fläche",
      "Einheitenseite: alle Stammdaten, Umlageschlüssel, Eigentümer und Mieter mit Namen, beendete Verträge",
    ],
  },
  {
    version: "1.25.0",
    date: "26.09.2026",
    title:
      "Zusammenführung mit 1.24.0 und Fix- und Abschlusswelle: Vier-Augen nach Betreiberentscheidung, Review-Befunde Tickets und Mail, Sicherheit, Performance, Bedienbarkeit, Vertragsformular, Import-Robustheit, Anhang D 54 von 58",
    changes: [
      "Tickets und Mail: Betreiberentscheidung M20-03 umgesetzt: Vier-Augen-Freigabe nur für Mitarbeiter mit Kennzeichen Azubi oder neuer Mitarbeiter (Einstellungen, Benutzer, optional befristet), alle anderen senden Ticketantworten direkt; Verfasser und Freigeber mit Zeitpunkt als Ticketereignisse und im Mailverlauf sichtbar; Notbremse alle Antworten mit Freigabe (Standard aus); Freigabeberechtigte werden benachrichtigt (Migration 0129, Regel M20-06)",
      "Prüfung Tickets und Mail: 31 von 34 Befunden behoben, darunter Doppelversand bei Verbindungsfehler ausgeschlossen (zweiphasiger Versand mit Nachweis), Rechnungsweiterleitung nach Commit, Postfach löschen als Deaktivierung ohne Sichtbarkeitsverlust, Mailliste mit Vorschau statt Volltext, Thread-Zuordnung über References und Gmail-Thread, abgewiesene Anhänge sichtbar, Kommentare mit Autor, interne Beschreibung, Zuweisungsereignis, Archivierung nach Commit, Arbeitsaufträge mit Terminvorschlägen im Ticket (Migration 0126)",
      "Sicherheit: Review 1.22 ohne hohe Befunde, 5 mittlere und 12 niedrige behoben (Ratenbegrenzung bei gefälschtem API-Key, Größenlimit Paperless-Webhook, Rechtsträgerbereich in WEG-Finanzen, Prüfung, Beirat und Mehrheitsregeln, Aushang-Sichtbarkeit je Zielgruppe, Webhook-Ziel mit gebundener Adresse gegen DNS-Umlenkung, Geheimnisse nur serverseitig, Paketgröße Einsicht, Telefonie-Antwort ohne Trefferstatus)",
      "Performance: Listen Verträge, Einheiten, Parteien, Journal, Rechnungen, Lastschriftläufe, Dokumenteingang und Startseite ohne N+1 (bis zu 57 auf 11 Abfragen), 18 neue Indizes (Migration 0127), Paginierung Verträge, Mandate, Journal, Rechnungen, Berechtigungskontext je Prozess 30 Sekunden zwischengespeichert mit sofortiger Wirkung von Sperre und Rollenentzug im selben Prozess",
      "Bedienbarkeit CRM und Portal: 63 Befunde behoben, darunter zwei Seitenabstürze (WEG Prüfauftrag, Objektseite), Kennzahlenkarte Bankabgleich lud im Betrieb nie, Lastschriftläufe haben jetzt eine Seite mit Vier-Augen-Freigabe hinter G2, Rohwerte statt Beträge und Daten in Exposé, Belegeingang und Automatisierung, Fehler- und Ladezustände, mobile Kartenansicht Hausgeldkonto, einklappbares Portalmenü, deutsche Fehler- und 404-Seiten im Portal",
      "Neue Funktionen: Vertragsformular im CRM für Miet-, Eigentums- und SEV-Verträge mit Zahlungsplan und Kaution; Webhook-Abonnements unter Einstellungen mit Zustellprotokoll; Prüfauftrag Beirat im CRM anlegen mit Positionsfilter und Beiratsstellungnahme (CRM und Portal); Formular-Einreichungen je Vorlage; Terminvorschläge der Dienstleister im CRM; Ratenplan Darlehen als Orientierung, Beschlussbezug am Versicherungsfall, Überleitung im Übernahmejahr (Migration 0128); Regel-Engine mit Bedingungen auf Objekt, Einheit, Kontakt und Vertrag, automatisch erzeugte Briefe als Entwurf gekennzeichnet; OpenImmo-Schemaprüfung mit hinterlegter XSD; Namensmaskierung im Belegeingang für Einzelunternehmer",
      "Import Immoware24: Listenimport liest Windows-1252, BOM, Semikolon, Komma, Tab, eingebettete Trennzeichen, wiederholte Kopfzeilen und Spalten in beliebiger Reihenfolge; Pflichtspalten mit klarer Meldung; Duplikate gemeldet statt still übernommen; Nummernzuordnung mit führenden Nullen; Telefon und E-Mail in allen Schreibweisen; IBAN nur als maskierter Hinweis; Checkliste im Handbuch",
      "Abnahme und Tests: Anhang D jetzt 54 von 58 technisch bestanden (offen nur D24 bis D27 wegen fehlender Betreiberregeln); Playwright gegen den Stack 12 CRM und 11 Portal grün inklusive Fototest; 66 neue Abdeckungstests; Ergebnisbuchung nach Eigentümerwechsel repariert, Versionsvergleich der WEG-Abrechnung als Endpunkt und Anzeige; Seed-Skript und Test-Datenbankaufbau stabil",
      "Dokumentation: Entscheidungsvorlage für den Betreiber (docs/reviews/2026-09-26-entscheidungsvorlage-betreiber.md), Handbuchkapitel für alle Funktionen seit 1.20, Lückenliste konsolidiert (A72 bis A89), Plan-Dokumente mit Stand 26.09.2026, Reviews Performance, Sicherheit 1.22, Bedienbarkeit CRM und Portal",
      "Offen (Betreiber): OpenImmo-XSD beschaffen (M26-02), Zins und Tilgung in der Jahresabrechnung (M24-03), Heizkosten und Verbrauchsinformation (D24 bis D27), Freigabestufen G1 bis G5 mit Steuerberatung, Rechtsberatung und Bank, Serverhärtung (M9-05)",
      "Zusammenführung: Stände 1.23.0 bis 1.24.0 der parallelen Sitzung übernommen (Migrationen Erledigungsnotiz und Hallo Heidi laufen jetzt als 0130 und 0131 hinter 0126 bis 0129)",
    ],
  },
  {
    version: "1.24.0",
    date: "26.09.2026",
    title: "Ticketfilter, Erledigungsnotiz, Hallo Heidi, Wissensdatenbank, Assistent-Rolle",
    changes: [
      "Tickets und Mail: erledigte Vorgänge ausgeblendet, Umschalter Erledigte anzeigen, Statusauswahl nach Rolle",
      "Tickets: Erledigungsnotiz beim Abschluss, jeder Abschluss wird als Lernbeispiel gespeichert",
      "Tickets: Anrufe der KI-Telefonassistenz werden erkannt, neue Rufnummern als Stammdatenvorschlag mit Antwortentwurf",
      "Einstellungen: Seite Wissen mit gelernten Playbooks und Lernbeispielen",
      "Assistent: Rolle aus der Chatanweisung beim Tabellenimport, nachträglich je Importlauf setzbar",
    ],
  },
  {
    version: "1.23.1",
    date: "26.09.2026",
    title: "Upload-Seite für Immoware24-Listen",
    changes: [
      "Importe: Objektdaten, Kontaktlisten und Zuordnung von Eigentümern und Mietern im Browser hochladen, mit Testlauf, Übernehmen und Bericht",
    ],
  },
  {
    version: "1.23.0",
    date: "26.09.2026",
    title: "Objektbezüge im Kontakt, CSV-Zuordnung, Gmail-Archivierung, Ticketfilter",
    changes: [
      "Kontakte: Beziehungen zu Objekten und Einheiten auf der Kontaktseite, Reiter Tickets, Rollen Mieter und Eigentümer werden automatisch abgeleitet",
      "Import: Zuordnung von Eigentümern und Mietern aus den Objektdaten zu Einheiten mit Verträgen und vereinbartem Zahlbetrag",
      "Immoware24: Fehler bei Alle unverknüpften Kontakte übernehmen behoben",
      "Gmail: Kennung der Nachrichten wird gespeichert, Archivierung bei Abschluss eines Tickets greift",
      "Tickets: erledigte Vorgänge in Übersichten ausgeblendet, Administratoren wechseln Status ohne Zwischenschritte, Suche über Betreff und Absender der Mails",
    ],
  },
  {
    version: "1.22.1",
    date: "26.09.2026",
    title: "SSH-Härtung: Passwortanmeldung bleibt aktiv",
    changes: [
      "Server: Härtungsskript lässt die Passwortanmeldung standardmäßig aktiv, Abschaltung nur auf ausdrücklichen Wunsch",
      "Runbook Server-Recovery um den Vorfall vom 26.09.2026 ergänzt",
    ],
  },
  {
    version: "1.22.0",
    date: "26.09.2026",
    title:
      "Master-Prompt-Umsetzung Welle 6: Ticket-Mails mit TNR#, Regel-Engine Stufe 2, Portal (Eigentümer, Beirat, Formulare, Schwarzes Brett, PWA), WEG (Darlehen, Versicherung, Überleitung, Protokoll, Einsicht), Telefonie, Abgleichbericht",
    changes: [
      "Tickets und Mail: Mailverlauf im Ticket als Thread mit Anhängen (Vorschau Bild und PDF, Download, Als Beleg erfassen), Antwortformular im Ticket (An, Kopie, Betreff, Text, Anhänge) mit Vier-Augen-Freigabe wie bisher; jede Antwort trägt die Ticketnummer im Betreff (TNR#412), eingehende Mails mit TNR# werden dem Ticket nur zugeordnet, wenn der Absender am Ticket beteiligt ist, sonst als Vorschlag angezeigt; Antwort auf ein erledigtes Ticket öffnet es wieder und benachrichtigt den Bearbeiter; Postfachzugriff wird auch bei Einzelmails geprüft (Regel M19-06, Migration 0119)",
      "Behobene Befunde aus der Prüfung Tickets und Mail (docs/reviews/2026-09-26-review-tickets-mail.md): Gmail-Abruf verlor Mails bei mehr als 50 neuen Nachrichten oder bei Einzelfehlern (jetzt seitenweise mit Nachlauf), Rechnungsweiterleitung ohne Anhänge, SLA-Uhr für Tickets aus Mail und Portal, Ticketliste mit Seitensteuerung, Indizes und eindeutige Mail-Deduplizierung (Migration 0120)",
      "Automatisierung: Regel-Engine Stufe 2 mit Aktionen Webhook (signiert), E-Mail-Entwurf aus Vorlage, Brief-Entwurf, KI-Aufgabe; Zeitplan als Auslöser (täglich, wöchentlich, monatlich, genau ein Lauf je Termin); strukturiertes Regelformular mit Vorschau statt JSON (Migration 0110)",
      "Portal: Eigentümerseiten Beschlüsse, Ansprechpartner und Hausgeldkonto (nur gebuchte Werte, ohne Rechtsfolge); Portalrolle Beirat mit Prüfungsraum (Prüfauftrag, Belege, Vermerke, Rückfragen, keine Freigabe, Migration 0109); Schwarzes Brett je Objekt im CRM pflegbar und im Portal sichtbar; Lesebestätigungen am Dokument im CRM als Indiz mit Test D34; Fotos an Schadensmeldungen als Dokumentverknüpfung mit Metadatenbereinigung; Dienstleister-Terminvorschläge mit Bestätigung durch den Bewohner und Fotos der Ausführung (Migration 0111); konfigurierbare Formulare je Mandant mit Einreichung als Ticket (Migration 0115); QR-Code zur Einladung im CRM; Portal als PWA installierbar mit Offline-Startseite",
      "WEG: Darlehen, Versicherungsfälle und größere Maßnahmen mit Positionen aus gebuchten Buchungen (Migration 0116); Überleitungsrechnung Gesamtgeldfluss im Abrechnungspaket mit erklärten Differenzen, unerklärte Differenz sperrt die interne Freigabe (Regeln W04, W10); Protokollentwurf der Versammlung als PDF im Mandanten-CI; Einsichtsanfragen außerhalb des Portals mit Verlauf und Bereitstellungspaket mit Prüfsummen (Migration 0117); neue Berechtigungsressource hoa",
      "Vermietung: Energieausweisdaten am Objekt und Angebotsmiete an der Anzeige, Vollständigkeitsprüfung von OpenImmo-Export und Exposé darauf gestützt (Migration 0112)",
      "Kommunikation und Betrieb: Telefonie-Webhook anbieterneutral mit Signatur, Zuordnung über Rufnummer, Anrufliste am Kontakt und Rückrufvorschlag (Migration 0118); täglicher Abgleichbericht Parallelbetrieb je Objekt aus Immoware24-Rohzeilen mit Differenzliste und CSV; Backup-Prüfjob 02:00 mit Kennzahl; ausgehende Webhooks contact.updated und invoice.issued; Namensmaskierung im Belegeingang auch ohne Anrede",
      "API: Versionsregel als ADR 0009 mit Deprecation-Headern, Drift-Prüfung meldet Entfernung von Pfaden ohne Deprecation; Handbuchkapitel Objekte, Verträge, Dokumente, Buchhaltung, WEG und Abrechnung",
      "Technik: Seed-Skript registriert alle Modelle (Abbruch bei membership.contact_id behoben), Migrationskette 0108 bis 0120 linear, Downgrades 0110 und 0112 unter erzwungener RLS lauffähig, eindeutige Schemanamen im OpenAPI-Dokument, Testnutzer je Modul eindeutig",
      "Aus der parallelen Sitzung: Kontakte: neue oder geänderte IBAN braucht die Freigabe einer zweiten Person, nicht freigegebene Konten werden in Lastschrift, Zahlung und Mandat nicht verwendet",
      "Aus der parallelen Sitzung: Verträge: Dienstleisterverträge mit Kündigungsfrist, Kündigungstermin in der Fristenliste",
      "Aus der parallelen Sitzung: WEG: Beschlussfrist virtueller Versammlungen in der Fristenliste, Mehrheitsregeln je Beschlussgegenstand mit Prüfung am Beschluss",
      "Aus der parallelen Sitzung: Bankabgleich: Tilgungsbestimmung aus dem Verwendungszweck mit Begründung je Zuordnung",
      "Aus der parallelen Sitzung: Mahnwesen: Zahlungserinnerung immer ohne Gebühr und Zinsen, Standard-Zahlungsfristen je Stufe",
      "Aus der parallelen Sitzung: KI-Kontierung als Vorschlag vorbereitet, gesperrt bis zur Freigabe des Anbieters",
      "Oberfläche: Die obere Menüleiste des CRM ist jetzt deckend; der fixierte Tabellenkopf (Name, Art, Rolle) der Kontaktliste schien beim Scrollen durch die halbtransparente Leiste hindurch",
      "Offen (Betreiberentscheidungen in docs/OPEN_QUESTIONS.md): Direktversand einfacher Ticketantworten ohne Vier-Augen-Freigabe (M20-03), Wiederholungsplan für Regel-Webhooks (M9-08), Verteilung von Zins und Tilgung in der Jahresabrechnung (M24-03), Fristen und Umfang der Einsicht (M25-05), Telefonieanbieter (M23-06), QR-Bibliothek für Einladungs-PDF (M21-08)",
    ],
  },
  {
    version: "1.21.0",
    date: "26.09.2026",
    title:
      "Master-Prompt-Umsetzung Welle 5: Abnahmefälle Anhang D, Lastschrift, XRechnung, E-Rechnung, Eigentümerabrechnung, Prüfexport, Regel-Engine, Tagesjobs, Portal und Importassistent",
    changes: [
      "Abnahme Anhang D: 43 von 58 Fällen technisch bestanden (Protokoll docs/acceptance/PROTOKOLL-2026-09-26.md), darunter Konkurrenz und Wiederholung des Sollstellungslaufs (D48), historische Stichtage (D49), Berechtigungen aller 38 Massenendpunkte (D50), Zahlungsfreigabe und Bankrückmeldung (D35 bis D38), Aufbewahrungssperre und Import-Rücknahme (D43, D46), Prompt-Injection ohne Wirkung (D57), WEG-Fälle (D18 bis D20, D54), Beirat (D32, D33, D53), Portalzugriff über alle Pfade (D29 bis D31), Betriebskosten (D21 bis D23, D28), Restore mit Löschjournal (D47); fachliche Bestätigung bleibt offen (V16)",
      "Behobene Produktfehler aus den Abnahmen: Idempotenzschlüssel blockierte den Neulauf nach Storno des Sollstellungslaufs; Verwalterhonorar belastete SEV-Eigentümer mit allen Einheiten des Objekts; SEV-Abrechnung enthielt Einheiten fremder Eigentümer; KI-Kontext hatte keinen Dokumentfilter je Portalnutzer; Ablehnungsereignis der Löschsperre ging im Rollback verloren; Vier-Augen-Prinzip prüfte nur die Benutzerkennung; Bankabstimmung meldete fremde Konten nicht als unbekannt",
      "Buchhaltung: SEPA-Lastschriftdatei pain.008 mit Mandatsprüfung, Sequenztyp und Vorabinformation als Entwurf (Datei hinter G2); XRechnung UBL 2.1 für Verwalterhonorare, mit KoSIT-Validator geprüft; E-Rechnung lesen (XRechnung, ZUGFeRD) im Belegeingang mit Widerspruchsanzeige; Eigentümerabrechnung Miete und SEV als Entwurf (Regel A06); Prüfexport nach Abschnitt 7.7 als ZIP mit Prüfsummen; DATEV-Kontenzuordnung je Mandant mit Sperre bei fehlender Zuordnung; Steuerberaterzugang je Rechtsträger; Rechtsträger der verwaltenden Gesellschaft per Einrichtungsschritt; MT940-Import; Kennzahlen Abdeckungsgrad und Fehlerquote des Bankabgleichs",
      "Mahnwesen und Abrechnung: Textbausteine je Mahnstufe mit Forderungsaufstellung, Mahnbescheid-Vorbereitung als PDF mit Hinweis auf anwaltliche Prüfung, Anschreiben Guthaben und Nachzahlung je Mieter aus dem Snapshot (Regel A07), KI-Plausibilität des Abrechnungsentwurfs (check_statement, 24 Evaluationsfälle)",
      "Automatisierung und Jobs: Regel-Engine Stufe 1 (Auslöser, Bedingungen, Aktionen Ticket, Benachrichtigung, Feld setzen, Testlauf, Protokoll), Tagesübersicht 07:00 und Fristenliste 20:00 mit Vorfrist, Dokumenteingang 06:30 mit Zuordnungsvorschlägen, protokollierte Spiegellöschung, Erinnerung vor Ablauf der finAPI-Zustimmung, Paperless-Webhook mit Signaturprüfung, Idempotency-Key für alle schreibenden Endpunkte, Ratenbegrenzung mit X-RateLimit-Headern",
      "Übergabe und Portal: Versionsverknüpfung beim U-Protokoll-Import, Lesebestätigung als Indiz beim Dokumentabruf (Datenmodell), Schwarzes Brett (Datenmodell)",
      "Importassistent: Immoware24-Listen (Objektdaten, Kontakte) über die Oberfläche mit Testlauf und Übernahme; Schnellpfad für Eigentümer- und Mieterlisten mit deterministischer Zeilenumsetzung; Evaluationsdatensätze für alle KI-Aufgaben mit mindestens 20 Fällen",
      "KI-Chat: Freitext-Kontakte aus eingefügtem Text, Verbindungstest je Modellstufe, Ausgabegrenze je Stufe; Tickets: Erkennungskorpus für Stammdatenänderungen (100 Prozent Trefferquote im Korpus), Antwortentwürfe je Änderungsart; objektakte: Synchronisationsstand, Benutzerabbildung, KI-Kostenauswertung, Listenablage als Dokument, Eigentümer- und Mieterlisten; Anzeigen: Bilder je Anzeige für den OpenImmo-Export",
      "Sicherheit: Review der 1.19.0-Endpunkte (docs/reviews/2026-09-26-sicherheitsreview-1.19.0.md), acht Befunde behoben (Dump-Pfad auf Exportverzeichnis begrenzt, Größenlimits, Postfachprüfung bei Ticketantworten, LIKE-Escaping, CSV-Formelschutz); englische Übersetzungen vollständig mit Prüfskript im Lint",
      "Technik: Migration 0108 (Fremdschlüssel admin_fee_invoice.tenant_id mit ON DELETE RESTRICT), Modelle und Migrationen ohne Abweichung im Autogenerate-Vergleich, Ratenbegrenzung in der Testkonfiguration abgeschaltet und nur im eigenen Test aktiv, Celery-Testisolation (D50)",
      "Offen: Regel-Engine Stufe 2, Portal Eigentümer (Beschlüsse, Ansprechpartner, Hausgeldkonto), Portalrolle Beirat, Fotoanhang an Portaltickets, CRM-Anzeige der Lesebestätigungen und Pflege des Schwarzen Bretts; Betreiberentscheidungen in docs/OPEN_QUESTIONS.md (unter anderem M10-05, M12-03, M16-14, M7-08, M15-01, M18-01)",
    ],
  },
  {
    version: "1.20.1",
    date: "26.09.2026",
    title: "Pflege: Plan-Dokumente, Formatierung, Typprüfung",
    changes: [
      "Plan-Dokumente auf den tatsächlichen Stand gebracht, Migrationen formatiert, Typfehler in Testdateien behoben",
    ],
  },
  {
    version: "1.20.0",
    date: "26.09.2026",
    title: "Übergabeprotokoll, Portal, Belegeingang, Betrieb",
    changes: [
      "Übergabeprotokoll: Fotos verlieren beim Hochladen EXIF- und GPS-Daten und werden auf höchstens 2000 px verkleinert",
      "Übergabeprotokoll: Einladungscode für Gehilfen als E-Mail-Entwurf oder PDF-Anschreiben, jede Zustellung erzeugt einen neuen Code",
      "Übergabeprotokoll: Termin anlegen mit Vorbelegung von Titel, Ort und Beteiligten, danach Link in den Kalender",
      "Portal: Mitarbeiter sehen Übergabeprotokolle ihrer Objekte, Rollenwechsel in eine ausgenommene Rolle entzieht den Zugang sofort",
      "Belegeingang: Schalter für den automatischen Eingang aus neuen Mail-Anhängen (Einstellungen, DMS), standardmäßig aus, Ergebnis nur als Vorschlag",
      "Tickets: Integrationstest für die Zusammenführung, Sperre zusammengeführter Tickets greift jetzt auch bei Zuweisern und Sammelstatus",
      "Betrieb: Runbook und Skript für Serverzugang, SSH-Härtung und Stilllegung von cloud-init",
    ],
  },
  {
    version: "1.19.0",
    date: "26.09.2026",
    title:
      "Tickets: Antwortvorlagen, lernende Stammdatenänderung, Links von der Startseite; Belegeingang; Bankkontenauswahl; Mahnwesen je Objekt mit PDF-Entwurf; OpenImmo-Prüfung; objektakte Stufen 4 und 5; Objekt- und Kontaktimport aus Immoware24-Listen; KI-Chat-Fehlerbehandlung",
    changes: [
      "Tickets: offene Tickets auf der Startseite mit Link ins Ticket; lange Betreffs und Texte laufen nicht mehr über die Seitenbreite hinaus (Ticket #404); Antwortvorlagen mit Platzhaltern (Anrede, Name, Objekt, Einheit, Ticketnummer) und Standardanhängen unter Einstellungen, im Ticket Vorschau, Bearbeiten und Senden zur Vier-Augen-Freigabe, Anhänge werden beim Versand beigefügt",
      "Tickets lernen: Mails mit Namens- oder Adressänderung (zum Beispiel Kampmeier zu Müller) erzeugen den Vorschlag Stammdatenänderung mit Akzeptieren, Korrigieren, Ablehnen und einem Antwortentwurf; jede Entscheidung fließt als Beispiel in künftige Vorschläge ein; IBAN wird nie vorgeschlagen (Regel M19-05)",
      "Belegeingang (M14): KI-Extraktion von Rechnungen aus Upload, Mail-Anhang oder Paperless als Entwurf mit Wert, Sicherheit und Quelle je Feld; Maskierung vor dem Anbieteraufruf; Bestätigung legt nur eine offene, ungebuchte Rechnung an; IBAN nur nach ausdrücklicher Bestätigung",
      "Bankkonten: Auswahlliste je Objekt und Rechtsträger mit Kontostand und letzten Umsätzen, Zuordnung von Konten zu Objekten, Standardkonto je Zweck (Hausgeld, Miete) und je Rechtsträger; WEG-Konten nie für fremde Objekte",
      "Mahnwesen: Mahnstufen, Mahngrenze, Gebühr und Zins je Objekt mit Vererbung vom Mandanten, Zahlungsfrist und Brieftext je Stufe; Mahnschreiben als PDF-Entwurf nach DIN 5008 mit Ablage als Dokument; Versand bleibt gesperrt (Gate G1)",
      "Anzeigen: OpenImmo-Export je Anzeige mit Vollständigkeitsprüfung (Adresse, Preis, Fläche, Energieausweis, Kontakt), Exportsperre mit bewusstem Übersteuern, ZIP mit Bildern",
      "objektakte Stufe 4: Listengenerierung (Anforderungsliste je Objekt, Dokumentenübersicht je Kategorie, CSV-Export), Berechtigungsschlüssel objektakte je Rolle, Benutzerabbildung als Bericht ohne automatische Anlage, Protokoll der KI-Aufrufe je Dokument",
      "objektakte Stufe 5: Differenzimport aus dem Dump (nur geänderte Zeilen seit dem letzten Lauf, Löschmarkierungen statt Löschung), täglicher Lauf je Mandant abschaltbar, manueller Lauf über die API",
      "Datenübernahme aus Immoware24-Listen: Befehl für Objekte und Einheiten aus der Objektliste (Verwaltungsart, Gebäude, Lage, Einheitenart abgeleitet, Eigentümer und Mieter nur als Herkunftsnotiz) und Befehl für Kontakte aus den Listen Eigentümer, Mieter, Bank und Sonstige (Rolle aus der Datei, Personen und Firmen getrennt, Telefon und E-Mail geprüft, keine Dubletten über die Immoware24-Nummer); Testlauf ohne Speichern ist Standard; Handbuchkapitel import-objektdaten und import-kontakte",
      "KI-Chat: Anbieterfehler werden mit Begründung angezeigt und protokolliert (bisher nur HTTP-Code), abgestürzte Läufe gelten nach dem Fehler als fehlgeschlagen statt endlos zu laufen, Zeitlimit von 10 Minuten im Chat, Chip Nur neue nennt die übersprungenen unvollständigen Zeilen; offene Frage M7-07: EU-Endpunkt wird derzeit nicht an den Anbieter übergeben",
      "Runbook Update einspielen korrigiert: das Produktions-Compose baut keine Images, die drei Images werden mit docker build unter dem Tag aus VERSION gebaut und der Tag in .env.prod gesetzt; exportierte Shell-Variablen überstimmen .env.prod",
    ],
  },
  {
    version: "1.18.0",
    date: "25.09.2026",
    title:
      "Große Sammelversion: Mitarbeiter und Portalrechte, Kalender, Ticketfilter, Open Banking, Mahnwesen, Rechnungseinstellungen, KI-Schnellimport, Immoware-Diagnose, WhatsApp, objektakte",
    changes: [
      "Mitarbeiter: beim Einladen entsteht automatisch der Kontakt mit Rolle Verwalter und ein sofort aktiver Portalzugang; Portalrechte je CRM-Rolle unter Einstellungen, Rollen einstellbar mit Nachziehen bestehender Zugänge; Löschen nur noch für Administratoren (Regel M2-07)",
      "Kalender: Termine aus Tickets, Übergabeprotokollen und der Kalenderseite mit Ort und Teilnehmern aus den Kontakten; Einladungen an Externe nur nach ausdrücklicher Bestätigung; Änderungen auf Google-Seite werden angezeigt und nie still überschrieben; Postfächer einmal neu verbinden",
      "Tickets: Suche über Nummer, Titel, Beschreibung, Kontakt und Adresse, Filter nach Bearbeiter, Objekt, Einheit, Kontaktrolle (Eigentümer, Mieter), Status, Priorität, Kategorie, Team und Zeitraum, Meine Tickets, Filter in der Adresszeile",
      "Banking: Open Banking über finAPI als Hauptweg für beliebig viele Banken (Bank per IBAN, BIC oder Name, Login im Bankfenster, Konten importieren und Buchungskreisen zuordnen, Umsätze manuell und rückwirkend abrufen, täglicher Abruf je Mandant abschaltbar), Rechnung-zu-Umsatz-Abgleich, Zahlung nur als Vorschlag (Gate G2), Ticket als Rechnung mit Ablage im Drive-Jahresordner, Beleg hinter der Buchung im Portal; finAPI-Einstellungsseite war bisher am Proxy vorbei nicht erreichbar",
      "Mahnwesen (V7): Vorschlagswerte für die Mahnleiter, Erinnerung kostenlos, Gebühr ab 1. Mahnung nur mit gepflegtem Betrag, Verzugszins nach gesetzlicher Regel nur mit gepflegtem Basiszinssatz, Gebühr als Sollstellung auf dem Debitorenkonto und Rechnungsentwurf der HVM an WEG bzw. Vermieter, Versandmarkierung, Vorbereitung Mahnbescheid (Prüfung durch Rechtsanwalt)",
      "Rechnungsstellung und Steuer je Mandant: Nummernkreis KUERZEL-JJJJ-000001 lückenlos, Umsatzsteuerstatus, XRechnung nur mit gepflegten Steuerdaten, DATEV-Buchungsstapel-Kopf nur mit Beraterdaten (Kontenzuordnung zu prüfen)",
      "KI-Import: Tabellen (CSV, Excel) werden deterministisch verarbeitet, die KI liefert nur die Spaltenzuordnung und bearbeitet Restzeilen; 864 Zeilen in Sekunden statt Minuten",
      "Immoware24: standardbasierte Erkennung von Adressbuch, Kalender und Dokumentwurzel, Diagnose mit Schritttabelle (zeigt, ob das DAV-Modul freigeschaltet ist), Sammelübernahme der Kontakte, Übernahme von Dokumenten einzeln und je Ordner",
      "WhatsApp als Eskalationskanal (Meta Cloud API, nur freigegebene Vorlagen, Einwilligung für Kontakte, SMS-Rückfall, Zustellstatus per Webhook, Testnachricht); Meta-Konto und Vorlagen sind vom Betreiber einzurichten",
      "objektakte-Übernahme Stufen 1 bis 3: Datenmodell, Stammdaten- und Dokumentimport aus dem Datenbank-Dump (Drive-Verweise ohne Kopie, OCR-Text per ZIP, IBAN nie im Klartext), Regelklassifikation, KI-Klassifikation mit Maskierung, Review-Center, Vollständigkeitsprüfung mit Nachforderungsentwurf, Menüpunkt Objektakte",
      "Übergabeprotokoll: Termin anlegen; Portal: Mitarbeiter sehen alle Protokolle; Portal-Anmeldung ohne zweiten Faktor führte in eine Schleife, behoben",
      "Sicherheit: Review der neuen Endpunkte (docs/reviews), Mitarbeiterzugang nie auf externem Portalkonto, Größenprüfung beim OCR-ZIP, eindeutige Quellkennungen, strengere Rückleitung",
      "Handbuch (elf Kapitel) und Runbooks (Update einspielen, Ressourcengrenzen); Playwright-Kernpfade mit neuen Rauchtests",
      "Dashboard: Tagesbalken der Ticketstatistik ordnen Buchungen nach Ortszeit Europa/Berlin zu (bisher nach UTC, dadurch nach 22 Uhr falscher Tag); Schemaabgleich der Tabellen Mahnwesen, Rechnungseinstellungen und Objektakte-Pflichtdokumente",
      "Tickets: Kontaktrollenfilter erkennt Eigentümer auch über die Objektzuordnung und prüft je Ticket (bisher leer oder zu weit); Dokumentspiegelung bricht bei fehlender Datei nicht mehr für alle Mandanten ab",
    ],
  },
  {
    version: "1.17.5",
    date: "25.09.2026",
    title: "SLA: Kanäle je Eskalationsstufe in der Oberfläche",
    changes: [
      "SLA-Einstellungen: je Regel Tabelle Stufe 1 bis 3 mit Intern, E-Mail und SMS, vorbelegt mit dem Standard; Hinweis, dass SMS nur mit aktivem Gateway und Mobilnummer greift",
      "Korrektur: Bearbeiten einer Regel im Formular setzt die Kanalwahl nicht mehr auf Standard zurück",
    ],
  },
  {
    version: "1.17.4",
    date: "25.09.2026",
    title: "Google-Verbindung ohne Abmeldung",
    changes: [
      "Google-Verbindung (DMS und Postfächer): die Rückleitung von Google landet auf einer same-site Zwischenseite, damit die Sitzung erhalten bleibt; bisher erschien nach dem Google-Login die Anmeldeseite des CRM, obwohl die Verbindung gespeichert war",
    ],
  },
  {
    version: "1.17.3",
    date: "25.09.2026",
    title: "Datenschutz: Ticket-Vorschau lädt nur den Kontaktnamen",
    changes: [
      "Neuer Endpunkt für den Anzeigenamen eines Kontakts; die Vorschau beim Zusammenführen von Tickets lädt damit nicht mehr den vollständigen Kontakt (Datenminimierung)",
    ],
  },
  {
    version: "1.17.2",
    date: "25.09.2026",
    title: "Worker: KI-Clients sauber schließen",
    changes: [
      'Die HTTP-Clients der KI-Anbieter werden nach jedem Anbieterschritt geschlossen, der Worker meldet nach KI-Läufen kein "Event loop is closed" mehr',
    ],
  },
  {
    version: "1.17.1",
    date: "25.09.2026",
    title: "KI-Import: parallele Verarbeitung der Teile",
    changes: [
      "KI: Teile großer Listen werden parallel verarbeitet (vier gleichzeitige Anfragen an den Anbieter statt nacheinander); ein Import mit 11 Teilen braucht damit statt 5 bis 10 Minuten etwa ein Viertel der Zeit. Fortschrittsanzeige und Aufteilung zu großer Teile bleiben erhalten",
    ],
  },
  {
    version: "1.17.0",
    date: "25.09.2026",
    title: "Tickets zusammenführen in der Oberfläche",
    changes: [
      "Tickets: Aktion Zusammenführen im Ticketdetail mit Suche nach Zielticket (Nummer oder Titel), Vorschau beider Tickets und Bestätigung, danach Weiterleitung zum Zielticket",
      "Tickets: zusammengeführte Quelltickets zeigen einen Hinweis mit Link zum Zielticket und sind für Bearbeitung, Checkliste und Kommentare gesperrt (auch in der API)",
      "Tickets: Zielticket zeigt Enthält Ticket mit allen Quelltickets",
      "Ticketliste: zusammengeführte Tickets standardmäßig ausgeblendet, Filter Zusammengeführte anzeigen",
      "API: Zusammenführen in ein bestehendes Ticket über target_ticket_id; Verlauf des Ziels vermerkt die Herkunft je Quelle mit Anzahl verschobener Einträge",
      "API: SLA-Uhren der Quelltickets werden erledigt, Zuweiser der Quellen am Ziel ergänzt, Ticketliste mit Suche q, include_merged und merged_into, Ticketdetail mit message_count",
    ],
  },
  {
    version: "1.16.0",
    date: "25.09.2026",
    title: "SLA-Eskalation per E-Mail und SMS",
    changes: [
      "SLA-Eskalation: Kanäle je Stufe (Standard Stufe 1 intern, Stufe 2 intern und E-Mail, Stufe 3 intern, E-Mail und SMS), je Regel über channels_by_level anpassbar",
      "SLA-Eskalation: E-Mail wird als Systemmail ohne Freigabeprozess über das Standardpostfach versendet (Gmail oder SMTP), mit Objekt, Priorität, Fälligkeit und Link zum Ticket",
      "SLA-Eskalation: neuer Kanal SMS über ein anbieterneutrales HTTP-Gateway je Mandant, Einstellungen unter SLA, Reiter SMS-Gateway, mit Testnachricht",
      "Notfallalarme zeigen Zustellung und Fehlerhinweis (delivered_at, delivery_error); fehlt Postfach oder Gateway, wird der Alarm mit Hinweis protokolliert",
      "Mitglieder: Mobilnummer je Mitglied pflegbar, genutzt für SMS an die Bereitschaft",
      "Mailversand nach Vier-Augen-Freigabe nutzt denselben gemeinsamen Transport (communication/transport.py); SMTP-Fehler nennen nur noch die Fehlerart",
    ],
  },
  {
    version: "1.15.1",
    date: "25.09.2026",
    title: "KI-Chat: Fehlermeldungen mit Schritt und Status",
    changes: [
      "KI-Chat: Fehlermeldungen nennen jetzt den Schritt (Unterhaltung anlegen, Nachricht senden, Lauf abfragen) und den HTTP-Status, damit Abbrüche wie Datensatz nicht gefunden zuzuordnen sind",
    ],
  },
  {
    version: "1.15.0",
    date: "25.09.2026",
    title:
      "Belegeingang mit KI, OpenImmo, Übergabeprotokoll mit Gehilfen und U-Protokoll-Übernahme",
    changes: [
      "Belegeingang (M14): KI-Extraktion von Rechnungen als Vorschlag (Aussteller, Nummern, Daten, Beträge, Skonto, Objektbezug) mit serverseitigen Warnungen bei IBAN-Abweichung und Dublette; Übernahme nur als Entwurf mit Vier-Augen-Prüfung, IBAN wird maskiert angezeigt und muss aus dem Original bestätigt werden; Fremdwährung wird gesperrt",
      "Belegeingang: Erfassung aus Mail-Anhängen (Schaltfläche Als Rechnung erfassen) und aus Paperless per Dokumentnummer; automatische Erfassung bleibt zurückgestellt (M14-05)",
      "Anzeigen (M26): OpenImmo-Export je Anzeige und als Sammelexport mit vorheriger Vollständigkeitsprüfung, Adresse nur bei Freigabe, kein Portalupload",
      "Übergabeprotokoll: Objekt und Einheit auch manuell erfassbar (Adresse, Etage, Einheit, externe Objektnummer, Eigentümername), Umschalter Bestand oder manuell",
      "Übergabeprotokoll: Gehilfenzugang über den bestehenden Portalzugang (Art Gehilfe, Mieter, Eigentümer, 30 Tage gültig), Einladung als Entwurf im Postausgang, Abschluss mit Rückfrage, PDF und Durchschrift an alle Beteiligten als Zustellentwürfe, Verwaltung der Zugänge im CRM",
      "Übergabeprotokoll: Datenübernahme aus U-Protokoll (MariaDB-Dump mit Vorschau und Übernahme, Dateien per ZIP mit Prüfsummenabgleich), idempotent je Quelldatensatz",
      "Planung: objektakte wird vollständig ins CRM überführt (docs/plans/M35-objektakte-uebernahme.md, sechs Stufen, offene Entscheidungen M35-01 bis M35-07)",
    ],
  },
  {
    version: "1.14.2",
    date: "25.09.2026",
    title: "Mail-Archivierung bei jedem Ticketabschluss",
    changes: [
      "Tickets: jeder Abschlussstatus (erledigt, abgeschlossen, abgelehnt) archiviert die zugehörigen Mails im Postfach; bisher nur erledigt und abgeschlossen. Die Postfach-Einstellung zur Archivierung bleibt maßgeblich",
    ],
  },
  {
    version: "1.14.1",
    date: "25.09.2026",
    title: "Abschaltplan Immoware Hub",
    changes: [
      "Runbook zur vierstufigen Abschaltung des Immoware Hub mit Rückweg je Schritt, Voraussetzungen und Aufbewahrungsfristen",
      "Weiterleitung der alten Hub-Hostnamen immoware.muellerhv.de und mail.muellerhv.de auf das CRM über Traefik (Zusatzdatei im Deploy)",
    ],
  },
  {
    version: "1.14.0",
    date: "25.09.2026",
    title: "KI-Wissensbasis und Mail-Vorbereitung",
    changes: [
      "KI-Wissensbasis je Mandant und Objekt unter Einstellungen, KI: Ablageregeln, Arbeitsweisen, Fakten und gelernte Korrekturen, filterbar je Objekt",
      "Mail-Vorbereitung: eingehende Mail wird dem Kontakt, der Einheit und dem Objekt zugeordnet, passende Objektdokumente (z. B. Teilungserklärung) werden gezielt aus Paperless und Google Drive nur im Ordner bzw. unter der Objektnummer des Objekts gesucht, ein Antwortentwurf wird als Vorschlag erzeugt; nichts wird versendet",
      "Mail: Panel Vorbereitung in der Mail-Ansicht mit Übernehmen (Entwurf) und Korrigieren; Korrekturen werden als gelernte Wissenseinträge gespeichert",
      "Regel M20-05: Dokumentsuche der KI ist strikt auf das jeweilige Objekt beschränkt, keine Kontoauflistung",
    ],
  },
  {
    version: "1.13.0",
    date: "25.09.2026",
    title: "Lernphase Immoware24",
    changes: [
      "Neue Lernphase (M33) für den Immoware24-Spiegel: WebDAV-, CardDAV- und CalDAV-Läufe erkunden lesend Ordnerstruktur und Feldnutzung der bereits gespiegelten Daten, Übernahme des Moduls Learning aus dem stillgelegten Immoware Hub",
      "Jeder Lauf vergleicht sich mit dem letzten erfolgreichen Lauf gleicher Art und liefert lesbare Änderungssätze",
      "Neue Seite Immoware24 – Lernphase mit Artauswahl, Lauflisten und Detailansicht der Fakten, kein Schreibpfad Richtung Immoware24",
    ],
  },
  {
    version: "1.12.0",
    date: "25.09.2026",
    title: "Portal für Mieter, Eigentümer und Dienstleister",
    changes: [
      "Portal portal.mueller-holding.ag: Startseite je Rolle nach der Anmeldung; Mieter und Eigentümer sehen Dokumente mit Download, Meldungen mit Verlauf, Foto und Kommentar, Kontoauszug, Zählerstand und Datenänderung; Dienstleister sehen ihre Aufträge mit Ablehnen, Angebot, Termin, Ausführungsbericht und Rechnungseinreichung",
      "Portal: alle Angaben mit Geld- oder Vertragsbezug sind Vorschläge und werden von der Verwaltung geprüft, nichts wird automatisch übernommen",
      "Portal: Menü je Rolle, auf Handy und Tablet nutzbar; vertrauenswürdige Geräte gibt es im Portal bewusst nicht, der zweite Faktor bleibt bei jeder Anmeldung",
    ],
  },
  {
    version: "1.11.1",
    date: "25.09.2026",
    title: "Immoware24-Kalender werden automatisch erkannt",
    changes: [
      "Immoware24-Kalender: der Abgleich ermittelt die Kalender unter der eingetragenen Adresse selbst (PROPFIND auf die Kalender-Heimat des Benutzers) und fragt jeden Kalender einzeln ab; eine Heimatadresse wie .../calendars/users/<Login>/ führt nicht mehr zu REPORT 404",
      "Immoware24-DAV: abgeleitete Adressen für Kalender und Adressbuch nutzen den hinterlegten Login (.../users/<Login>/), wenn keine eigene Adresse eingetragen ist",
    ],
  },
  {
    version: "1.11.0",
    date: "25.09.2026",
    title:
      "Zwei-Faktor für Administratoren, Google-Kalender, Kontakttypen mit SEPA-Mandat, Banking über finAPI, Bearbeiterzuweisung",
    changes: [
      "Anmeldung: Zwei-Faktor-Pflicht nur noch für Administratoren, vertrauenswürdige Geräte 180 Tage ohne erneuten zweiten Faktor",
      "Kalender: Google-Kalender je Postfach, Vorgabe ist das Standardpostfach des Mandanten (info@), zusätzlich das dem Benutzer zugewiesene Postfach; Postfächer müssen dafür einmal neu verbunden werden",
      "Kontakte: Kontakttypen (Eigentümer, Mieter, Verwalter, Dienstleister, Bank, Sonstiges), SEPA-Freigabe je Bankverbindung mit Mandat als PDF oder Erteilung per Telefon, Brief oder E-Mail mit Datum",
      "Banking: Kontoanbindung über finAPI (Lesezugriff, WebForm) neben dem Dateiupload, Konten werden Objekten und Buchungskreisen zugeordnet; Zahlungsauslösung bleibt hinter Gate G2 gesperrt",
      "Tickets: automatische Bearbeiterzuweisung nach Postfach, Anrede oder Signatur, Kompetenzen je Benutzer (Katalog unter Einstellungen, Benutzer) und bisheriger Zuordnung; mehrere Bearbeiter je Ticket",
      "Tickets: Erledigen archiviert die zugehörige Gmail-Nachricht; Tickets werden am Kontakt, Objekt und an der Einheit angezeigt",
      "Mail: Weiterleitung von Firmenrechnungen (nicht Objektrechnungen) an die Buchhaltungsadresse mit Lernen aus Korrekturen, jede Weiterleitung nur nach Freigabe",
      "SLA: Schaltfläche Vorschlagswerte laden legt fehlende Regeln je Priorität und den Geschäftszeitenkalender als Vorschlag an (Produktschutz, keine Rechtsvorschrift)",
      "Oberfläche: Favicon und App-Symbol im CRM",
    ],
  },
  {
    version: "1.10.0",
    date: "25.09.2026",
    title:
      "Tickets mit Sammelstatus und Vorlagen, Start-Auswertungen, Handy-Oberfläche, KI-Stückelung",
    changes: [
      "Tickets: Sammelauswahl mit Statuswechsel (Mitarbeiter höchstens 10 gleichzeitig, Administratoren unbegrenzt), Ticketvorlagen mit Checklisten und Pflichtfeldern (z. B. IBAN beim Kautionsticket) unter Einstellungen",
      "Start: Auswertungen mit Kennzahlen und Grafik (Tickets offen, neu und erledigt je Tag, Woche, Monat, Quartal, Jahr), Filter je Benutzer und Vergleich zweier Benutzer",
      "Menü: Mail und Tickets unter Übersicht, eigene Gruppe Makler (Anzeigen, FLOW-Import, Übergabeprotokoll), WEG-Objekte und WEG-Verwaltung als ein Eintrag, Importassistent ohne Zusatz",
      "Handy und Tablet: Menü im Vordergrund, Mail-Ansicht ohne seitlichen Überlauf und lesbar auf dem Handy, Chat mit Fortschrittsanzeige und eigener Farbgebung",
      "KI: Umlaute aus Windows-kodierten CSV-Dateien korrekt, große Listen werden in Teilen verarbeitet statt gesperrt, automatische Wahl des großen Modells bei Umfang, Fortschritt je Teil, Zeichenstatistik je Datei im Lauf",
      "Buchhaltung: Auswertungen je Buchungskreis (Liquiditätsvorschau 90 Tage, Zahlungen je Debitor, Erträge je Erlöskonto)",
      "Makler: Anzeigenformulare in Gruppen (Objekt, Adresse und Freigabe, Preise mit Warmmiete, Energieausweis, Ausstattung, Vermarktung)",
      "Tests: Integrationstests für DMS-Anzeige und Immoware-Spiegel",
    ],
  },
  {
    version: "1.9.2",
    date: "25.09.2026",
    title: "OIDC-Anbieter für die Statusseite zusammengeführt",
    changes: [
      "Das CRM stellt eine OpenID-Connect-Anmeldung für angebundene Dienste bereit, zuerst genutzt von der Statusseite status.mueller-holding.ag",
      "Zweig für die Statusseiten-Anmeldung in den Hauptstand übernommen, damit spätere Deploys die Funktion behalten",
    ],
  },
  {
    version: "1.9.1",
    date: "25.09.2026",
    title: "Google Drive per OAuth verbinden",
    changes: [
      "Auf der DMS-Seite verbindet ein Klick auf Mit Google verbinden das Drive-Konto, Client-Secret und Refresh-Token werden automatisch hinterlegt",
      "Manuelle Eingabe bleibt als Alternative erhalten",
    ],
  },
  {
    version: "1.9.0",
    date: "25.09.2026",
    title: "Immoware24-Lesezugriff per DAV",
    changes: [
      "Neues Paket mhvp.immoware: Spiegel von Immoware24 per WebDAV, CardDAV und CalDAV, strikt lesend",
      "Anbindung je Tenant mit Verbindungstest, manueller und automatischer Abholung alle 15 Minuten",
      "Dokumentbaum, Adressbuch (Zuordnung oder Anlage als CRM-Kontakt) und Kalender als Spiegeltabellen",
    ],
  },
  {
    version: "1.8.0",
    date: "25.09.2026",
    title: "Gehilfenzugang für Übergabeprotokolle über das Portal",
    changes: [
      "Makler, Übergabeprotokolle: Portalzugang je Beteiligtem mit CRM-Kontakt einrichten und beenden; Portalkonto wird bei Bedarf angelegt, Einladungscode einmalig angezeigt",
      "Portal: Anmeldung mit Passwort und zweitem Faktor, Liste der eigenen Übergabeprotokolle, Ausfüllen der Abschnitte, Fotos, Unterschrift, Abschluss; interne Vermerke bleiben verborgen",
      "Nach dem Abschluss durch den Beteiligten bleibt das PDF im Portal 14 Tage lesbar, danach erlischt der Zugang; Zustellung weiterhin nur über den Postausgang",
      "Portal-API /api/v1/portal/handover, Regel M30-01 ergänzt, offene Fragen M30-01 und M30-05",
    ],
  },
  {
    version: "1.7.0",
    date: "25.09.2026",
    title: "Übergabeprotokolle im Bereich Makler",
    changes: [
      "Neuer Unterpunkt Makler, Übergabeprotokolle: Anlage mit Vorbelegung aus Objekt und Einheit, Beteiligte aus den Kontakten, Zähler, Räume, Mängel, Schlüssel, Gegenstände, Bemerkungen, Fotos und Anhänge als Dokumente",
      "Unterschriften per Canvas mit Prüfsumme, Hinweise vor dem Abschluss, Abschluss mit PDF auf dem Briefbogen, Festschreibung, neue Versionen ohne Dateiduplikate, Stornierung, Archivierung",
      "Zustellung an die Beteiligten als E-Mail-Entwurf im Postausgang (Vier-Augen-Freigabe), kein automatischer Versand",
      "Protokollnummern UP-JJJJMMTT-NNN aus der Nummernfolge je Mandant und Tag",
      "Migration 0043 (Tabellen handover_*), Regel M30-01, Plan M30; Gehilfenzugang über das Portal folgt als Stufe 3",
    ],
  },
  {
    version: "1.6.1",
    date: "25.09.2026",
    title: "Google Drive auf der DMS-Seite einrichtbar",
    changes: [
      "Google-Drive-Anbindung wird auf der Seite DMS-Anbindung eingerichtet: Wurzelordner, OAuth-Client, Zugangsdaten",
    ],
  },
  {
    version: "1.6.0",
    date: "25.09.2026",
    title: "Einstellungsseite DMS-Anbindung",
    changes: [
      "Neue Einstellungsseite DMS-Anbindung: Paperless-Basis-URL, API-Token und die Feld-IDs Objektnummer und Gesellschaft im Browser pflegbar",
      "Google Drive wird auf derselben Seite nur lesend angezeigt (aktiv, Basis-URL, Token hinterlegt)",
      "Karte DMS-Anbindung in den Einstellungen, sichtbar mit dem Recht tenant_settings:update",
    ],
  },
  {
    version: "1.5.1",
    date: "25.09.2026",
    title: "Korrektur Migration SLA",
    changes: [
      "Migration 0042 verwendet den vorhandenen Typ ticket_priority statt ihn erneut anzulegen, Deploy brach bisher ab",
    ],
  },
  {
    version: "1.5.0",
    date: "25.09.2026",
    title: "Paperless-Dokumente in Ticket und Objekt",
    changes: [
      "Abschnitt Dokumente (Paperless) in der Ticketansicht und in der Objektansicht mit Vorschau und Download",
      "Suche in Paperless über die Objektnummer (Custom Field) und die Ticketnummer im Volltext, Treffer werden zusammengeführt",
      "Dateien werden über das CRM durchgereicht, der Paperless-Zugang bleibt serverseitig",
      "Feld-IDs für Objektnummer und Gesellschaft je Mandant in der DMS-Anbindung einstellbar",
      "Versionsnummer im Footer mit Verlauf unter /version",
    ],
  },
  {
    version: "1.4.0",
    date: "25.09.2026",
    title: "SLA, Notfallkette und Bereitschaft",
    changes: [
      "SLA-Regeln je Ticketpriorität mit Reaktions- und Lösungszeit, Uhren laufen nur in der Geschäftszeit",
      "Arbeitskalender mit Feiertagen, Uhren lassen sich pausieren und fortsetzen",
      "Eskalationsstufen mit Benachrichtigung an Zuständige und Bereitschaft",
      "Bereitschaftsplan mit aktueller Bereitschaft und Alarmen zum Quittieren",
      "Einstellungsseite SLA und Bereitschaft, SLA-Ampel im Ticket",
      "Erste Antwort per freigegebener Mail stoppt die Reaktionsuhr",
    ],
  },
  {
    version: "1.3.0",
    date: "25.09.2026",
    title: "KI-Vorschläge und Playbooks für Mails",
    changes: [
      "KI-Antwortvorschlag je eingehender Mail im Ticket",
      "Playbooks werden aus abgeschlossenen Tickets gelernt und beim nächsten gleichartigen Vorgang angeboten",
      "Tickets zusammenführen zu einem neuen Ticket mit neuer Nummer, Verlauf bleibt erhalten",
    ],
  },
  {
    version: "1.2.1",
    date: "25.09.2026",
    title: "SLA, Notfallkette und Bereitschaft",
    changes: [
      "SLA-Regeln je Ticketpriorität mit Reaktions- und Lösungszeit, Uhren laufen nur in der Geschäftszeit",
      "Arbeitskalender mit Feiertagen, Uhren lassen sich pausieren und fortsetzen",
      "Eskalationsstufen mit Benachrichtigung an Zuständige und Bereitschaft",
      "Bereitschaftsplan mit aktueller Bereitschaft und Alarmen zum Quittieren",
      "Einstellungsseite SLA und Bereitschaft, SLA-Ampel im Ticket",
      "Erste Antwort per freigegebener Mail stoppt die Reaktionsuhr",
      "Migration 0042, Plan docs/plans/M30-sla.md",
    ],
  },
  {
    version: "1.2.0",
    date: "24.09.2026",
    title: "Postfach im CRM",
    changes: [
      "Gmail-Abruf je Postfach, jede Mail wird einem Ticket zugeordnet oder eröffnet ein neues",
      "Google-OAuth-Einstellungen, Standardpostfach und Zugriff je Benutzer",
      "Mail-Reiter im Ticket mit Vier-Augen-Freigabe vor dem Versand über Gmail",
      "Fehlerhafte Einzelmails brechen den Abruf nicht mehr ab und werden gemeldet",
    ],
  },
  {
    version: "1.1.0",
    date: "24.09.2026",
    title: "Makler, DMS-Bereich und neue Oberfläche",
    changes: [
      "Maklerbereich mit Miet- und Kaufangeboten, Felder nach FLOW-Datenvertrag, FLOW-Import",
      "DMS-Bereich mit Anbindung der Objektübernahme (objektakte)",
      "Überarbeitetes Design mit dunkler Navigationsleiste, Seitenköpfen und Dashboard-Kacheln, mobile Ansicht",
      "Einstellungsbereich mit Benutzerverwaltung, Rollen, Mandant, Profil",
      "KI-Assistent auf jeder Seite mit Seitenkontext, Auswertung aller Chats für Revisionsleser",
      "Mehrkern-Auslegung für API, Celery und PostgreSQL im Produktivbetrieb",
    ],
  },
  {
    version: "1.0.0",
    date: "23.09.2026",
    title: "Marktreife der Grundplattform",
    changes: [
      "Mandantenfähige Plattform mit Rollen, Rechten und Revisionsprotokoll",
      "Kontakte, Objekte, Einheiten, Verträge",
      "Dokumente mit Aufbewahrung, DMS-Spiegel (Paperless, Google Drive), Briefe und Serienbriefe",
      "Buchungskreis, Bankanbindung, Matching mit KI-Kontierung, Sollstellung, Verwalterhonorar",
      "Belegeingang, Kreditoren, Zahlläufe, Mahnwesen, Mietabrechnung, Auswertungen und Exporte",
      "Tickets und Aufträge, Postfach, Portale für Mieter, Eigentümer und Dienstleister",
      "WEG-Wirtschaftsplan und Abrechnung, Versammlung, Beiratsprüfung, Mieterhöhung und Vermietung",
      "Immoware24-Import und KI-Onboarding",
    ],
  },
];

export const CURRENT_VERSION = CHANGELOG[0]?.version ?? "0.0.0";
