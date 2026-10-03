import { readdirSync, statSync } from "node:fs";
import path from "node:path";

import de from "../../messages/de.json";
import en from "../../messages/en.json";

import { mergeChatContext } from "./chat-context";
import { chatPageContext, ROUTES, SUGGESTIONS, suggestionsFor, type ChatArea } from "./chat-suggestions";
import { settingsSearchIndex } from "./settings-index";

const ID = "01920000-0000-7000-8000-00000000e001";
const ID2 = "01920000-0000-7000-8000-00000000e002";
const APP_DIR = path.resolve(import.meta.dirname, "..", "app", "(app)");

/** Every page.tsx under src/app/(app) as a concrete path (dynamic segments filled with UUIDs). */
function pageRoutes(dir = APP_DIR, prefix = ""): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) {
      const segment = name.startsWith("[") ? (name === "[number]" ? "42" : ID) : name;
      out.push(...pageRoutes(full, `${prefix}/${segment}`));
    } else if (name === "page.tsx") {
      out.push(prefix || "/");
    }
  }
  return out;
}

/** Table of every area and sub area with its expected mapping (route -> context). */
const TABLE: { path: string; area: ChatArea; subArea: string | null; entityType: string | null; contextType?: string }[] = [
  { path: "/start", area: "start", subArea: null, entityType: null },
  { path: "/kontakte", area: "contacts", subArea: null, entityType: null },
  { path: "/kontakte/neu", area: "contacts", subArea: "new", entityType: null },
  { path: `/kontakte/${ID}`, area: "contacts", subArea: "detail", entityType: "contact", contextType: "contact" },
  { path: `/kontakte/${ID}/bearbeiten`, area: "contacts", subArea: "edit", entityType: "contact", contextType: "contact" },
  { path: "/objekte", area: "properties", subArea: null, entityType: null },
  { path: `/objekte/${ID}`, area: "properties", subArea: "detail", entityType: "property", contextType: "property" },
  { path: `/objekte/${ID}/gebaeude/${ID2}`, area: "properties", subArea: "building", entityType: "property", contextType: "property" },
  { path: "/objektakte", area: "objektakte", subArea: null, entityType: null },
  { path: "/weg", area: "hoa", subArea: null, entityType: null },
  { path: `/weg/${ID}`, area: "hoa", subArea: "detail", entityType: "hoa", contextType: "property" },
  { path: `/weg/${ID}/versammlung/${ID2}`, area: "hoa", subArea: "meeting", entityType: "meeting", contextType: "property" },
  { path: `/weg/${ID}/abrechnung/${ID2}`, area: "hoa", subArea: "statement", entityType: "hoa", contextType: "property" },
  { path: `/weg/${ID}/darlehen/${ID2}`, area: "hoa", subArea: "loan", entityType: "hoa" },
  { path: `/weg/${ID}/einsicht`, area: "hoa", subArea: "inspection", entityType: "hoa" },
  { path: `/weg/${ID}/einsicht/${ID2}`, area: "hoa", subArea: "inspection", entityType: "hoa" },
  { path: `/weg/${ID}/massnahme/${ID2}`, area: "hoa", subArea: "measure", entityType: "hoa" },
  { path: `/weg/${ID}/plan/${ID2}`, area: "hoa", subArea: "plan", entityType: "hoa" },
  { path: `/weg/${ID}/pruefung/${ID2}`, area: "hoa", subArea: "audit", entityType: "hoa" },
  { path: `/weg/${ID}/sonderumlage/${ID2}`, area: "hoa", subArea: "levy", entityType: "hoa" },
  { path: `/weg/${ID}/vermoegensbericht`, area: "hoa", subArea: "assetReport", entityType: "hoa" },
  { path: `/weg/${ID}/vermoegensbericht/${ID2}`, area: "hoa", subArea: "assetReport", entityType: "hoa" },
  { path: `/weg/${ID}/versicherung/${ID2}`, area: "hoa", subArea: "insurance", entityType: "hoa" },
  { path: "/vermietung", area: "letting", subArea: null, entityType: null },
  { path: "/vermietung/kautionen", area: "letting", subArea: "deposits", entityType: null },
  { path: `/vermietung/einheit/${ID}`, area: "letting", subArea: "unit", entityType: "unit" },
  { path: `/vermietung/mieterhoehung/${ID}`, area: "letting", subArea: "rentIncrease", entityType: "rent_increase" },
  { path: "/vertraege", area: "contracts", subArea: null, entityType: null },
  { path: "/vertraege/neu", area: "contracts", subArea: "new", entityType: null },
  { path: "/vertraege/freigabe", area: "contracts", subArea: "approval", entityType: null },
  { path: `/vertraege/${ID}`, area: "contracts", subArea: "detail", entityType: "contract" },
  { path: `/vertraege/${ID}/bearbeiten`, area: "contracts", subArea: "edit", entityType: "contract" },
  { path: "/dienstleistervertraege", area: "serviceContracts", subArea: null, entityType: null },
  { path: "/bank", area: "bank", subArea: null, entityType: null },
  { path: "/bank/zahlungen", area: "bank", subArea: "payments", entityType: null },
  { path: "/bank/lastschriften", area: "bank", subArea: "directDebits", entityType: null },
  { path: "/bank/verbindungen", area: "bank", subArea: "connections", entityType: null },
  { path: "/rechnungen", area: "invoices", subArea: null, entityType: null },
  { path: "/rechnungen/belegeingang", area: "invoices", subArea: "intake", entityType: null },
  { path: `/rechnungen/${ID}`, area: "invoices", subArea: "detail", entityType: "invoice" },
  { path: "/buchhaltung", area: "accounting", subArea: null, entityType: null },
  { path: `/buchhaltung/${ID}`, area: "accounting", subArea: "ledger", entityType: "ledger" },
  { path: `/buchhaltung/${ID}/auswertungen`, area: "accounting", subArea: "reports", entityType: "ledger" },
  { path: "/buchhaltung/mahnwesen", area: "accounting", subArea: "dunning", entityType: null },
  { path: `/buchhaltung/mahnwesen/${ID}`, area: "accounting", subArea: "dunning", entityType: "dunning_run" },
  { path: "/buchhaltung/mahnwesen/einstellungen", area: "accounting", subArea: "dunningSettings", entityType: null },
  { path: "/buchhaltung/sollstellungen", area: "accounting", subArea: "receivables", entityType: null },
  { path: "/buchhaltung/eigentuemerabrechnung", area: "accounting", subArea: "ownerStatement", entityType: null },
  { path: "/abrechnung", area: "statements", subArea: null, entityType: null },
  { path: `/abrechnung/${ID}`, area: "statements", subArea: "detail", entityType: "statement" },
  { path: "/tickets", area: "tickets", subArea: null, entityType: null },
  { path: `/tickets/${ID}`, area: "tickets", subArea: "detail", entityType: "ticket", contextType: "global" },
  { path: `/auftraege/${ID}`, area: "orders", subArea: "detail", entityType: "work_order" },
  { path: "/auswertung/tickets", area: "reports", subArea: "tickets", entityType: null },
  { path: "/mail", area: "mail", subArea: null, entityType: null },
  { path: `/mail?message=${ID}`, area: "mail", subArea: null, entityType: "mail" },
  { path: "/mail/playbooks", area: "mail", subArea: "playbooks", entityType: null },
  { path: "/mail/postausgang", area: "mail", subArea: "outbox", entityType: null },
  { path: "/makler", area: "broker", subArea: null, entityType: null },
  { path: "/makler/neu", area: "broker", subArea: "new", entityType: null },
  { path: "/makler/import", area: "broker", subArea: "import", entityType: null },
  { path: `/makler/${ID}`, area: "broker", subArea: "listing", entityType: null },
  { path: "/makler/uebergabe", area: "handover", subArea: null, entityType: null },
  { path: "/makler/uebergabe/neu", area: "handover", subArea: "new", entityType: null },
  { path: `/makler/uebergabe/${ID}`, area: "handover", subArea: "detail", entityType: "handover" },
  { path: "/kalender", area: "calendar", subArea: null, entityType: null },
  { path: `/kalender?termin=${ID}&datum=2026-10-01`, area: "calendar", subArea: null, entityType: "calendar_entry" },
  { path: "/fristen", area: "deadlines", subArea: null, entityType: null },
  { path: "/fristen?kind=contract_end", area: "deadlines", subArea: "contract_end", entityType: null },
  { path: "/dokumente", area: "documents", subArea: null, entityType: null },
  { path: "/dokumente?q=Protokoll", area: "documents", subArea: "search", entityType: null },
  { path: "/dokumente/eingang", area: "documents", subArea: "intakeProposals", entityType: null },
  { path: "/dokumente/loeschvorschlaege", area: "documents", subArea: "deletionProposals", entityType: null },
  { path: "/dokumente/papierkorb", area: "documents", subArea: "trash", entityType: null },
  { path: `/dokumente/${ID}`, area: "documents", subArea: "detail", entityType: "document" },
  { path: "/dms", area: "dms", subArea: null, entityType: null },
  { path: "/dms/suche", area: "dms", subArea: "search", entityType: null },
  { path: "/dms/42", area: "dms", subArea: "document", entityType: null },
  { path: "/einstellungen", area: "settings", subArea: null, entityType: null },
  { path: "/einstellungen/mandant", area: "settings", subArea: "mandant", entityType: null },
  { path: "/einstellungen/buchhaltung/datev", area: "settings", subArea: "buchhaltung-datev", entityType: null },
  { path: "/einstellungen/schnittstellen/messdienstleister", area: "settings", subArea: "messdienstleister", entityType: null },
  { path: "/einstellungen/fachliche-regeln", area: "settings", subArea: "fachliche-regeln", entityType: null },
  { path: "/einstellungen/buchhaltung/periodensperren", area: "settings", subArea: "buchhaltung-periodensperren", entityType: null },
  { path: "/einstellungen/textbausteine", area: "settings", subArea: "textbausteine", entityType: null },
  { path: "/einstellungen/portal-rechtstexte", area: "settings", subArea: "portal-rechtstexte", entityType: null },
  { path: "/importe", area: "imports", subArea: null, entityType: null },
  { path: `/importe/${ID}`, area: "imports", subArea: "detail", entityType: "import_run" },
  { path: "/importe/abgleich", area: "imports", subArea: "reconcile", entityType: null },
  { path: "/importe/immoware24", area: "imports", subArea: "immoware", entityType: null },
  { path: "/importe/immoware24-listen", area: "imports", subArea: "immowareLists", entityType: null },
  { path: "/importe/migration", area: "imports", subArea: "migration", entityType: null },
  { path: "/importe/vollimport", area: "imports", subArea: "full", entityType: null },
  { path: "/immoware", area: "immoware", subArea: null, entityType: null },
  { path: "/immoware/lernphase", area: "immoware", subArea: "learning", entityType: null },
  { path: "/plattform", area: "platform", subArea: null, entityType: null },
  { path: "/plattform/abnahme", area: "platform", subArea: "acceptance", entityType: null },
  { path: "/plattform/freigabe-g5", area: "platform", subArea: "gateG5", entityType: null },
  { path: "/plattform/indexwerte", area: "platform", subArea: "indexValues", entityType: null },
  { path: "/plattform/mietrecht", area: "platform", subArea: "rentLaw", entityType: null },
  { path: "/plattform/onboarding", area: "platform", subArea: "onboarding", entityType: null },
  { path: "/plattform/preisliste", area: "platform", subArea: "priceList", entityType: null },
  { path: "/plattform/uebersicht", area: "platform", subArea: "overview", entityType: null },
  { path: "/assistent", area: "assistant", subArea: null, entityType: null },
  { path: `/assistent/${ID}`, area: "assistant", subArea: "conversation", entityType: null },
  { path: "/hilfe", area: "assistant", subArea: "help", entityType: null },
  { path: "/hilfe/banking", area: "assistant", subArea: "help", entityType: null },
  { path: "/version", area: "other", subArea: "version", entityType: null },
];

describe("chatPageContext", () => {
  it.each(TABLE)("maps $path to $area / $subArea ($entityType)", ({ path: route, area, subArea, entityType, contextType }) => {
    const ctx = chatPageContext(route);
    expect(ctx.area).toBe(area);
    expect(ctx.subArea).toBe(subArea);
    expect(ctx.entityType).toBe(entityType);
    if (entityType) expect(ctx.entityId).toMatch(/^[0-9a-f-]{36}$/);
    else expect(ctx.entityId).toBeNull();
    if (contextType) expect(ctx.contextType).toBe(contextType);
  });

  it("covers every page file of the app (no area falls back to other, except version)", () => {
    const unmapped = pageRoutes().filter((route) => chatPageContext(route).area === "other");
    expect(unmapped).toEqual(["/version"]);
  });

  it("passes the record open on the page and the property of a WEG sub page", () => {
    expect(chatPageContext(`/kontakte/${ID}`)).toMatchObject({ area: "contacts", entityType: "contact", entityId: ID, contextType: "contact", contextId: ID });
    expect(chatPageContext(`/weg/${ID}/versammlung/${ID2}`)).toMatchObject({ entityType: "meeting", entityId: ID2, contextType: "property", contextId: ID });
    expect(chatPageContext(`/objekte/${ID}/gebaeude/${ID2}`)).toMatchObject({ entityType: "property", entityId: ID, contextId: ID });
    expect(chatPageContext("/kalender", `?termin=${ID}`)).toMatchObject({ entityType: "calendar_entry", entityId: ID });
    expect(chatPageContext("/kalender", "?termin=nicht-gültig")).toMatchObject({ entityType: null, entityId: null });
    expect(chatPageContext("/kontakte")).toMatchObject({ entityType: null, entityId: null, subArea: null });
    expect(chatPageContext("/kontakte/")).toMatchObject({ area: "contacts" });
  });

  it("maps settings pages to their settings index entry", () => {
    const ctx = chatPageContext("/einstellungen/mandant");
    expect(ctx.settingsEntry).toEqual({ id: "mandant", title: expect.any(String), href: "/einstellungen/mandant" });
    expect(ctx.subArea).toBe("mandant");
    expect(chatPageContext("/einstellungen").settingsEntry).toBeNull();
    // every settings page file has an index entry
    const pages = pageRoutes().filter((r) => r.startsWith("/einstellungen/"));
    const missing = pages.filter((r) => !settingsSearchIndex.some((e) => e.href.split("#")[0] === r));
    expect(missing).toEqual([]);
  });

  it("lists every route rule once and every rule's area has a label in both languages", () => {
    const paths = ROUTES.map((r) => r.path);
    expect(new Set(paths).size).toBe(paths.length);
    for (const rule of ROUTES) {
      expect((de.AiChat.area as Record<string, string>)[rule.area], rule.area).toBeTruthy();
      expect((en.AiChat.area as Record<string, string>)[rule.area], rule.area).toBeTruthy();
      if (rule.subArea) {
        expect((de.AiChat.subArea as Record<string, string>)[rule.subArea], rule.subArea).toBeTruthy();
        expect((en.AiChat.subArea as Record<string, string>)[rule.subArea], rule.subArea).toBeTruthy();
      }
    }
  });

  it("lets a page override single fields", () => {
    const base = chatPageContext("/bank");
    const merged = mergeChatContext(base, { subArea: "payments", entityType: "contact", entityId: ID });
    expect(merged).toMatchObject({ area: "bank", subArea: "payments", entityType: "contact", entityId: ID, contextType: "contact", contextId: ID });
    expect(mergeChatContext(base, null)).toEqual(base);
  });
});

describe("suggestionsFor", () => {
  it("offers the set of the record, the sub area or the area", () => {
    expect(suggestionsFor(chatPageContext(`/kontakte/${ID}`))).toEqual(SUGGESTIONS.contact);
    expect(suggestionsFor(chatPageContext(`/objekte/${ID}`))).toContain("propertyUnits");
    expect(suggestionsFor(chatPageContext(`/weg/${ID}`))).toEqual(SUGGESTIONS.hoa);
    expect(suggestionsFor(chatPageContext(`/weg/${ID}/abrechnung/${ID2}`))).toEqual(SUGGESTIONS["hoa/statement"]);
    expect(suggestionsFor(chatPageContext(`/weg/${ID}/versammlung/${ID2}`))).toEqual(SUGGESTIONS.meeting);
    expect(suggestionsFor(chatPageContext("/weg"))).toEqual(SUGGESTIONS.hoaList);
    expect(suggestionsFor(chatPageContext(`/makler/uebergabe/${ID}`))).toContain("handoverSignatures");
    expect(suggestionsFor(chatPageContext("/makler/uebergabe"))).toEqual(SUGGESTIONS.handoverList);
    expect(suggestionsFor(chatPageContext(`/tickets/${ID}`))).toContain("ticketReply");
    expect(suggestionsFor(chatPageContext("/mail"))).toContain("mailDraft");
    expect(suggestionsFor(chatPageContext(`/mail?message=${ID}`))).toEqual(SUGGESTIONS.mail);
    expect(suggestionsFor(chatPageContext("/kalender"))).toEqual(["calendarToday", "calendarFreeSlot", "calendarCreate", "handoverThisWeek"]);
    expect(suggestionsFor(chatPageContext("/fristen"))).toEqual(["deadlinesOverdue", "deadlinesWeek", "deadlineCreate"]);
    expect(suggestionsFor(chatPageContext("/bank"))).toEqual(["bankUnmatched", "bankDebtor", "bankOpenItems"]);
    expect(suggestionsFor(chatPageContext("/bank/zahlungen"))).toEqual(SUGGESTIONS["bank/payments"]);
    expect(suggestionsFor(chatPageContext("/buchhaltung"))).toEqual(["accountingOpenItems", "accountingJournal", "accountingExplain"]);
    expect(suggestionsFor(chatPageContext("/dokumente"))).toEqual(["documentFind", "documentSummarize", "documentsForProperty"]);
    expect(suggestionsFor(chatPageContext("/einstellungen/mandant"))).toEqual(["settingsExplain", "settingsWhere", "whereSettings"]);
    expect(suggestionsFor(chatPageContext("/einstellungen/fachliche-regeln"))).toEqual(SUGGESTIONS["settings/fachliche-regeln"]);
    expect(suggestionsFor(chatPageContext("/einstellungen/buchhaltung/periodensperren"))).toContain("periodLocksExplain");
    expect(suggestionsFor(chatPageContext("/einstellungen/textbausteine"))).toContain("textBlocksExplain");
    expect(suggestionsFor(chatPageContext("/einstellungen/portal-rechtstexte"))).toContain("legalTextsExplain");
    expect(suggestionsFor(chatPageContext("/plattform/abnahme"))).toEqual(SUGGESTIONS["platform/acceptance"]);
    expect(suggestionsFor(chatPageContext("/start"))).toEqual(["todayOverview", "calendarToday", "deadlinesWeek", "ticketsOpen"]);
    expect(suggestionsFor(chatPageContext("/vermietung"))).toEqual(["lettingVacancies", "lettingRentIncreases", "lettingProspects"]);
    expect(suggestionsFor(chatPageContext("/version"))).toEqual(SUGGESTIONS["other/version"]);
  });

  it("has a set for every area and every sub area of the route table", () => {
    for (const rule of ROUTES) {
      const ctx = chatPageContext(rule.path.replace(/\{id\}/g, ID).replace("*", "x"));
      const keys = suggestionsFor(ctx);
      expect(keys.length, rule.path).toBeGreaterThan(0);
      expect(keys, rule.path).not.toEqual(SUGGESTIONS.list);
    }
  });

  it("gives every sub page without a record its own set instead of the area set (GAI-421)", () => {
    const missing = ROUTES.filter((r) => r.subArea && !r.entityType && !r.query && r.area !== "settings")
      .filter((r) => !SUGGESTIONS[`${r.area}/${r.subArea}`])
      .map((r) => r.path);
    expect(missing).toEqual([]);
  });

  it("has a German and an English text for every suggestion, without dashes in German", () => {
    const keys = Object.values(SUGGESTIONS).flat();
    for (const key of keys) {
      const text = (de.AiChat.suggestions as Record<string, string>)[key];
      expect(text, key).toBeTruthy();
      expect((en.AiChat.suggestions as Record<string, string>)[key], key).toBeTruthy();
      expect(text).not.toMatch(/[–—]| - /);
    }
    const unused = Object.keys(de.AiChat.suggestions).filter((k) => !keys.includes(k));
    expect(unused).toEqual([]);
  });
});
