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
