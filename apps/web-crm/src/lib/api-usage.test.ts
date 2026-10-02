import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { API_USAGE_ALLOWLIST, API_USAGE_CATEGORIES } from "./api-usage-allowlist";
import { openApiPaths, uncalledPaths } from "./api-usage-scan";

const root = path.resolve(import.meta.dirname, "../../../..");
const openApi = path.join(root, "apps/api/openapi.json");
const roots = [path.join(root, "apps/web-crm/src"), path.join(root, "apps/web-portal/src")];

describe("api usage (GAI-110, uncalled API paths)", () => {
  const uncalled = uncalledPaths(openApi, roots);
  if (process.env.API_USAGE_DUMP) fs.writeFileSync(process.env.API_USAGE_DUMP, JSON.stringify(uncalled, null, 1));
  const allowed = new Set(API_USAGE_ALLOWLIST.map((e) => e.path));

  it("every OpenAPI path is called by the UI or listed in the allowlist", () => {
    const missing = uncalled.filter((p) => !allowed.has(p));
    expect(missing, `Neue API Pfade ohne Aufruf im CRM oder Portal. Anbinden oder mit Kategorie in src/lib/api-usage-allowlist.ts eintragen:\n${missing.join("\n")}`).toEqual([]);
  });

  it("the allowlist only contains paths of the current OpenAPI document", () => {
    const known = new Set(openApiPaths(openApi));
    const stale = API_USAGE_ALLOWLIST.filter((e) => !known.has(e.path)).map((e) => e.path);
    expect(stale).toEqual([]);
  });

  it("uses known categories and no duplicates", () => {
    for (const e of API_USAGE_ALLOWLIST) expect(API_USAGE_CATEGORIES).toContain(e.category);
    expect(allowed.size).toBe(API_USAGE_ALLOWLIST.length);
  });
});
