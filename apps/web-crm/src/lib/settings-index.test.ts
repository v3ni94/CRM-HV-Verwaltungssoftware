import { existsSync } from "node:fs";
import path from "node:path";

import { normalizeSearchText, searchSettingsIndex, settingsSearchIndex } from "./settings-index";

const APP_ROOT = path.resolve(import.meta.dirname, "..", "..");

/** Every href (ignoring a `#anchor`) must point at a `page.tsx` that actually exists under
 *  `src/app/(app)/einstellungen`, so the index never sends the search to a dead page. */
describe("settingsSearchIndex", () => {
  it("every href resolves to an existing page.tsx", () => {
    for (const entry of settingsSearchIndex) {
      const routePath = entry.href.split("#")[0]!;
      expect(routePath.startsWith("/einstellungen")).toBe(true);
      const relative = routePath.replace(/^\//, "");
      const file = path.join(APP_ROOT, "src", "app", "(app)", relative, "page.tsx");
      expect(existsSync(file), `${entry.id}: ${file} does not exist`).toBe(true);
    }
  });

  it("has unique ids", () => {
    const ids = settingsSearchIndex.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("every entry keeps Einstellungen as the first breadcrumb level", () => {
    for (const entry of settingsSearchIndex) {
      expect(entry.breadcrumb[0]).toBe("Einstellungen");
    }
  });
});

describe("normalizeSearchText", () => {
  it("folds umlauts and ß to their ASCII digraphs and lower cases", () => {
    expect(normalizeSearchText("Postfächer")).toBe("postfaecher");
    expect(normalizeSearchText("STRASSE")).toBe("strasse");
    expect(normalizeSearchText("Straße")).toBe("strasse");
    expect(normalizeSearchText("Grösse")).toBe("groesse");
  });
});

describe("searchSettingsIndex", () => {
  const allPermissions = [
    "members:read",
    "roles:read",
    "tenant_settings:read",
    "tenant_settings:update",
    "accounting:read",
    "tickets:read",
  ];

  it("returns nothing for an empty query", () => {
    expect(searchSettingsIndex("", allPermissions)).toEqual([]);
    expect(searchSettingsIndex("   ", allPermissions)).toEqual([]);
  });

  it("finds a second level page by title", () => {
    const hits = searchSettingsIndex("Postfächer", allPermissions);
    expect(hits.some((h) => h.entry.id === "postfaecher")).toBe(true);
  });

  it("is tolerant of umlaut spelling and case in both directions", () => {
    const withUmlaut = searchSettingsIndex("postfächer", allPermissions).map((h) => h.entry.id);
    const withoutUmlaut = searchSettingsIndex("POSTFAECHER", allPermissions).map((h) => h.entry.id);
    expect(withUmlaut).toContain("postfaecher");
    expect(withoutUmlaut).toContain("postfaecher");
  });

  it("reaches a third level entry via its keyword synonym", () => {
    // "Buchhaltung > Steuern > Reverse Charge": the visible heading text is "Steuerkennzeichen
    // je Lieferant", found only through the keyword synonym "Reverse Charge".
    const hits = searchSettingsIndex("Reverse Charge", allPermissions);
    expect(hits[0]?.entry.id).toBe("buchhaltung-steuern-reverse-charge");
  });

  it("reaches a third level entry of Postfächer, Vier-Augen-Prinzip", () => {
    const hits = searchSettingsIndex("Vier-Augen", allPermissions);
    expect(hits.some((h) => h.entry.id === "postfaecher-vier-augen")).toBe(true);
  });

  it("reaches Profil, Signatur", () => {
    const hits = searchSettingsIndex("Signatur", ["members:read"]);
    expect(hits.some((h) => h.entry.id === "profil-signatur")).toBe(true);
  });

  it("weighs a title match above a keyword only match", () => {
    // "steuern" is the DATEV/Kontenrahmen breadcrumb group and part of several keywords, but
    // matches the Steuern page title directly, so that page must come out on top.
    const hits = searchSettingsIndex("Steuern", allPermissions);
    expect(hits[0]?.entry.id).toBe("buchhaltung-steuern");
  });

  it("never returns an entry the caller has no permission for", () => {
    const hits = searchSettingsIndex("Postfächer", []);
    expect(hits).toEqual([]);
  });

  it("returns entries gated by either permission of an OR requirement", () => {
    expect(searchSettingsIndex("Automatisierung", ["tickets:read"]).some((h) => h.entry.id === "automatisierung")).toBe(true);
    expect(searchSettingsIndex("Automatisierung", ["tenant_settings:read"]).some((h) => h.entry.id === "automatisierung")).toBe(true);
    expect(searchSettingsIndex("Automatisierung", []).some((h) => h.entry.id === "automatisierung")).toBe(false);
  });

  it("always shows entries without a permission gate", () => {
    expect(searchSettingsIndex("Meine Daten", []).some((h) => h.entry.id === "profil")).toBe(true);
  });

  it("caps results at 12", () => {
    const hits = searchSettingsIndex("Einstellungen", allPermissions);
    expect(hits.length).toBeLessThanOrEqual(12);
  });
});
