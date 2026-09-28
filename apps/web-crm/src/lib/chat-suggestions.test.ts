import de from "../../messages/de.json";
import en from "../../messages/en.json";

import { chatPageContext, SUGGESTIONS, suggestionsFor } from "./chat-suggestions";

const ID = "01920000-0000-7000-8000-00000000e001";

describe("chatPageContext", () => {
  it("passes the record open on the page", () => {
    expect(chatPageContext(`/kontakte/${ID}`)).toMatchObject({ area: "contacts", entityType: "contact", entityId: ID, contextType: "contact", contextId: ID });
    expect(chatPageContext(`/objekte/${ID}`)).toMatchObject({ entityType: "property", contextType: "property" });
    expect(chatPageContext(`/weg/${ID}`)).toMatchObject({ area: "hoa", entityType: "hoa", contextType: "property" });
    expect(chatPageContext(`/tickets/${ID}`)).toMatchObject({ area: "tickets", entityType: "ticket", contextType: "global" });
    expect(chatPageContext(`/vermietung/einheit/${ID}`)).toMatchObject({ area: "letting", entityType: "unit" });
    expect(chatPageContext(`/vertraege/${ID}`)).toMatchObject({ area: "contracts", entityType: "contract" });
    expect(chatPageContext(`/makler/uebergabe/${ID}`)).toMatchObject({ area: "handover", entityType: "handover" });
    expect(chatPageContext("/mail")).toMatchObject({ area: "mail", entityType: null });
    expect(chatPageContext("/kontakte")).toMatchObject({ entityType: null, entityId: null });
    expect(chatPageContext("/start").area).toBe("other");
  });
});

describe("suggestionsFor", () => {
  it("offers the set of the page and the record", () => {
    expect(suggestionsFor(chatPageContext(`/kontakte/${ID}`))).toEqual(["contactOpen", "contactContracts", "contactRecent", "contactCheck"]);
    expect(suggestionsFor(chatPageContext(`/objekte/${ID}`))).toContain("propertyUnits");
    expect(suggestionsFor(chatPageContext(`/weg/${ID}`))).toEqual(["hoaResolutions", "hoaMeetings", "hoaReserve"]);
    expect(suggestionsFor(chatPageContext(`/makler/uebergabe/${ID}`))).toContain("handoverSignatures");
    expect(suggestionsFor(chatPageContext(`/tickets/${ID}`))).toContain("ticketReply");
    expect(suggestionsFor(chatPageContext("/mail"))).toContain("mailDraft");
    expect(suggestionsFor(chatPageContext("/kontakte"))).toEqual(SUGGESTIONS.list);
  });

  it("has a German and an English text for every suggestion, without dashes in German", () => {
    const keys = Object.values(SUGGESTIONS).flat();
    for (const key of keys) {
      const text = (de.AiChat.suggestions as Record<string, string>)[key];
      expect(text, key).toBeTruthy();
      expect((en.AiChat.suggestions as Record<string, string>)[key], key).toBeTruthy();
      expect(text).not.toMatch(/[–—]| - /);
    }
  });
});
