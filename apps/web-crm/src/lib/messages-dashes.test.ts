// @vitest-environment node
import { readFileSync } from "node:fs";
import path from "node:path";

/** GAH-417: German UI texts use no dashes as sentence punctuation (CLAUDE.md section 9).
 *  Hyphens inside words (Soll-Ist) stay allowed; a spaced hyphen, any en dash or em dash fails. */
const APPS = path.resolve(import.meta.dirname, "../../..");
const DASH = /\s-\s|[–—]/;

function strings(value: unknown, prefix: string, out: Array<[string, string]>): Array<[string, string]> {
  if (typeof value === "string") out.push([prefix, value]);
  else if (Array.isArray(value)) value.forEach((v, i) => strings(v, `${prefix}[${i}]`, out));
  else if (value && typeof value === "object") {
    for (const [k, v] of Object.entries(value)) strings(v, prefix ? `${prefix}.${k}` : k, out);
  }
  return out;
}

describe("German message files contain no dashes as punctuation", () => {
  it.each(["web-crm", "web-portal"])("%s/messages/de.json", (app) => {
    const data = JSON.parse(readFileSync(path.join(APPS, app, "messages/de.json"), "utf8"));
    const all = strings(data, "", []);
    expect(all.length).toBeGreaterThan(100);
    expect(all.filter(([, text]) => DASH.test(text)).map(([key, text]) => `${key}: ${text}`)).toEqual([]);
  });

  it("detects the forbidden patterns", () => {
    expect(DASH.test("Hausgeld - Abrechnung")).toBe(true);
    expect(DASH.test("Hausgeld – Abrechnung")).toBe(true);
    expect(DASH.test("Hausgeld—Abrechnung")).toBe(true);
    expect(DASH.test("Soll-Ist-Vergleich")).toBe(false);
  });
});
