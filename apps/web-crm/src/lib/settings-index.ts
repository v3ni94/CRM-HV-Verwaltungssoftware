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

import { BUSINESS_RULES } from "./business-rules";

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

const RULES_PAGE = "/einstellungen/fachliche-regeln";

/** Search title and synonyms of each switch on the page "Fachliche Regeln" (AE39); the anchor is
 *  the id of the rule row, the permission is taken from the rule registry. The five further
 *  acquisition rules share the entry of the first one. */
const RULE_SEARCH: Record<string, [title: string, keywords: string[]]> = {
  "rent-invoice-numbering": ["Nummer für Mietrechnungsentwürfe", ["entwurfsnummer", "rechnungsnummer", "gutschrift", "mietrechnung", "g1", "nummernkreis"]],
  "subledger-exclude-written-off": ["Nebenbuchprüfung, ausgebuchte Posten", ["nebenbuch", "ausgebucht", "storniert", "nebenbuchabgleich", "differenz"]],
  "tax-35a-basis": ["Ausweis haushaltsnaher Leistungen, Rechnungsauswahl", ["35a", "haushaltsnah", "handwerker", "zahlungsdatum", "bezahlt"]],
  "return-fee-pass-on": ["Rücklastschriftgebühr weiterbelasten", ["rücklastschrift", "gebühr", "weiterbelastung", "lastschrift"]],
  "write-off-approval": ["Forderungsausbuchung freigeben", ["ausbuchung", "abschreibung", "uneinbringlich", "verzicht", "vier augen"]],
  "deposit-limit-hint": ["Prüfhinweis Kaution", ["kaution", "kautionshöhe", "raten", "monatsmieten", "prüfhinweis"]],
  "rent-increase-proposals": ["Mieterhöhungsvorschläge aus Staffel und Index", ["mieterhöhung", "staffel", "index", "vorschlag", "entwurf"]],
  "rent-increase-block-mietspiegel": ["Mieterhöhungssperre, Dauer Mietspiegel", ["mieterhöhung", "sperre", "sperrfrist", "mietspiegel"]],
  "rent-increase-block-comparison": ["Mieterhöhungssperre, Dauer Vergleichswohnungen", ["mieterhöhung", "sperre", "sperrfrist", "vergleichswohnungen"]],
  "rent-increase-block-modernization": ["Mieterhöhungssperre, Dauer Modernisierung", ["mieterhöhung", "sperre", "sperrfrist", "modernisierung"]],
  "rent-increase-block-index": ["Mieterhöhungssperre, Dauer Indexmiete", ["mieterhöhung", "sperre", "sperrfrist", "indexmiete"]],
  "rent-increase-block-graduated": ["Mieterhöhungssperre, Dauer Staffelmiete", ["mieterhöhung", "sperre", "sperrfrist", "staffelmiete"]],
  "sale-marketing": ["Verkaufsinserate und Maklerveröffentlichung", ["verkauf", "inserat", "makler", "vermarktung", "anzeige"]],
  "ai-realtime-mail-classification": ["KI-Einordnung je eingehender Ticket-Mail", ["ki", "klassifikation", "einordnung", "antwortvorschlag", "e-mail", "datenschutz"]],
  "ai-master-data-proposals": ["KI-Stammdatenvorschlag aus Ticket-Mails", ["ki", "stammdaten", "adressänderung", "kontakt", "vorschlag"]],
  "ai-automation-ai-task": ["KI-Aufgaben aus Automationsregeln", ["ki", "automation", "regel", "ai_task", "kosten", "budget"]],
  "period-lock-mode": ["Periodensperre, Umfang", ["periodensperre", "sperre", "buchungskreis", "objekt", "zeitraum"]],
  "period-lock-auto": ["Periodensperre beim Abschluss setzen", ["abschluss", "abrechnung", "automatisch sperren"]],
  "period-lock-reopen": ["Periodensperre aufheben zulassen", ["aufhebung", "wieder öffnen", "vier augen"]],
  "chart-four-eyes": ["Kontenrahmen, Freigabe durch zwei Personen", ["kontenrahmen", "vier augen", "freigabe", "zweite person"]],
  "chart-coverage": ["Kontenrahmen, Abrechnungsart und Mehrschlüssel", ["abrechnungsart", "heizung", "mehrschlüssel", "verteilung", "prüfbericht", "konten ohne zuordnung"]],
  "interest-tax": ["Steuerabzug auf Habenzinsen", ["kapitalertragsteuer", "solidaritätszuschlag", "kirchensteuer", "zinsen", "steuerkonten"]],
  "dunning-day-count": ["Verzugszins, Zinstagemethode", ["zinstage", "365", "366", "schaltjahr", "verzugszins", "mahnwesen", "basiszinssatz"]],
  "rule-checkpoints": ["Prüfpunkte Heizkostenverordnung", ["heizkostenv", "nachrüstfrist", "übergangsfrist", "vorfrist", "prüfpunkt"]],
  "advance-open-mode": ["Offene Vorauszahlungen bei Erteilung der Abrechnung", ["vorauszahlung", "vorschuss", "betriebskostenabrechnung", "d24", "verrechnung"]],
  "allocation-basis-block": ["Prüfbericht Umlagegrundlagen blockiert Ausgabe", ["umlagevereinbarung", "umlagefähigkeit", "klausel", "prüfbericht"]],
  "heating-negative-costs": ["Negative Heizkostenanteile verteilen", ["heizkosten", "negativ", "gutschrift", "verteilung", "heizkostenv"]],
  "hoa-remainder-mode": ["Hausgeld, Restcent der Monatsraten", ["hausgeld", "wirtschaftsplan", "monatsrate", "restcent", "rundung"]],
  "check-amounts-tolerance": ["Bruttoprüfung, Toleranz in Cent", ["brutto", "netto", "umsatzsteuer", "toleranz", "cent", "zahlung"]],
  "deadline-policy": ["Abrechnungsfrist, Verhalten nach Ablauf", ["abrechnungsfrist", "556", "nachforderung", "fristende", "ausschlussfrist"]],
  "deadline-watch": ["Abrechnungsfrist, Warnung", ["frist warnung", "benachrichtigung", "fristende"]],
  "deadline-warn-first": ["Abrechnungsfrist, erste Warnung in Tagen", ["warntage", "60 tage"]],
  "deadline-warn-second": ["Abrechnungsfrist, zweite Warnung in Tagen", ["warntage", "30 tage"]],
  "text-blocks": ["Textbausteine mit Freigabe (Fachliche Regeln)", ["textbaustein", "informationsblatt", "35a", "freigabe"]],
  "opening-lock-mode": ["Anfangsbestand der Rücklage, Sperre", ["anfangsbestand", "rücklage", "sperre", "protokolliert", "v01-01"]],
  "reserve-plan-tax": ["Steuerliche Einordnung der Rücklagenzuführung", ["rücklagenplan", "steuerliche einordnung", "platzhalter"]],
  "reserve-payment-mode": ["Zahlungen je Zweckrücklage", ["zweckrücklage", "planverhältnis", "aufteilung", "rücklagenzahlung"]],
  "correction-report": ["Korrekturbericht je Eigentümer", ["korrekturbericht", "abrechnungsversion", "korrektur", "differenz"]],
  "allocation-proposal": ["Zuordnungsvorschlag bei Eigentümerwechsel", ["zuordnungsvorschlag", "eigentümerwechsel", "planübernahme", "abrechnungsergebnis"]],
  "plan-change-mode": ["Unterjährige Planänderung", ["wirtschaftsplan", "differenz", "nachforderung", "gutschrift", "nächste rate", "planänderung"]],
  "acquisition-purchase": ["Zuordnung bei Eigentümerwechsel je Erwerbsart", ["erwerbsart", "eigentümerwechsel", "erbfall", "zwangsversteigerung", "schenkung", "ersterwerb", "kauf", "abrechnungsspitze"]],
  "virtual-meetings": ["Virtuelle Versammlung zulassen", ["virtuelle versammlung", "online", "hybrid", "v13"]],
  "virtual-basis-term-lock": ["Grundlagenbeschluss, Höchstdauer als Sperre", ["drei jahre", "grundlagenbeschluss", "virtuell"]],
  "virtual-basis-transition-date": ["Stichtag der Übergangsregel virtuelle Versammlung", ["übergangsregel", "stichtag", "48"]],
  "online-meeting": ["Online-Versammlung im Portal", ["online teilnahme", "abstimmung portal", "eigentümerversammlung"]],
  "majority-rule-four-eyes": ["Vier-Augen-Freigabe der Mehrheitsregeln", ["mehrheitsregel", "vier augen", "freigabe", "versammlung", "beschluss"]],
  "direct-debit-creator-may-not-approve": ["Lastschrift: Ersteller darf nicht freigeben", ["lastschrift", "sepa", "freigabe", "ersteller", "vier augen"]],
  "portal-circular-resolution": ["Umlaufbeschluss im Eigentümerportal", ["umlaufbeschluss", "umlaufverfahren", "abstimmung portal", "textform"]],
  "proxy-conflict-mode": ["Vollmacht gegen eigene Stimme", ["vollmacht", "stimme", "konflikt", "online abstimmung"]],
  "crm-branding-apply": ["Mandantenfarben im CRM", ["branding", "farben", "white label", "primärfarbe", "akzentfarbe", "corporate design"]],
  "owner-rental-income": ["Mieterträge im Eigentümerportal", ["mieterträge", "kapitalanleger", "sondereigentumsverwaltung", "datenschutz"]],
  "owner-hoa-rental-statements-portal": ["Abrechnungen der Gemeinschaft im Eigentümerportal", ["eigentümerabrechnung", "eigentümerportal", "gemeinschaft", "gemeinschaftseigentum"]],
  "portal-owner-receipts": ["Belegeinsicht im Eigentümerportal", ["belege", "belegeinsicht", "eigentümerportal", "abrechnung"]],
  "owner-rental-statements-portal": ["Eigentümerabrechnung im Eigentümerportal", ["eigentümerabrechnung", "eigentümerportal", "sev", "mietverwaltung"]],
  "tenant-statement-portal": ["Nebenkostenabrechnung im Mieterportal", ["nebenkostenabrechnung", "mieterportal", "betriebskosten", "heizkosten"]],
  "insurance-broker-access": ["Zugriff der Rolle Versicherungsmakler", ["versicherungsmakler", "makler", "schadenfälle", "versicherung", "rolle ohne zugriff"]],
  "onboarding-link-threshold": ["Objektübernahme, Schwelle für automatische Zuordnung", ["übernahme", "personenabgleich", "schwellenwert", "zuordnung", "onboarding"]],
  "onboarding-suggest-threshold": ["Objektübernahme, Schwelle für Vorschläge", ["übernahme", "personenabgleich", "schwellenwert", "vorschlag", "onboarding"]],
  "invoice-intake-auto": ["Belegerfassung aus dem Dokumenteingang", ["belegerfassung", "dokumenteingang", "rechnung", "eingangsvorschlag"]],
  "webhook-auto-disable": ["Webhooks nach Fehlschlägen deaktivieren", ["webhook", "fehlschlag", "deaktivieren", "zustellung"]],
  "objektakte-webhook-timestamp": ["Objektakte-Webhook mit Zeitstempel", ["objektakte", "webhook", "zeitstempel", "replay"]],
  "owner-ticket-scope": ["Tickets im Eigentümerportal", ["ticketumfang", "eigentümer tickets", "objekt tickets"]],
  "meter-photo-mode": ["Foto beim Zählerstand im Portal", ["zählerfoto", "fotopflicht", "zählerstand foto", "ablesung"]],
  "provider-rating-display": ["Bewertungen von Dienstleistern", ["dienstleister bewertung", "rating", "auftragsbewertung"]],
  "terms-version-mode": ["Fassung der Nutzungsbedingungen", ["nutzungsbedingungen", "einwilligungsrichtlinie", "fassung", "nb"]],
  "automation-switch": ["Buchungsautomatik (Schalter)", ["automatik", "auto posting", "bankumsätze", "vier augen", "g1"]],
  "portal-chat-bot": ["Portal-Assistent (Chat-Bot)", ["chat bot", "assistent", "portal fragen", "ki antwort", "dokumente fragen"]],
  "portal-chat-privacy": ["Portal-Assistent, Datenschutzhinweis", ["datenschutz feature", "kenntnisnahme", "chat", "hinweis"]],
  "ebics-enabled": ["EBICS-Anbindung", ["ebics", "kontoauszug abruf", "c53", "teilnehmer", "bankanbindung"]],
  "ebics-signature-key-mode": ["EBICS, Ablage des Signaturschlüssels", ["signaturschlüssel", "extern", "chipkarte", "server schlüssel", "ebics"]],
  "legal-basis-email-delivery": ["Rechtsgrundlage E-Mail-Zustellung", ["einwilligung", "berechtigtes interesse", "vertrag", "dsgvo", "e-mail versand"]],
  "legal-basis-data-sharing": ["Rechtsgrundlage Datenweitergabe", ["einwilligung", "berechtigtes interesse", "weitergabe", "dsgvo"]],
  "legal-basis-marketing": ["Rechtsgrundlage Werbung", ["werbung", "marketing", "einwilligung", "berechtigtes interesse", "widerspruch"]],
  "contact-address-history": ["Adresshistorie der Kontakte", ["adresshistorie", "frühere anschrift", "stichtag", "umzug", "anschrift"]],
  "legal-basis-portal-terms": ["Rechtsgrundlage Nutzungsbedingungen Portal", ["nutzungsbedingungen", "annahme", "einwilligung", "vertrag"]],
  "mfa-crm-mode": ["Zweiter Faktor für CRM-Benutzer", ["totp", "zwei faktor", "2fa", "mfa", "authenticator", "pflicht"]],
  "mfa-portal-required": ["Zweiter Faktor im Portal", ["totp", "portal anmeldung", "2fa", "mfa"]],
  "mfa-admin-reset": ["Zweiten Faktor zurücksetzen (Vier-Augen)", ["2fa zurücksetzen", "mfa reset", "totp verloren", "zweiter faktor"]],
  "access-export-third-party": ["Auskunftsexport, andere Personen", ["auskunft", "art 15", "dsgvo", "dritte", "name oder rolle"]],
  "access-export-internal-notes": ["Auskunftsexport, interne Vermerke", ["auskunft", "interne notizen", "dsgvo", "vermerke"]],
  "access-export-tickets": ["Auskunftsexport, Vorgänge", ["auskunft", "art 15", "tickets", "vorgänge"]],
  "access-export-communication": ["Auskunftsexport, Kommunikation", ["auskunft", "art 15", "nachrichten", "e-mails"]],
  "access-export-documents": ["Auskunftsexport, Dokumentbezüge", ["auskunft", "art 15", "dokumente"]],
  "access-export-portal-account": ["Auskunftsexport, Portalkonto und Anmeldungen", ["auskunft", "art 15", "portalkonto", "anmeldung", "sitzung", "login"]],
  "access-export-payments": ["Auskunftsexport, Zahlungsdaten", ["auskunft", "art 15", "zahlungen", "forderungen", "offene posten"]],
  "access-export-contracts": ["Auskunftsexport, Vertragsdaten", ["auskunft", "art 15", "verträge", "mietvertrag", "laufzeit"]],
  "text-block-second-person": ["Textbausteine, Zweitpersonprüfung", ["textbaustein", "zweite person", "vier augen", "freigabe", "letter_notice"]],
  "document-trash-enabled": ["Dokument-Papierkorb", ["papierkorb", "wiederherstellen", "gelöschte dokumente", "löschfrist"]],
  "document-trash-days": ["Dokument-Papierkorb, Frist in Tagen", ["papierkorb frist", "30 tage", "aufbewahrung gelöscht"]],
  "credit-payable-mode": ["Guthaben aus Abrechnungen, Verbindlichkeitsposten", ["guthaben", "verbindlichkeit", "auszahlung ohne rechnung", "umbuchung", "kreditor", "nebenbuch", "zahlungsauftrag"]],
  "credit-payable-four-eyes": ["Guthaben-Auszahlung, Freigabe durch zwei Personen", ["guthaben", "vier augen", "freigabe", "auszahlung"]],
  "bank-reconciliation-basis": ["Bankabstimmung, Abstimmungsbasis", ["abstimmungsbasis", "buchungsdatum", "bankbuchungstag", "zeitliche differenz", "bankabstimmung"]],
  "bank-clearing-account": ["Bankabstimmung, Klärungskonto", ["klärungskonto", "transitkonto", "überzahlung", "restbetrag", "kontenrahmen"]],
  "g1-checklist": ["G1 Öffnungsliste (Fachliche Regeln)", ["g1", "öffnungsliste", "checkliste", "nachweis"]],
};

const businessRuleEntries: SettingsSearchEntry[] = BUSINESS_RULES.flatMap((rule) => {
  const meta = RULE_SEARCH[rule.id];
  if (!meta) return [];
  const [title, keywords] = meta;
  return [
    {
      id: `fachliche-regeln-${rule.id}`,
      title,
      breadcrumb: [ROOT, "Fachliche Regeln", title],
      href: `${RULES_PAGE}#${rule.id}`,
      keywords: [...keywords, "fachliche regel", "schalter", "entscheidung offen"],
      permission: [...rule.permission],
    },
  ];
});

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
    id: "mandant-gmail-done-sync",
    title: "Erledigt aus Gmail übernehmen",
    breadcrumb: [ROOT, "Mandant und Briefbogen", "Erledigt aus Gmail übernehmen"],
    href: "/einstellungen/mandant#gmail-done-sync-title",
    keywords: ["Gmail", "archiviert", "erledigt", "Rückkanal", "Sammelpostfach", "papierkorb", "wiederherstellen"],
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

  // --- Datenschutz -----------------------------------------------------------------------
  {
    id: "datenschutz",
    title: "Datenschutz",
    breadcrumb: [ROOT, "Datenschutz"],
    href: "/einstellungen/datenschutz",
    keywords: ["dsgvo", "löschprofil", "löschantrag", "verarbeitungsverzeichnis", "auftragsverarbeiter", "avv", "anonymisierung"],
    permission: ["privacy:read"],
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
    id: "lexware-office",
    title: "Lexware Office",
    breadcrumb: [ROOT, "Schnittstellen", "Lexware Office"],
    href: "/einstellungen/schnittstellen/lexware-office",
    keywords: ["lexware", "lexoffice", "rechnung", "rechnungskopie", "rechnungsentwurf", "kontaktabgleich", "avv"],
    permission: ["tenant_settings:read"],
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
    id: "mailquellen",
    title: "Mailquellen",
    breadcrumb: [ROOT, "Schnittstellen", "Mailquellen"],
    href: "/einstellungen/mailquellen",
    keywords: ["mailquelle", "eingangs-webhook", "geheimnis erneuern", "empfangsprotokoll"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "api-schluessel",
    title: "API-Schlüssel",
    breadcrumb: [ROOT, "Schnittstellen", "API-Schlüssel"],
    href: "/einstellungen/api-schluessel",
    keywords: ["api key", "schlüssel widerrufen", "token", "präfix"],
    permission: ["api_keys:read"],
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

  // --- Übernahme-Tickets (V06-01) ----------------------------------------------------------
  {
    id: "uebernahme-tickets",
    title: "Übernahme-Tickets, Standardteam und Zuständiger",
    breadcrumb: [ROOT, "Übernahme-Tickets"],
    href: "/einstellungen/uebernahme-tickets",
    keywords: ["übernahme", "checkliste", "standardteam", "zuständiger", "objektübernahme"],
    permission: ["tenant_settings:read"],
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

  // --- Fristtypen (rule WS-01) ------------------------------------------------------------------
  {
    id: "fristtypen",
    title: "Fristtypen, Auslöser, Dauer und verantwortliche Rolle",
    breadcrumb: [ROOT, "Fristtypen"],
    href: "/einstellungen/fristtypen",
    keywords: ["frist", "fristtyp", "verwalterwechsel", "kautionsabrechnung", "mieterhöhung", "kündigungsfrist", "vorfrist", "dauer"],
    permission: ["tenant_settings:read"],
  },

  // --- Abrechnung (GAF-12) ---------------------------------------------------------------------
  {
    id: "abrechnung-einstellungen",
    title: "Abrechnung, Heizkosten-Regeltabellen und Kostenart je Konto",
    breadcrumb: [ROOT, "Abrechnung"],
    href: "/einstellungen/abrechnung",
    keywords: ["heizkosten", "regeltabelle", "co2 stufen", "gradtage", "kostenart", "betriebskostenart", "kostenkonto", "betrkv"],
    permission: ["accounting:read"],
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

  // --- Teams der Tickets und Tags der Kontakte (Paket Q05) ----------------------------------
  {
    id: "teams",
    title: "Teams",
    breadcrumb: [ROOT, "Teams"],
    href: "/einstellungen/teams",
    keywords: ["team", "teams", "ticketteam", "gruppe", "zuständigkeit", "mitglieder"],
    permission: ["tickets:read"],
  },
  {
    id: "dokumentkategorien",
    title: "Dokumentkategorien",
    breadcrumb: [ROOT, "Dokumentkategorien"],
    href: "/einstellungen/dokumentkategorien",
    keywords: ["dokument", "kategorie", "kategorien", "kategoriebaum", "paperless", "drive", "ordner"],
    permission: ["documents:read"],
  },
  {
    id: "kontakt-tags",
    title: "Kontakt-Tags",
    breadcrumb: [ROOT, "Kontakt-Tags"],
    href: "/einstellungen/kontakt-tags",
    keywords: ["tag", "tags", "schlagwort", "schlagwörter", "kontakte", "umbenennen", "zusammenführen"],
    permission: ["contacts:read"],
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
    id: "dienstleister-portal",
    title: "Dienstleister im Portal",
    breadcrumb: [ROOT, "Dienstleister im Portal"],
    href: "/einstellungen/dienstleister-portal",
    keywords: ["dienstleister", "verfügbarkeit", "zeitfenster", "klassenfreigabe", "unterlagenklasse"],
    permission: ["contacts:update"],
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
    id: "nummernkreise",
    title: "Zustellweg und Nummernkreise",
    breadcrumb: [ROOT, "Zustellweg und Nummernkreise"],
    href: "/einstellungen/nummernkreise",
    keywords: ["nummernkreis", "vertragsnummer", "rechnungsnummer", "zustellweg", "standard versand", "post", "e-mail", "portal"],
    permission: ["tenant_settings:update"],
  },
  {
    id: "regelvorschlaege",
    title: "Regelvorschläge",
    breadcrumb: [ROOT, "Regelvorschläge"],
    href: "/einstellungen/regelvorschlaege",
    keywords: ["regelvorschlag", "vorschlag", "gelernte regel", "automatisierung", "ki regel", "freigabe regel"],
    permission: ["tenant_settings:read"],
  },
  {
    id: "antwortvorlagen",
    title: "Antwortvorlagen",
    breadcrumb: [ROOT, "Antwortvorlagen"],
    href: "/einstellungen/antwortvorlagen",
    keywords: ["antwortvorlage", "textbaustein", "platzhalter", "standardantwort"],
    permission: ["tickets:read"],
  },

  {
    id: "portal-rechtstexte",
    title: "Rechtstexte des Portals",
    breadcrumb: [ROOT, "Rechtstexte des Portals"],
    href: "/einstellungen/portal-rechtstexte",
    keywords: ["impressum", "datenschutzerklärung", "nutzungsbedingungen", "portal", "rechtstext", "white label", "fassung", "einwilligung"],
    permission: ["documents:read"],
  },
  {
    id: "textbausteine",
    title: "Textbausteine",
    breadcrumb: [ROOT, "Textbausteine"],
    href: "/einstellungen/textbausteine",
    keywords: ["textbaustein", "informationsblatt", "35a", "freigabe", "anschreiben"],
    permission: ["documents:read"],
  },
  {
    id: "fachliche-regeln",
    title: "Fachliche Regeln",
    breadcrumb: [ROOT, "Fachliche Regeln"],
    href: RULES_PAGE,
    keywords: ["schalter", "entscheidung offen", "offene fragen", "standard", "varianten", "mandantenschalter", "open_questions", "regel"],
    permission: ["tenant_settings:read", "accounting:read"],
  },
  ...businessRuleEntries,

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
    id: "buchhaltung-automatik",
    title: "Automatikstufen",
    breadcrumb: [ROOT, "Buchhaltung", "Automatikstufen"],
    href: "/einstellungen/buchhaltung/automatik",
    keywords: ["automatik", "automatikstufe", "stufe", "l1", "l2", "ein-klick", "nachkontrolle", "regelautomatik", "bankabgleich"],
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
    id: "buchhaltung-periodensperren",
    title: "Buchhaltung, Periodensperren",
    breadcrumb: [ROOT, "Buchhaltung", "Periodensperren"],
    href: "/einstellungen/buchhaltung/periodensperren",
    keywords: ["periodensperre", "festschreibung", "objekt", "zeitraum", "abschluss abrechnung", "aufhebung"],
    permission: ["accounting:read"],
  },
  {
    id: "buchhaltung-g1-oeffnung",
    title: "Buchhaltung, G1 Öffnung",
    breadcrumb: [ROOT, "Buchhaltung", "G1 Öffnung"],
    href: "/einstellungen/buchhaltung/g1-oeffnung",
    keywords: ["g1", "freigabestufe", "produktive buchführung", "abnahme anhang d", "checkliste öffnung"],
    permission: ["accounting:read"],
  },
  {
    id: "buchhaltung-honorarbuchung",
    title: "Buchhaltung, Honorarbuchung",
    breadcrumb: [ROOT, "Buchhaltung", "Honorarbuchung"],
    href: "/einstellungen/buchhaltung/honorarbuchung",
    keywords: ["honorar konten", "verwalterhonorar buchung", "erlöskonto honorar", "kontenzuordnung honorar", "forderungskonto honorar"],
    permission: ["accounting:read"],
  },
  {
    id: "buchhaltung-glaeubiger-id",
    title: "Buchhaltung, Gläubiger-ID",
    breadcrumb: [ROOT, "Buchhaltung", "Gläubiger-ID"],
    href: "/einstellungen/buchhaltung/glaeubiger-id",
    keywords: ["gläubiger-id", "gläubiger identifikationsnummer", "sepa lastschrift", "creditor id", "lastschrift rechtsträger"],
    permission: ["accounting:read"],
  },
  {
    id: "buchhaltung-rechnungspruefung",
    title: "Buchhaltung, Rechnungsprüfung",
    breadcrumb: [ROOT, "Buchhaltung", "Rechnungsprüfung"],
    href: "/einstellungen/buchhaltung/rechnungspruefung",
    keywords: ["toleranz", "preistoleranz", "mengentoleranz", "sachliche prüfung", "rechnungsprüfung"],
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
    keywords: ["objektakte", "klassifikation", "regel dokument", "dreistufig", "regelstufe", "importlauf", "ocr cache", "vorschaubilder"],
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
    id: "profil-benachrichtigungen",
    title: "Benachrichtigungen",
    breadcrumb: [ROOT, "Profil", "Benachrichtigungen"],
    href: "/einstellungen/benachrichtigungen",
    keywords: ["benachrichtigung", "glocke", "e-mail", "stummschalten", "kanal"],
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
