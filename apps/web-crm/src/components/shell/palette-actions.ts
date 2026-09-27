/**
 * Actions of the command palette (operator decision 27.09.2026, design proposal 1). Each
 * action is a navigation target guarded by a permission; the palette filters by the signed
 * in user's permissions, so the list may name more than a user sees. Labels are i18n keys
 * under `Shell.action`.
 */
export type PaletteAction = {
  id: string;
  /** Key under `Shell.action`. */
  labelKey: string;
  href: string;
  /** Required permission; undefined means visible to everyone. */
  permission?: string;
  /** Free text keywords (lower case) that also match the query. */
  keywords?: string[];
};

export const PALETTE_ACTIONS: PaletteAction[] = [
  { id: "create-ticket", labelKey: "createTicket", href: "/tickets#anlegen", permission: "tickets:create", keywords: ["neu", "vorgang"] },
  { id: "create-contact", labelKey: "createContact", href: "/kontakte/neu", permission: "contacts:create", keywords: ["neu", "person"] },
  { id: "start-dunning", labelKey: "startDunning", href: "/buchhaltung/mahnwesen", permission: "accounting:create", keywords: ["mahnung", "mahnwesen"] },
  // Auswertung Tickets: tenant administrators only (operator 27.09.2026, admin marker
  // tickets:delete per rule M2-07); the platform administrator after a tenant switch holds it too.
  { id: "ticket-analytics", labelKey: "ticketAnalytics", href: "/auswertung/tickets", permission: "tickets:delete", keywords: ["statistik", "bericht"] },

  // Settings pages (operator 27.09.2026, settings search): the same navigation targets as
  // `src/lib/settings-index.ts`, so Strg+K also finds them; one entry per page, gated by the
  // same permission that shows its card on `/einstellungen`. The two pages with no permission
  // gate there (Profil, the Schnittstellen hub) are left out here on purpose so a signed out or
  // permission less session still sees zero actions, as `CommandPalette.test.tsx` expects.
  { id: "settings-benutzer", labelKey: "settingsBenutzer", href: "/einstellungen/benutzer", permission: "members:read", keywords: ["benutzer", "mitarbeiter", "account"] },
  { id: "settings-rollen", labelKey: "settingsRollen", href: "/einstellungen/rollen", permission: "roles:read", keywords: ["rolle", "rechte", "berechtigung"] },
  { id: "settings-mandant", labelKey: "settingsMandant", href: "/einstellungen/mandant", permission: "tenant_settings:read", keywords: ["firma", "mandant", "briefkopf"] },
  { id: "settings-ki", labelKey: "settingsKi", href: "/einstellungen/ki", permission: "tenant_settings:update", keywords: ["ki", "ai", "assistent"] },
  { id: "settings-wissen", labelKey: "settingsWissen", href: "/einstellungen/wissen", permission: "tenant_settings:read", keywords: ["playbook", "wissensdatenbank"] },
  { id: "settings-postfaecher", labelKey: "settingsPostfaecher", href: "/einstellungen/postfaecher", permission: "tenant_settings:update", keywords: ["mail", "email", "gmail", "postfach"] },
  { id: "settings-dms", labelKey: "settingsDms", href: "/einstellungen/dms", permission: "tenant_settings:update", keywords: ["dms", "paperless", "google drive"] },
  { id: "settings-aufbewahrung", labelKey: "settingsAufbewahrung", href: "/einstellungen/aufbewahrung", permission: "tenant_settings:update", keywords: ["aufbewahrungsfrist", "löschung", "retention"] },
  { id: "settings-bank", labelKey: "settingsBank", href: "/einstellungen/bank", permission: "tenant_settings:update", keywords: ["bank", "konto", "finapi", "iban"] },
  { id: "settings-telefonie", labelKey: "settingsTelefonie", href: "/einstellungen/telefonie", permission: "tenant_settings:read", keywords: ["telefon", "anruf"] },
  { id: "settings-messdienstleister", labelKey: "settingsMessdienstleister", href: "/einstellungen/schnittstellen/messdienstleister", permission: "metering_data:read", keywords: ["messdienstleister", "ista", "techem"] },
  { id: "settings-webhooks", labelKey: "settingsWebhooks", href: "/einstellungen/webhooks", permission: "tenant_settings:update", keywords: ["webhook", "ereignis"] },
  { id: "settings-weg", labelKey: "settingsWeg", href: "/einstellungen/weg", permission: "accounting:read", keywords: ["weg", "mehrheitsregel", "beschluss"] },
  { id: "settings-kataloge", labelKey: "settingsKataloge", href: "/einstellungen/kataloge", permission: "properties:read", keywords: ["katalog", "auswahlliste"] },
  { id: "settings-felder", labelKey: "settingsFelder", href: "/einstellungen/felder", permission: "properties:read", keywords: ["feld", "custom field"] },
  { id: "settings-kautionszinsen", labelKey: "settingsKautionszinsen", href: "/einstellungen/kautionszinsen", permission: "contracts:read", keywords: ["kaution", "zinssatz"] },
  { id: "settings-sla", labelKey: "settingsSla", href: "/einstellungen/sla", permission: "sla:read", keywords: ["sla", "bereitschaft"] },
  { id: "settings-ticketvorlagen", labelKey: "settingsTicketvorlagen", href: "/einstellungen/ticketvorlagen", permission: "tickets:read", keywords: ["ticketvorlage", "checkliste"] },
  { id: "settings-portalformulare", labelKey: "settingsPortalformulare", href: "/einstellungen/portalformulare", permission: "tickets:read", keywords: ["portalformular"] },
  { id: "settings-automatisierung", labelKey: "settingsAutomatisierung", href: "/einstellungen/automatisierung", permission: "tickets:read", keywords: ["automatisierung", "regel"] },
  { id: "settings-antwortvorlagen", labelKey: "settingsAntwortvorlagen", href: "/einstellungen/antwortvorlagen", permission: "tickets:read", keywords: ["antwortvorlage", "textbaustein"] },
  { id: "settings-datev", labelKey: "settingsDatev", href: "/einstellungen/buchhaltung/datev", permission: "accounting:read", keywords: ["datev", "kontenzuordnung"] },
  { id: "settings-kontenrahmen", labelKey: "settingsKontenrahmen", href: "/einstellungen/buchhaltung/kontenrahmen", permission: "accounting:read", keywords: ["kontenrahmen"] },
  { id: "settings-steuern", labelKey: "settingsSteuern", href: "/einstellungen/buchhaltung/steuern", permission: "tenant_settings:read", keywords: ["steuer", "vorsteuer"] },
  { id: "settings-immoware", labelKey: "settingsImmoware", href: "/einstellungen/immoware", permission: "immoware:read", keywords: ["immoware", "webdav"] },
  { id: "settings-objektakte", labelKey: "settingsObjektakte", href: "/einstellungen/objektakte", permission: "documents:read", keywords: ["objektakte", "klassifikation"] },
];

export function allowedActions(permissions: readonly string[]): PaletteAction[] {
  return PALETTE_ACTIONS.filter((a) => !a.permission || permissions.includes(a.permission));
}
