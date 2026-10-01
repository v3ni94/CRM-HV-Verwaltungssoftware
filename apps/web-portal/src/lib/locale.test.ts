import { readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import de from "../../messages/de.json";
import en from "../../messages/en.json";

import { SUPPORTED_LOCALES, resolveLocale } from "./locale";

function keys(node: unknown, prefix = ""): string[] {
  if (node === null || typeof node !== "object") return [prefix];
  return Object.entries(node as Record<string, unknown>).flatMap(([k, v]) => keys(v, prefix ? `${prefix}.${k}` : k));
}

describe("resolveLocale (GA11-01)", () => {
  it("prefers the stored cookie", () => {
    expect(resolveLocale("en", "de-DE,de;q=0.9")).toBe("en");
  });
  it("ignores an unknown cookie and uses Accept-Language by quality", () => {
    expect(resolveLocale("xx", "fr;q=0.9,en;q=0.8,de;q=0.1")).toBe("en");
    expect(resolveLocale(undefined, "en-GB,en;q=0.9")).toBe("en");
  });
  it("falls back to German", () => {
    expect(resolveLocale(undefined, null)).toBe("de");
    expect(resolveLocale(undefined, "fr-FR,it;q=0.8")).toBe("de");
  });
});

describe("message files", () => {
  it("has a file for every supported language and no file without registration", () => {
    const files = readdirSync(join(__dirname, "../../messages"))
      .filter((f) => f.endsWith(".json"))
      .map((f) => f.replace(".json", ""))
      .sort();
    expect(files).toEqual([...SUPPORTED_LOCALES].sort());
  });
  it("en has exactly the keys of de", () => {
    expect(keys(en).sort()).toEqual(keys(de).sort());
  });
});
