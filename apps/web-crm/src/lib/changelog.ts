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
    version: "1.17.1",
    date: "25.09.2026",
    title: "Worker: KI-Clients sauber schließen",
    changes: [
      "Die HTTP-Clients der KI-Anbieter werden nach jedem Anbieterschritt geschlossen, der Worker meldet nach KI-Läufen kein \"Event loop is closed\" mehr",
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
    title: "Belegeingang mit KI, OpenImmo, Übergabeprotokoll mit Gehilfen und U-Protokoll-Übernahme",
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
