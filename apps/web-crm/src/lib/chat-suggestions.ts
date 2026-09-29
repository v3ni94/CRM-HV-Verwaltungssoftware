/**
 * Page context of the chat bubble (rule AI-LOOKUP-01): which menu item, which sub page and
 * which record are open, so the assistant relates to what the user is looking at. Derived
 * from the route and the query string (no page has to register anything); a page that knows
 * better overrides single fields with `useChatContext` (chat-context.ts). The area and sub
 * area go to the API as `area` / `sub_area` (they select the lookup tools of the page), the
 * record as `context_entity_type` / `context_entity_id`; the suggestions below depend on them.
 */

import { settingsSearchIndex, type SettingsSearchEntry } from "./settings-index";

export type ChatArea =
  | "start"
  | "contacts"
  | "properties"
  | "objektakte"
  | "hoa"
  | "letting"
  | "contracts"
  | "serviceContracts"
  | "bank"
  | "invoices"
  | "accounting"
  | "statements"
  | "tickets"
  | "orders"
  | "reports"
  | "mail"
  | "broker"
  | "handover"
  | "calendar"
  | "deadlines"
  | "documents"
  | "dms"
  | "settings"
  | "imports"
  | "immoware"
  | "platform"
  | "assistant"
  | "other";

export type ChatEntityType =
  | "contact"
  | "property"
  | "hoa"
  | "unit"
  | "contract"
  | "ticket"
  | "handover"
  | "mail"
  | "document"
  | "meeting"
  | "rent_increase"
  | "work_order"
  | "calendar_entry"
  | "invoice"
  | "ledger"
  | "statement"
  | "dunning_run"
  | "import_run";

export type ChatPageContext = {
  area: ChatArea;
  /** Sub page of the area (route segment or query, e.g. "meeting", "payments", "search"). */
  subArea: string | null;
  /** Conversation context of the API (`ConversationIn.context_type`). */
  contextType: "global" | "property" | "contact";
  contextId: string | null;
  /** The record open on the page, or null on list pages. */
  entityType: ChatEntityType | null;
  entityId: string | null;
  /** Settings pages: the settings index entry of the open page. */
  settingsEntry: { id: string; title: string; href: string } | null;
};

const UUID = /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/g;
const ONE_UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

type Rule = {
  /** Matched against the pathname; `{id}` stands for a UUID segment. */
  path: string;
  area: ChatArea;
  subArea?: string;
  /** Record type of the page; `entityIndex` says which UUID of the path is its id (default 0). */
  entityType?: ChatEntityType;
  entityIndex?: number;
  /** Which UUID is the property of the conversation context (hoa sub pages). */
  propertyIndex?: number;
  /** Query parameters that refine the context: name -> [subArea, entityType]. */
  query?: Record<string, { subArea?: string; entityType?: ChatEntityType }>;
};

/**
 * Route table, most specific first. Every menu item and sub level of `src/app/(app)` is listed
 * (the vitest in chat-suggestions.test.ts walks the page files and fails on an unmapped one).
 */
export const ROUTES: Rule[] = [
  { path: "/start", area: "start" },
  { path: "/kontakte/neu", area: "contacts", subArea: "new" },
  { path: "/kontakte/{id}/bearbeiten", area: "contacts", subArea: "edit", entityType: "contact" },
  { path: "/kontakte/{id}", area: "contacts", subArea: "detail", entityType: "contact" },
  { path: "/kontakte", area: "contacts" },
  { path: "/objekte/{id}/gebaeude/{id}", area: "properties", subArea: "building", entityType: "property" },
  { path: "/objekte/{id}", area: "properties", subArea: "detail", entityType: "property" },
  { path: "/objekte", area: "properties" },
  { path: "/objektakte", area: "objektakte" },
  { path: "/weg/{id}/versammlung/{id}", area: "hoa", subArea: "meeting", entityType: "meeting", entityIndex: 1, propertyIndex: 0 },
  { path: "/weg/{id}/abrechnung/{id}", area: "hoa", subArea: "statement", entityType: "hoa" },
  { path: "/weg/{id}/darlehen/{id}", area: "hoa", subArea: "loan", entityType: "hoa" },
  { path: "/weg/{id}/einsicht/{id}", area: "hoa", subArea: "inspection", entityType: "hoa" },
  { path: "/weg/{id}/einsicht", area: "hoa", subArea: "inspection", entityType: "hoa" },
  { path: "/weg/{id}/massnahme/{id}", area: "hoa", subArea: "measure", entityType: "hoa" },
  { path: "/weg/{id}/plan/{id}", area: "hoa", subArea: "plan", entityType: "hoa" },
  { path: "/weg/{id}/pruefung/{id}", area: "hoa", subArea: "audit", entityType: "hoa" },
  { path: "/weg/{id}/sonderumlage/{id}", area: "hoa", subArea: "levy", entityType: "hoa" },
  { path: "/weg/{id}/vermoegensbericht/{id}", area: "hoa", subArea: "assetReport", entityType: "hoa" },
  { path: "/weg/{id}/vermoegensbericht", area: "hoa", subArea: "assetReport", entityType: "hoa" },
  { path: "/weg/{id}/versicherung/{id}", area: "hoa", subArea: "insurance", entityType: "hoa" },
  { path: "/weg/{id}", area: "hoa", subArea: "detail", entityType: "hoa" },
  { path: "/weg", area: "hoa" },
  { path: "/vermietung/einheit/{id}", area: "letting", subArea: "unit", entityType: "unit" },
  { path: "/vermietung/mieterhoehung/{id}", area: "letting", subArea: "rentIncrease", entityType: "rent_increase" },
  { path: "/vermietung", area: "letting" },
  { path: "/vertraege/neu", area: "contracts", subArea: "new" },
  { path: "/vertraege/freigabe", area: "contracts", subArea: "approval" },
  { path: "/vertraege/{id}/bearbeiten", area: "contracts", subArea: "edit", entityType: "contract" },
  { path: "/vertraege/{id}", area: "contracts", subArea: "detail", entityType: "contract" },
  { path: "/vertraege", area: "contracts" },
  { path: "/dienstleistervertraege", area: "serviceContracts" },
  { path: "/bank/zahlungen", area: "bank", subArea: "payments" },
  { path: "/bank/lastschriften", area: "bank", subArea: "directDebits" },
  // Bank screens BK-2 (rule UI-BANK-01): reconciliation and bank rules.
  { path: "/bank/abstimmung", area: "bank", subArea: "reconciliation" },
  { path: "/bank/regeln", area: "bank", subArea: "rules" },
  // Nachkontrolle automatischer Buchungen (Regel M12-05).
  { path: "/bank/nachkontrolle", area: "bank", subArea: "review" },
  { path: "/bank", area: "bank" },
  { path: "/rechnungen/belegeingang", area: "invoices", subArea: "intake" },
  { path: "/rechnungen/{id}", area: "invoices", subArea: "detail", entityType: "invoice" },
  { path: "/rechnungen", area: "invoices" },
  { path: "/buchhaltung/mahnwesen/einstellungen", area: "accounting", subArea: "dunningSettings" },
  { path: "/buchhaltung/mahnwesen/{id}", area: "accounting", subArea: "dunning", entityType: "dunning_run" },
  { path: "/buchhaltung/mahnwesen", area: "accounting", subArea: "dunning" },
  { path: "/buchhaltung/sollstellungen", area: "accounting", subArea: "receivables" },
  { path: "/buchhaltung/eigentuemerabrechnung", area: "accounting", subArea: "ownerStatement" },
  { path: "/buchhaltung/{id}/auswertungen", area: "accounting", subArea: "reports", entityType: "ledger" },
  { path: "/buchhaltung/{id}", area: "accounting", subArea: "ledger", entityType: "ledger" },
  { path: "/buchhaltung", area: "accounting" },
  { path: "/abrechnung/{id}", area: "statements", subArea: "detail", entityType: "statement" },
  { path: "/abrechnung", area: "statements" },
  { path: "/tickets/{id}", area: "tickets", subArea: "detail", entityType: "ticket" },
  { path: "/tickets", area: "tickets" },
  { path: "/auftraege/{id}", area: "orders", subArea: "detail", entityType: "work_order" },
  { path: "/auftraege", area: "orders" },
  { path: "/auswertung/tickets", area: "reports", subArea: "tickets" },
  { path: "/auswertung", area: "reports" },
  { path: "/mail/playbooks", area: "mail", subArea: "playbooks" },
  { path: "/mail/postausgang", area: "mail", subArea: "outbox" },
  { path: "/mail", area: "mail", query: { message: { entityType: "mail" } } },
  { path: "/makler/uebergabe/neu", area: "handover", subArea: "new" },
  { path: "/makler/uebergabe/{id}", area: "handover", subArea: "detail", entityType: "handover" },
  { path: "/makler/uebergabe", area: "handover" },
  { path: "/makler/neu", area: "broker", subArea: "new" },
  { path: "/makler/import", area: "broker", subArea: "import" },
  { path: "/makler/{id}", area: "broker", subArea: "listing" },
  { path: "/makler", area: "broker" },
  { path: "/kalender", area: "calendar", query: { termin: { entityType: "calendar_entry" } } },
  { path: "/fristen", area: "deadlines", query: { kind: {} } },
  { path: "/dokumente/loeschvorschlaege", area: "documents", subArea: "deletionProposals" },
  { path: "/dokumente/{id}", area: "documents", subArea: "detail", entityType: "document" },
  { path: "/dokumente", area: "documents", query: { q: { subArea: "search" } } },
  { path: "/dms/suche", area: "dms", subArea: "search" },
  { path: "/dms/*", area: "dms", subArea: "document" },
  { path: "/dms", area: "dms" },
  { path: "/einstellungen/*", area: "settings" },
  { path: "/einstellungen", area: "settings" },
  { path: "/importe/abgleich", area: "imports", subArea: "reconcile" },
  { path: "/importe/immoware24-listen", area: "imports", subArea: "immowareLists" },
  { path: "/importe/immoware24", area: "imports", subArea: "immoware" },
  { path: "/importe/vollimport", area: "imports", subArea: "full" },
  { path: "/importe/{id}", area: "imports", subArea: "detail", entityType: "import_run" },
  { path: "/importe", area: "imports" },
  { path: "/immoware/lernphase", area: "immoware", subArea: "learning" },
  { path: "/immoware", area: "immoware" },
  { path: "/plattform/freigabe-g5", area: "platform", subArea: "gateG5" },
  { path: "/plattform/mietrecht", area: "platform", subArea: "rentLaw" },
  { path: "/plattform/onboarding", area: "platform", subArea: "onboarding" },
  { path: "/plattform/preisliste", area: "platform", subArea: "priceList" },
  { path: "/plattform/uebersicht", area: "platform", subArea: "overview" },
  { path: "/plattform", area: "platform" },
  { path: "/assistent/*", area: "assistant", subArea: "conversation" },
  { path: "/assistent", area: "assistant" },
];

function toRegex(path: string): RegExp {
  const source = path
    .split("/")
    .map((seg) => (seg === "{id}" ? "[0-9a-fA-F-]{36}" : seg === "*" ? "[^/]+(?:/[^/]+)*" : seg.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))
    .join("/");
  return new RegExp(`^${source}/?$`);
}

const COMPILED = ROUTES.map((rule) => ({ rule, regex: toRegex(rule.path) }));

function settingsEntryOf(pathname: string): SettingsSearchEntry | null {
  const clean = pathname.replace(/\/$/, "");
  const candidates = settingsSearchIndex.filter((e) => e.href.split("#")[0] === clean);
  if (!candidates.length) return null;
  // The page itself (shortest breadcrumb) before its sections.
  return candidates.sort((a, b) => a.breadcrumb.length - b.breadcrumb.length)[0] ?? null;
}

function parseQuery(search: string | undefined): URLSearchParams {
  try {
    return new URLSearchParams(search ?? "");
  } catch {
    return new URLSearchParams();
  }
}

export function chatPageContext(pathname: string, search?: string): ChatPageContext {
  const base: ChatPageContext = {
    area: "other",
    subArea: null,
    contextType: "global",
    contextId: null,
    entityType: null,
    entityId: null,
    settingsEntry: null,
  };
  const path = (pathname.split("?")[0] ?? "").replace(/\/+$/, "") || "/";
  const params = parseQuery(search ?? (pathname.includes("?") ? pathname.slice(pathname.indexOf("?")) : ""));
  const found = COMPILED.find(({ regex }) => regex.test(path));
  if (!found) return base;
  const { rule } = found;
  const ids = path.match(UUID) ?? [];
  const ctx: ChatPageContext = { ...base, area: rule.area, subArea: rule.subArea ?? null };
  const id = ids[rule.entityIndex ?? 0] ?? ids[0];
  if (rule.entityType && id) {
    ctx.entityType = rule.entityType;
    ctx.entityId = id;
  }
  for (const [name, refine] of Object.entries(rule.query ?? {})) {
    const value = params.get(name);
    if (!value) continue;
    if (refine.subArea) ctx.subArea = refine.subArea;
    else if (!refine.entityType && !ctx.subArea) ctx.subArea = value.replace(/[^a-zA-Z0-9_]/g, "").slice(0, 40) || null;
    if (refine.entityType && ONE_UUID.test(value)) {
      ctx.entityType = refine.entityType;
      ctx.entityId = value;
    }
  }
  if (rule.area === "settings") {
    const entry = settingsEntryOf(path);
    if (entry) {
      ctx.settingsEntry = { id: entry.id, title: entry.title, href: entry.href };
      ctx.subArea = entry.id;
    }
  }
  const propertyId = rule.propertyIndex !== undefined ? (ids[rule.propertyIndex] ?? null) : null;
  if (ctx.entityType === "contact" && ctx.entityId) {
    ctx.contextType = "contact";
    ctx.contextId = ctx.entityId;
  } else if ((ctx.entityType === "property" || ctx.entityType === "hoa") && ctx.entityId) {
    ctx.contextType = "property";
    ctx.contextId = ctx.entityId;
  } else if (propertyId) {
    ctx.contextType = "property";
    ctx.contextId = propertyId;
  }
  return ctx;
}

/**
 * Suggestion keys per record, sub area and area (i18n `AiChat.suggestions.<key>`); each one is
 * a button that sends the prefilled question. Record suggestions only when a record is open;
 * otherwise the sub area's set, then the area's set, then the generic list set.
 */
export const SUGGESTIONS: Record<string, string[]> = {
  // Records
  contact: ["contactOpen", "contactContracts", "contactRecent", "contactCheck", "calendarForContact"],
  property: ["propertyTickets", "propertyUnits", "propertyOwners", "propertyDocuments", "propertyDeadlines"],
  hoa: ["hoaResolutions", "hoaMeetings", "hoaReserve", "hoaOpenItems"],
  unit: ["unitContracts", "unitTickets", "unitRentIncrease"],
  contract: ["contractSummary", "contractParties", "contractOpenItems"],
  ticket: ["ticketSummary", "ticketReply", "ticketRelated", "ticketNext", "ticketOrders"],
  handover: ["handoverSummary", "handoverDefects", "handoverMeters", "handoverSignatures", "handoverPdf"],
  mail: ["mailSummarize", "mailDraft", "mailTicket"],
  document: ["documentSummarize", "documentWhere", "documentRelated"],
  meeting: ["meetingAgenda", "meetingResolutions", "meetingProtocol"],
  rent_increase: ["rentIncreaseStatus", "rentIncreaseNext", "rentIncreaseLetter"],
  work_order: ["orderStatus", "orderAppointment", "orderTicket"],
  calendar_entry: ["calendarEntryDetails", "calendarEntryMove", "calendarToday"],
  invoice: ["invoiceStatus", "invoiceMatch", "invoiceWhere"],
  ledger: ["ledgerOpenItems", "ledgerJournal", "ledgerExplain"],
  statement: ["statementStatus", "statementExplain", "statementNext"],
  dunning_run: ["dunningRunStatus", "dunningRunItems", "dunningExplain"],
  import_run: ["importRunStatus", "importRunItems", "importUndo"],
  // Areas and sub areas
  start: ["todayOverview", "calendarToday", "deadlinesWeek", "ticketsOpen"],
  contacts: ["findContact", "contactsDuplicates", "contactsNew"],
  "contacts/new": ["contactsNewHelp", "contactsDuplicates"],
  properties: ["findProperty", "propertiesVacancy", "propertiesDeadlines"],
  objektakte: ["objektakteMissing", "objektakteFind"],
  hoaList: ["hoaMeetingsUpcoming", "hoaResolutionsOpen", "hoaReserveWhich"],
  "hoa/meeting": ["meetingAgenda", "meetingResolutions", "meetingProtocol"],
  "hoa/statement": ["hoaStatementStatus", "hoaStatementExplain", "hoaReserve"],
  "hoa/assetReport": ["hoaAssetReport", "hoaReserve"],
  letting: ["lettingVacancies", "lettingRentIncreases", "lettingProspects"],
  "letting/rentIncrease": ["rentIncreaseStatus", "rentIncreaseNext", "rentIncreaseLetter"],
  contracts: ["findContract", "contractsEnding", "contractsApproval"],
  "contracts/approval": ["contractsApproval", "findContract"],
  serviceContracts: ["serviceContractsNotice", "serviceContractsFind"],
  bank: ["bankUnmatched", "bankDebtor", "bankOpenItems"],
  "bank/payments": ["bankPaymentsOpen", "bankUnmatched"],
  "bank/directDebits": ["bankDirectDebitsNext", "bankOpenItems"],
  "bank/reconciliation": ["bankUnmatched", "bankOpenItems"],
  "bank/rules": ["bankUnmatched", "bankDebtor"],
  invoices: ["invoicesOpen", "invoicesFind", "invoicesIntake"],
  "invoices/intake": ["invoicesIntake", "invoicesOpen"],
  accounting: ["accountingOpenItems", "accountingJournal", "accountingExplain"],
  "accounting/dunning": ["dunningOverdue", "dunningExplain", "accountingOpenItems"],
  "accounting/receivables": ["receivablesDue", "accountingOpenItems"],
  statements: ["statementsOpen", "statementExplain"],
  tickets: ["ticketsOpen", "ticketsOverdue", "ticketsCreate"],
  orders: ["ordersOpen", "orderStatus"],
  reports: ["reportsExplain", "ticketsOverdue"],
  mailList: ["mailUnanswered", "mailDraft", "mailTicket"],
  "mail/outbox": ["mailOutboxPending", "mailUnanswered"],
  "mail/playbooks": ["mailPlaybooksExplain", "whereSettings"],
  broker: ["brokerListings", "brokerProspects"],
  handoverList: ["handoverThisWeek", "handoverCreate"],
  calendar: ["calendarToday", "calendarFreeSlot", "calendarCreate", "handoverThisWeek"],
  deadlines: ["deadlinesOverdue", "deadlinesWeek", "deadlineCreate"],
  documents: ["documentFind", "documentSummarize", "documentsForProperty"],
  "documents/search": ["documentFind", "documentSummarize"],
  dms: ["dmsFind", "dmsExplain"],
  settings: ["settingsExplain", "settingsWhere", "whereSettings"],
  imports: ["importsStatus", "importsHow"],
  immoware: ["immowareStatus", "immowareExplain"],
  platform: ["platformExplain", "whereSettings"],
  assistant: ["assistantHow", "findContact"],
  list: ["findContact", "whereSettings"],
};

/** Areas whose list page uses a set named differently from a record of the same name. */
const LIST_SET: Partial<Record<ChatArea, string>> = { hoa: "hoaList", mail: "mailList", handover: "handoverList" };

export function suggestionsFor(ctx: ChatPageContext): string[] {
  const generic = SUGGESTIONS.list ?? [];
  const sub = ctx.subArea ? SUGGESTIONS[`${ctx.area}/${ctx.subArea}`] : undefined;
  const record = ctx.entityType ? SUGGESTIONS[ctx.entityType] : undefined;
  if (record) return sub && ctx.entityType === "hoa" ? sub : record;
  if (sub) return sub;
  const listKey = LIST_SET[ctx.area] ?? ctx.area;
  return SUGGESTIONS[listKey] ?? generic;
}
