/**
 * Page context of the chat bubble (rule AI-LOOKUP-01): which page the user is on and which
 * record is open there. Derived from the route only (least invasive: no page has to register
 * anything). The record goes to the API as `context_entity_type` / `context_entity_id`, the
 * platform lookup starts from it, and the suggestions below depend on it.
 */

export type ChatArea =
  | "contacts"
  | "properties"
  | "hoa"
  | "letting"
  | "contracts"
  | "bank"
  | "invoices"
  | "tickets"
  | "mail"
  | "handover"
  | "other";

export type ChatEntityType = "contact" | "property" | "hoa" | "unit" | "contract" | "ticket" | "handover" | "mail";

export type ChatPageContext = {
  area: ChatArea;
  /** Conversation context of the API (`ConversationIn.context_type`). */
  contextType: "global" | "property" | "contact";
  contextId: string | null;
  /** The record open on the page, or null on list pages. */
  entityType: ChatEntityType | null;
  entityId: string | null;
};

const UUID = /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/;

export function chatPageContext(pathname: string): ChatPageContext {
  const id = pathname.match(UUID)?.[0] ?? null;
  const base = { contextType: "global" as const, contextId: null, entityType: null, entityId: null };
  const on = (area: ChatArea, entityType: ChatEntityType | null): ChatPageContext => ({
    ...base,
    area,
    entityType: id ? entityType : null,
    entityId: id && entityType ? id : null,
    contextType: id && (entityType === "contact" || entityType === "property" || entityType === "hoa") ? (entityType === "contact" ? "contact" : "property") : "global",
    contextId: id && (entityType === "contact" || entityType === "property" || entityType === "hoa") ? id : null,
  });
  if (pathname.startsWith("/kontakte")) return on("contacts", "contact");
  if (pathname.startsWith("/objekte")) return on("properties", "property");
  if (pathname.startsWith("/weg")) return on("hoa", "hoa");
  if (pathname.startsWith("/vermietung/einheit")) return on("letting", "unit");
  if (pathname.startsWith("/vermietung")) return on("letting", null);
  if (pathname.startsWith("/vertraege")) return on("contracts", "contract");
  if (pathname.startsWith("/bank")) return on("bank", null);
  if (pathname.startsWith("/rechnungen")) return on("invoices", null);
  if (pathname.startsWith("/tickets")) return on("tickets", "ticket");
  if (pathname.startsWith("/mail")) return { ...base, area: "mail" };
  if (pathname.startsWith("/makler/uebergabe")) return on("handover", "handover");
  return { ...base, area: "other" };
}

/**
 * Suggestion keys per page and record (i18n `AiChat.suggestions.<key>`); each one is a button
 * that sends the prefilled question. Record suggestions only when a record is open.
 */
export const SUGGESTIONS: Record<ChatEntityType | "mail" | "list", string[]> = {
  contact: ["contactOpen", "contactContracts", "contactRecent", "contactCheck"],
  property: ["propertyTickets", "propertyUnits", "propertyOwners", "propertyDocuments", "propertyDeadlines"],
  hoa: ["hoaResolutions", "hoaMeetings", "hoaReserve"],
  unit: ["unitContracts", "unitTickets"],
  contract: ["contractSummary", "contractParties"],
  ticket: ["ticketSummary", "ticketReply", "ticketRelated", "ticketNext"],
  handover: ["handoverSummary", "handoverDefects", "handoverMeters", "handoverSignatures", "handoverPdf"],
  mail: ["mailUnanswered", "mailDraft", "mailTicket"],
  list: ["findContact", "whereSettings"],
};

export function suggestionsFor(ctx: ChatPageContext): string[] {
  if (ctx.entityType) return SUGGESTIONS[ctx.entityType];
  if (ctx.area === "mail") return SUGGESTIONS.mail;
  return SUGGESTIONS.list;
}
