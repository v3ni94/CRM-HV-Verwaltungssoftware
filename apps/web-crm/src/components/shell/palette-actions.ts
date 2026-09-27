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
  { id: "ticket-analytics", labelKey: "ticketAnalytics", href: "/auswertung/tickets", permission: "tickets:read", keywords: ["statistik", "bericht"] },
];

export function allowedActions(permissions: readonly string[]): PaletteAction[] {
  return PALETTE_ACTIONS.filter((a) => !a.permission || permissions.includes(a.permission));
}
