/**
 * Static search index for the settings hub (operator request 27.09.2026: "Ergänze eine Suche
 * bei Einstellungen"). One entry per settings page under `src/app/(app)/einstellungen/**` plus
 * one entry per named section within a page (heading, card or form group), so the search
 * reaches into the second and third level below the hub, not only the page itself.
 *
 * `permission` mirrors the same right that already shows or hides the card on the hub
 * (`src/app/(app)/einstellungen/page.tsx`) or gates the page itself (its `notFound()` check);
 * an array is read as "any of these" (matches an `a || b` gate), `null` means visible to
 * everyone (no gate on the page). Sections reuse their page's permission, not a narrower one
 * some inner widget may additionally require, exactly as instructed.
 *
 * Anchors (`#id`) only exist where the heading actually carries that `id`. A few pages render
 * their sections through components other agents are working on in parallel
 * (`src/components/mail/*`, `src/components/settings/SignatureProfile.tsx`,
 * `SignatureTemplateSettings.tsx`, `ProfileSettings.tsx`, `MembersAdmin.tsx`) or through
 * `src/app/(app)/einstellungen/bank/page.tsx`; those sections link to the page only, without an
 * anchor, per the task instructions.
 */

export type SettingsSearchEntry = {
  /** Stable id, used as the React key and for the "existing page" file system test. */
  id: string;
  /** Result title, most heavily weighted in the search. */
  title: string;
  /** Levels shown above the title, e.g. ["Einstellungen", "Buchhaltung", "Steuern"]. */
  breadcrumb: string[];
  /** Target path, optionally with a `#anchor` into a section of that page. */
  href: string;
  /** Synonyms and related terms matched after the title. */
  keywords: string[];
  /** Permission codes; any one present grants visibility. `null` means always visible. */
  permission: string[] | null;
};

const ROOT = "Einstellungen";

export const settingsSearchIndex: SettingsSearchEntry[] = [
  // --- Benutzer und Rollen -------------------------------------------------------------
  {
    id: "benutzer",
    title: "Benutzer und Rollen",
    breadcrumb: [ROOT, "Benutzer und Rollen"],
    href: "/einstellungen/benutzer",
    keywords: ["benutzer", "mitarbeiter", "account", "zugang", "user", "konten", "einladen"],
    permission: ["members:read"],
  },
  {
    id: "benutzer-hinzufuegen",
    title: "Benutzer hinzufügen",
    breadcrumb: [ROOT, "Benutzer und Rollen", "Benutzer hinzufügen"],
    href: "/einstellungen/benutzer",
    keywords: ["einladen", "neuer benutzer", "account anlegen", "user hinzufügen", "mitarbeiter anlegen"],
    permission: ["members:read"],
  },
  {
    id: "rollen",
    title: "Rollen und Rechte",
    breadcrumb: [ROOT, "Rollen und Rechte"],
    href: "/einstellungen/rollen",
    keywords: ["rolle", "rechte", "berechtigung", "permission", "zugriffsrecht"],
    permission: ["roles:read"],
  },
  {
    id: "rollen-anlegen",
    title: "Rolle anlegen",
    breadcrumb: [ROOT, "Rollen und Rechte", "Rolle anlegen"],
    href: "/einstellungen/rollen#roles-create-title",
    keywords: ["neue rolle", "rolle anlegen"],
    permission: ["roles:read"],
  },
  {
    id: "rollen-portalrechte",
    title: "Portalrechte je Rolle",
    breadcrumb: [ROOT, "Rollen und Rechte", "Portalrechte je Rolle"],
    href: "/einstellungen/rollen#portal-role-permissions-title",
    keywords: ["portal", "mieterportal", "eigentümerportal", "zugriff portal", "portalfunktion"],
    permission: ["roles:read"],
  },

  // --- Mandant und Briefbogen -----------------------------------------------------------
  {
    id: "mandant",
    title: "Mandant und Briefbogen",
    breadcrumb: [ROOT, "Mandant und Briefbogen"],
    href: "/einstellungen/mandant",
    keywords: ["firma", "firmendaten", "mandant", "briefkopf", "stammdaten unternehmen", "unternehmen"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "mandant-markenfarben",
    title: "Markenfarben",
    breadcrumb: [ROOT, "Mandant und Briefbogen", "Markenfarben"],
    href: "/einstellungen/mandant#company-branding-title",
    keywords: ["farbe", "branding", "logo", "corporate design", "ci farben"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "mandant-rechtstraeger",
    title: "Rechtsträger der verwaltenden Gesellschaft",
    breadcrumb: [ROOT, "Mandant und Briefbogen", "Rechtsträger der verwaltenden Gesellschaft"],
    href: "/einstellungen/mandant#manager-entity-title",
    keywords: ["rechtsträger", "legal entity", "verwaltende gesellschaft", "hausverwaltung müller gmbh"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "mandant-signaturvorlage",
    title: "E-Mail-Signaturvorlage",
    breadcrumb: [ROOT, "Mandant und Briefbogen", "E-Mail-Signaturvorlage"],
    href: "/einstellungen/mandant",
    keywords: ["signatur", "vorlage", "unterschrift mail", "mailsignatur mandant"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "mandant-ticketantworten-freigabe",
    title: "Ticketantworten, Freigabe für alle",
    breadcrumb: [ROOT, "Mandant und Briefbogen", "Ticketantworten, Freigabe für alle (Notbremse)"],
    href: "/einstellungen/mandant#ticket-reply-approval-all-title",
    keywords: ["freigabe alle", "notbremse", "vier augen prinzip ticket", "alle antworten freigeben"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "mandant-messdienstleister-modul",
    title: "Messdienstleister-Modul",
    breadcrumb: [ROOT, "Mandant und Briefbogen", "Messdienstleister-Modul"],
    href: "/einstellungen/mandant#metering-module-switch-title",
    keywords: ["messdienstleister modul", "ista schalten", "techem schalten", "modul aktivieren"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "mandant-lernbeispiele",
    title: "Lernbeispiele aus Ticketabschlüssen",
    breadcrumb: [ROOT, "Mandant und Briefbogen", "Lernbeispiele aus Ticketabschlüssen"],
    href: "/einstellungen/mandant#ai-learning-examples-title",
    keywords: ["ki lernbeispiele", "training ki", "beispiele ticket", "ai learning"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "mandant-erledigungsarten",
    title: "Erledigungsarten beim Ticketabschluss",
    breadcrumb: [ROOT, "Mandant und Briefbogen", "Erledigungsarten beim Ticketabschluss"],
    href: "/einstellungen/mandant#resolution-kinds-title",
    keywords: ["erledigungsart", "abschlussgrund", "ticket schließen", "resolution kind"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "mandant-umlaufbeschluss",
    title: "Umlaufbeschluss mit einfacher Mehrheit",
    breadcrumb: [ROOT, "Mandant und Briefbogen", "Umlaufbeschluss mit einfacher Mehrheit"],
    href: "/einstellungen/mandant#circular-lower-majority-switch-title",
    keywords: ["umlaufbeschluss", "einfache mehrheit", "weg beschluss ohne versammlung"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "mandant-rechnungsstellung",
    title: "Rechnungsstellung und Steuer",
    breadcrumb: [ROOT, "Mandant und Briefbogen", "Rechnungsstellung und Steuer"],
    href: "/einstellungen/mandant#billing-settings-title",
    keywords: ["rechnung mandant", "steuer mandant", "abrechnung leistung", "billing"],
    permission: ["tenant_settings:read"],
  },

  // --- KI ---------------------------------------------------------------------------------
  {
    id: "ki",
    title: "KI-Einstellungen",
    breadcrumb: [ROOT, "KI"],
    href: "/einstellungen/ki",
    keywords: ["ki", "ai", "künstliche intelligenz", "assistent", "chatbot"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "ki-anbieterstrategie",
    title: "Anbieterstrategie",
    breadcrumb: [ROOT, "KI", "Anbieterstrategie"],
    href: "/einstellungen/ki#ai-routing-title",
    keywords: ["routing", "anbieter reihenfolge", "anthropic openai reihenfolge"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "ki-anbieter-anthropic",
    title: "Anbieter Anthropic",
    breadcrumb: [ROOT, "KI", "Anbieter Anthropic"],
    href: "/einstellungen/ki#ai-provider-anthropic-title",
    keywords: ["anthropic", "claude", "api schlüssel anthropic"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "ki-anbieter-openai",
    title: "Anbieter OpenAI",
    breadcrumb: [ROOT, "KI", "Anbieter OpenAI"],
    href: "/einstellungen/ki#ai-provider-openai-title",
    keywords: ["openai", "chatgpt", "api schlüssel openai"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "ki-verbrauch",
    title: "Verbrauch im Monat",
    breadcrumb: [ROOT, "KI", "Verbrauch"],
    href: "/einstellungen/ki#usage-title",
    keywords: ["budget ki", "kosten ki", "nutzung ki", "verbrauch"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "ki-einbettungen",
    title: "Einbettungen (Ähnlichkeitssuche)",
    breadcrumb: [ROOT, "KI", "Einbettungen"],
    href: "/einstellungen/ki#ai-embeddings-title",
    keywords: ["embeddings", "ähnlichkeitssuche", "vektor", "semantische suche"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "ki-wissensbasis",
    title: "Wissensbasis",
    breadcrumb: [ROOT, "KI", "Wissensbasis"],
    href: "/einstellungen/ki#ai-knowledge-title",
    keywords: ["wissensbasis ki", "dokumente ki", "kontext ki"],
    permission: ["tenant_settings:update"],
  },

  // --- Wissensdatenbank ---------------------------------------------------------------------
  {
    id: "wissen",
    title: "Wissensdatenbank",
    breadcrumb: [ROOT, "Wissensdatenbank"],
    href: "/einstellungen/wissen",
    keywords: ["playbook", "lernbeispiel", "wissensdatenbank", "ki gelernt", "erledigungsnotiz"],
    permission: ["tenant_settings:read"],
  },

  // --- Postfächer ---------------------------------------------------------------------------
  {
    id: "postfaecher",
    title: "Postfächer",
    breadcrumb: [ROOT, "Postfächer"],
    href: "/einstellungen/postfaecher",
    keywords: ["mail", "e-mail", "email", "gmail", "postfach", "google mail"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "postfaecher-oauth",
    title: "Google OAuth-Client",
    breadcrumb: [ROOT, "Postfächer", "Google OAuth-Client"],
    href: "/einstellungen/postfaecher",
    keywords: ["oauth", "google client", "verbindung google", "google verbinden"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "postfaecher-verbunden",
    title: "Verbundene Postfächer",
    breadcrumb: [ROOT, "Postfächer", "Verbundene Postfächer"],
    href: "/einstellungen/postfaecher",
    keywords: ["postfach hinzufügen", "mailbox", "standardpostfach"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "postfaecher-vier-augen",
    title: "Vier-Augen-Prinzip beim Mailversand",
    breadcrumb: [ROOT, "Postfächer", "Vier-Augen-Prinzip"],
    href: "/einstellungen/postfaecher#mail-approval-settings-title",
    keywords: ["vier augen", "freigabe mail", "genehmigung versand", "stellvertreter", "deputy"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "postfaecher-rechnungsweiterleitung",
    title: "Rechnungs-Weiterleitung",
    breadcrumb: [ROOT, "Postfächer", "Rechnungs-Weiterleitung"],
    href: "/einstellungen/postfaecher",
    keywords: ["rechnung weiterleiten", "invoice forwarding", "beleg mail", "weiterleitung"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "postfaecher-telefonassistenz",
    title: "Telefonassistenz (Hallo Heidi)",
    breadcrumb: [ROOT, "Postfächer", "Telefonassistenz"],
    href: "/einstellungen/postfaecher",
    keywords: ["telefonassistenz", "hallo heidi", "anruf mail", "call assistant"],
    permission: ["tenant_settings:update"],
  },

  // --- DMS-Anbindung --------------------------------------------------------------------
  {
    id: "dms",
    title: "DMS-Anbindung",
    breadcrumb: [ROOT, "DMS-Anbindung"],
    href: "/einstellungen/dms",
    keywords: ["dms", "dokumentenmanagement", "paperless", "google drive"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "dms-paperless",
    title: "Paperless",
    breadcrumb: [ROOT, "DMS-Anbindung", "Paperless"],
    href: "/einstellungen/dms#dms-paperless-title",
    keywords: ["paperless", "zugangsdaten dms"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "dms-google-drive",
    title: "Google Drive",
    breadcrumb: [ROOT, "DMS-Anbindung", "Google Drive"],
    href: "/einstellungen/dms#dms-google-drive-title",
    keywords: ["google drive", "oauth drive", "drive verbinden"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "dms-belegeingang",
    title: "Automatischer Belegeingang",
    breadcrumb: [ROOT, "DMS-Anbindung", "Automatischer Belegeingang"],
    href: "/einstellungen/dms#invoice-intake-auto-title",
    keywords: ["beleg", "rechnungseingang", "automatisch", "invoice intake"],
    permission: ["tenant_settings:update"],
  },

  // --- Aufbewahrung --------------------------------------------------------------------
  {
    id: "aufbewahrung",
    title: "Aufbewahrung",
    breadcrumb: [ROOT, "Aufbewahrung"],
    href: "/einstellungen/aufbewahrung",
    keywords: ["aufbewahrungsfrist", "löschung", "retention", "dokumentkategorie", "löschvorschlag"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "aufbewahrung-zuordnung",
    title: "Zuordnung Dokumentkategorie zu Profil",
    breadcrumb: [ROOT, "Aufbewahrung", "Zuordnung Dokumentkategorie zu Profil"],
    href: "/einstellungen/aufbewahrung#retention-mapping-title",
    keywords: ["kategorie zuordnen", "dokumentklasse", "profil zuordnen"],
    permission: ["tenant_settings:update"],
  },

  // --- Bank --------------------------------------------------------------------------------
  {
    id: "bank",
    title: "Bank (finAPI)",
    breadcrumb: [ROOT, "Bank"],
    href: "/einstellungen/bank",
    keywords: ["bank", "konto", "finapi", "iban", "onlinebanking", "fints", "kontoinformationsdienst"],
    permission: ["tenant_settings:update"],
  },

  // --- Telefonie ---------------------------------------------------------------------------
  {
    id: "telefonie",
    title: "Telefonie-Webhook",
    breadcrumb: [ROOT, "Telefonie"],
    href: "/einstellungen/telefonie",
    keywords: ["telefon", "anruf", "telefonanlage", "webhook telefon", "rufnummer"],
    permission: ["tenant_settings:read"],
  },

  // --- Schnittstellen ------------------------------------------------------------------------
  {
    id: "schnittstellen",
    title: "Schnittstellen",
    breadcrumb: [ROOT, "Schnittstellen"],
    href: "/einstellungen/schnittstellen",
    keywords: ["schnittstelle", "integration", "extern", "anbindung"],
    permission: null,
  },
  {
    id: "schadenbearbeiter",
    title: "Schadenbearbeiter",
    breadcrumb: [ROOT, "Schnittstellen", "Schadenbearbeiter"],
    href: "/einstellungen/schnittstellen/schadenbearbeiter",
    keywords: ["schadenbearbeiter", "schadenstool", "versicherung", "schaden", "mdv", "midive", "gutachter"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "schadenbearbeiter-uebernahme",
    title: "Vorhandene Schadentickets übernehmen",
    breadcrumb: [ROOT, "Schnittstellen", "Schadenbearbeiter", "Übernahme"],
    href: "/einstellungen/schnittstellen/schadenbearbeiter#sdt-takeover-title",
    keywords: ["schadenticket", "übernehmen", "import", "zuordnen"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "messdienstleister",
    title: "Messdienstleister",
    breadcrumb: [ROOT, "Schnittstellen", "Messdienstleister"],
    href: "/einstellungen/schnittstellen/messdienstleister",
    keywords: ["messdienstleister", "ista", "techem", "kalo", "brunata", "zähler", "verbrauch"],
    permission: ["metering_data:read"],
  },
  {
    id: "messdienstleister-verbindungen",
    title: "Verbindungen",
    breadcrumb: [ROOT, "Schnittstellen", "Messdienstleister", "Verbindungen"],
    href: "/einstellungen/schnittstellen/messdienstleister#metering-connection-title",
    keywords: ["verbindung anlegen", "zugang messdienstleister"],
    permission: ["metering_data:read"],
  },
  {
    id: "messdienstleister-bved",
    title: "bved 3.10 Austauschdateien",
    breadcrumb: [ROOT, "Schnittstellen", "Messdienstleister", "bved 3.10 Austauschdateien"],
    href: "/einstellungen/schnittstellen/messdienstleister#bved-austausch",
    keywords: ["heiwako", "bved", "austauschdatei"],
    permission: ["metering_data:read"],
  },
  {
    id: "messdienstleister-zuordnung",
    title: "Zuordnungsübersicht",
    breadcrumb: [ROOT, "Schnittstellen", "Messdienstleister", "Zuordnungsübersicht"],
    href: "/einstellungen/schnittstellen/messdienstleister#zuordnungen",
    keywords: ["zuordnung objekt zähler", "übersicht messdienstleister"],
    permission: ["metering_data:read"],
  },
  {
    id: "webhooks",
    title: "Webhook-Abonnements",
    breadcrumb: [ROOT, "Schnittstellen", "Webhooks"],
    href: "/einstellungen/webhooks",
    keywords: ["webhook", "ereignis", "abonnement", "fremdsystem"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "webhooks-geheimnis",
    title: "Geheimnis",
    breadcrumb: [ROOT, "Schnittstellen", "Webhooks", "Geheimnis"],
    href: "/einstellungen/webhooks#webhook-secret-title",
    keywords: ["secret", "hmac", "signatur webhook"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "webhooks-neu",
    title: "Neues Abonnement",
    breadcrumb: [ROOT, "Schnittstellen", "Webhooks", "Neues Abonnement"],
    href: "/einstellungen/webhooks#webhook-new-title",
    keywords: ["webhook anlegen", "neu abonnement"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "immoware",
    title: "Immoware24-Anbindung",
    breadcrumb: [ROOT, "Schnittstellen", "Immoware24"],
    href: "/einstellungen/immoware",
    keywords: ["immoware", "immoware24", "webdav", "carddav", "caldav"],
    permission: ["immoware:read"],
  },
  {
    id: "immoware-verbindung",
    title: "Verbindung",
    breadcrumb: [ROOT, "Schnittstellen", "Immoware24", "Verbindung"],
    href: "/einstellungen/immoware#immoware-connection-title",
    keywords: ["verbindung immoware", "zugangsdaten immoware"],
    permission: ["immoware:read"],
  },
  {
    id: "immoware-abholung",
    title: "Abholung",
    breadcrumb: [ROOT, "Schnittstellen", "Immoware24", "Abholung"],
    href: "/einstellungen/immoware#immoware-sync-title",
    keywords: ["sync", "synchronisation", "abholen", "manueller lauf"],
    permission: ["immoware:read"],
  },

  // --- WEG ---------------------------------------------------------------------------------
  {
    id: "weg",
    title: "WEG",
    breadcrumb: [ROOT, "WEG"],
    href: "/einstellungen/weg",
    keywords: ["weg", "mehrheitsregel", "beschluss", "eigentümerversammlung", "beschlussgegenstand"],
    permission: ["accounting:read"],
  },

  // --- Kataloge und Felder ---------------------------------------------------------------
  {
    id: "datenqualitaet",
    title: "Datenqualität",
    breadcrumb: [ROOT, "Datenqualität"],
    href: "/einstellungen/datenqualitaet",
    keywords: ["datenqualität", "erfassungsstandard", "stammdaten", "dubletten", "fehlende e-mail", "postleitzahl"],
    permission: ["contacts:read"],
  },
  {
    id: "kataloge",
    title: "Kataloge",
    breadcrumb: [ROOT, "Kataloge"],
    href: "/einstellungen/kataloge",
    keywords: ["katalog", "auswahlliste", "stammdaten liste", "anhang b"],
    permission: ["properties:read"],
  },
  {
    id: "felder",
    title: "Benutzerdefinierte Felder",
    breadcrumb: [ROOT, "Benutzerdefinierte Felder"],
    href: "/einstellungen/felder",
    keywords: ["custom field", "feldtyp", "zusatzfeld", "eigenes feld"],
    permission: ["properties:read"],
  },
  {
    id: "felder-liste",
    title: "Felder, Liste",
    breadcrumb: [ROOT, "Benutzerdefinierte Felder", "Liste"],
    href: "/einstellungen/felder#custom-fields-list",
    keywords: ["felder liste", "definierte felder"],
    permission: ["properties:read"],
  },
  {
    id: "felder-neu",
    title: "Neues Feld",
    breadcrumb: [ROOT, "Benutzerdefinierte Felder", "Neues Feld"],
    href: "/einstellungen/felder#custom-fields-form",
    keywords: ["feld anlegen", "neues feld"],
    permission: ["properties:read"],
  },

  // --- Kautionszinsen ----------------------------------------------------------------------
  {
    id: "kautionszinsen",
    title: "Kautionszinsen, Referenzzinssatz je Jahr",
    breadcrumb: [ROOT, "Kautionszinsen"],
    href: "/einstellungen/kautionszinsen",
    keywords: ["kaution", "zinssatz", "referenzzins", "kautionsabrechnung"],
    permission: ["contracts:read"],
  },
  {
    id: "kautionszinsen-setzen",
    title: "Zinssatz setzen",
    breadcrumb: [ROOT, "Kautionszinsen", "Zinssatz setzen"],
    href: "/einstellungen/kautionszinsen#deposit-rates-form-title",
    keywords: ["zins setzen", "jahr zins", "referenzzins pflegen"],
    permission: ["contracts:read"],
  },

  // --- SLA -----------------------------------------------------------------------------------
  {
    id: "sla",
    title: "SLA und Bereitschaft",
    breadcrumb: [ROOT, "SLA"],
    href: "/einstellungen/sla",
    keywords: ["sla", "bereitschaft", "eskalation", "notfall", "rufbereitschaft", "reaktionszeit"],
    permission: ["sla:read"],
  },

  // --- Tickets: Vorlagen, Formulare, Automatisierung, Antworten -----------------------------
  {
    id: "ticketvorlagen",
    title: "Ticketvorlagen",
    breadcrumb: [ROOT, "Ticketvorlagen"],
    href: "/einstellungen/ticketvorlagen",
    keywords: ["ticketvorlage", "checkliste", "zusatzfeld ticket", "wiederkehrender vorgang"],
    permission: ["tickets:read"],
  },
  {
    id: "portalformulare",
    title: "Portalformulare",
    breadcrumb: [ROOT, "Portalformulare"],
    href: "/einstellungen/portalformulare",
    keywords: ["portalformular", "formular mieter", "formular eigentümer"],
    permission: ["tickets:read"],
  },
  {
    id: "automatisierung",
    title: "Automatisierung",
    breadcrumb: [ROOT, "Automatisierung"],
    href: "/einstellungen/automatisierung",
    keywords: ["regel engine", "automation", "wenn dann", "auslöser", "regel"],
    permission: ["tenant_settings:read", "tickets:read"],
  },
  {
    id: "antwortvorlagen",
    title: "Antwortvorlagen",
    breadcrumb: [ROOT, "Antwortvorlagen"],
    href: "/einstellungen/antwortvorlagen",
    keywords: ["antwortvorlage", "textbaustein", "platzhalter", "standardantwort"],
    permission: ["tickets:read"],
  },

  // --- Buchhaltung -----------------------------------------------------------------------
  {
    id: "buchhaltung-datev",
    title: "DATEV-Kontenzuordnung",
    breadcrumb: [ROOT, "Buchhaltung", "DATEV"],
    href: "/einstellungen/buchhaltung/datev",
    keywords: ["datev", "kontenzuordnung", "buchungsstapel", "steuerberater export", "sachkonto"],
    permission: ["accounting:read"],
  },
  {
    id: "buchhaltung-datev-zuordnungen",
    title: "Zuordnungen",
    breadcrumb: [ROOT, "Buchhaltung", "DATEV", "Zuordnungen"],
    href: "/einstellungen/buchhaltung/datev#datev-mappings-title",
    keywords: ["konto zuordnen", "datev zuordnung"],
    permission: ["accounting:read"],
  },
  {
    id: "buchhaltung-datev-import",
    title: "Import aus CSV",
    breadcrumb: [ROOT, "Buchhaltung", "DATEV", "Import aus CSV"],
    href: "/einstellungen/buchhaltung/datev#datev-import-title",
    keywords: ["csv import", "datev import"],
    permission: ["accounting:read"],
  },
  {
    id: "buchhaltung-datev-pruefbericht",
    title: "Prüfbericht nicht zugeordneter Konten",
    breadcrumb: [ROOT, "Buchhaltung", "DATEV", "Prüfbericht"],
    href: "/einstellungen/buchhaltung/datev#datev-report-title",
    keywords: ["prüfbericht", "nicht zugeordnet", "datev export prüfen"],
    permission: ["accounting:read"],
  },
  {
    id: "buchhaltung-kontenrahmen",
    title: "Kontenrahmen",
    breadcrumb: [ROOT, "Buchhaltung", "Kontenrahmen"],
    href: "/einstellungen/buchhaltung/kontenrahmen",
    keywords: ["kontenrahmen", "freigabe g1", "versionsverlauf konten", "kontenplan"],
    permission: ["accounting:read"],
  },
  {
    id: "buchhaltung-steuern",
    title: "Buchhaltung, Steuern",
    breadcrumb: [ROOT, "Buchhaltung", "Steuern"],
    href: "/einstellungen/buchhaltung/steuern",
    keywords: ["steuer", "vorsteuer", "bauabzugsteuer", "35a", "umsatzsteuer"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "buchhaltung-steuern-sollstellung",
    title: "Sollstellungsregeln",
    breadcrumb: [ROOT, "Buchhaltung", "Steuern", "Sollstellungsregeln"],
    href: "/einstellungen/buchhaltung/steuern#receivable-rules-settings-title",
    keywords: ["sollstellung", "hausgeld berechnung", "miete berechnung", "fälligkeit"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "buchhaltung-steuern-schalter",
    title: "Schalter je Mandant",
    breadcrumb: [ROOT, "Buchhaltung", "Steuern", "Schalter je Mandant"],
    href: "/einstellungen/buchhaltung/steuern#tax-switches-title",
    keywords: ["vorsteuer schalten", "bauabzugsteuer schalten", "paragraf 35a"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "buchhaltung-steuern-freigabegrenzen",
    title: "Freigabegrenzen je Rolle",
    breadcrumb: [ROOT, "Buchhaltung", "Steuern", "Freigabegrenzen je Rolle"],
    href: "/einstellungen/buchhaltung/steuern#tax-limits-title",
    keywords: ["freigabegrenze", "limit rolle", "zweite freigabe"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "buchhaltung-steuern-umsatzsteueroption",
    title: "Umsatzsteueroption je Objekt",
    breadcrumb: [ROOT, "Buchhaltung", "Steuern", "Umsatzsteueroption je Objekt"],
    href: "/einstellungen/buchhaltung/steuern#tax-property-title",
    keywords: ["ust option", "optiert", "umsatzsteuer objekt", "revenue key"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "buchhaltung-steuern-reverse-charge",
    title: "Steuerkennzeichen je Lieferant",
    breadcrumb: [ROOT, "Buchhaltung", "Steuern", "Steuerkennzeichen je Lieferant"],
    href: "/einstellungen/buchhaltung/steuern#tax-supplier-title",
    keywords: ["reverse charge", "steuerschuldnerschaft", "lieferant steuer", "leistungsempfänger"],
    permission: ["tenant_settings:read"],
  },

  // --- Objektakte ----------------------------------------------------------------------------
  {
    id: "objektakte",
    title: "Klassifikationsregeln",
    breadcrumb: [ROOT, "Objektakte"],
    href: "/einstellungen/objektakte",
    keywords: ["objektakte", "klassifikation", "regel dokument", "dreistufig", "regelstufe"],
    permission: ["documents:read"],
  },

  // --- Profil ------------------------------------------------------------------------------
  {
    id: "profil",
    title: "Meine Daten",
    breadcrumb: [ROOT, "Profil"],
    href: "/einstellungen/profil",
    keywords: ["profil", "account", "meine daten", "passwort", "sitzung"],
    permission: null,
  },
  {
    id: "profil-passwort",
    title: "Passwort ändern",
    breadcrumb: [ROOT, "Profil", "Passwort ändern"],
    href: "/einstellungen/profil",
    keywords: ["passwort", "kennwort ändern", "passwort wechseln"],
    permission: null,
  },
  {
    id: "profil-2fa",
    title: "Sicherheit, Zweiter Faktor",
    breadcrumb: [ROOT, "Profil", "Zweiter Faktor"],
    href: "/einstellungen/profil#totp-title",
    keywords: ["2fa", "zwei faktor", "authenticator", "totp", "mfa"],
    permission: null,
  },
  {
    id: "profil-sitzungen",
    title: "Aktive Sitzungen",
    breadcrumb: [ROOT, "Profil", "Aktive Sitzungen"],
    href: "/einstellungen/profil",
    keywords: ["sitzung", "session", "abmelden gerät", "aktive anmeldung"],
    permission: null,
  },
  {
    id: "profil-geraete",
    title: "Gemerkte Geräte",
    breadcrumb: [ROOT, "Profil", "Gemerkte Geräte"],
    href: "/einstellungen/profil",
    keywords: ["gerät merken", "trusted device", "gerät vergessen"],
    permission: null,
  },
  {
    id: "profil-signatur",
    title: "E-Mail-Signatur",
    breadcrumb: [ROOT, "Profil", "Signatur"],
    href: "/einstellungen/profil",
    keywords: ["signatur", "unterschrift", "position mail", "e-mail signatur eigene"],
    permission: null,
  },
];

/** Lower cases and folds German umlauts and ß to their ASCII digraphs (ä→ae, ß→ss, ...) so
 *  "Postfächer" and "Postfaecher" or "Straße" and "Strasse" match the same way, whichever
 *  spelling the query and the indexed text happen to use. */
export function normalizeSearchText(value: string): string {
  return value
    .toLowerCase()
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss");
}

function hasPermission(entry: SettingsSearchEntry, permissions: readonly string[]): boolean {
  if (entry.permission === null) return true;
  return entry.permission.some((p) => permissions.includes(p));
}

export type SettingsSearchHit = { entry: SettingsSearchEntry; score: number };

/** Matches title first (weight 3, +1 more when the title starts with the query), then
 *  keywords (weight 2), then the breadcrumb (weight 1); entries the caller has no permission
 *  for are left out entirely. Returns hits best match first, at most `limit`. */
export function searchSettingsIndex(
  query: string,
  permissions: readonly string[],
  index: readonly SettingsSearchEntry[] = settingsSearchIndex,
  limit = 12,
): SettingsSearchHit[] {
  const q = normalizeSearchText(query.trim());
  if (!q) return [];
  const hits: SettingsSearchHit[] = [];
  for (const entry of index) {
    if (!hasPermission(entry, permissions)) continue;
    const title = normalizeSearchText(entry.title);
    let score = 0;
    if (title.includes(q)) score = title.startsWith(q) ? 4 : 3;
    else if (entry.keywords.some((k) => normalizeSearchText(k).includes(q))) score = 2;
    else if (normalizeSearchText(entry.breadcrumb.join(" ")).includes(q)) score = 1;
    if (score > 0) hits.push({ entry, score });
  }
  hits.sort((a, b) => b.score - a.score);
  return hits.slice(0, limit);
}
