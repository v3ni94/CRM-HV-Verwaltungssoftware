import { readFileSync } from "node:fs";
import path from "node:path";

/** Guards the message catalogues of both web apps: de.json and en.json must carry the same
 *  key set (next-intl falls back to the key path and logs an error for a missing message, so
 *  a gap is a silent UI defect), and German texts must not use dashes as sentence punctuation
 *  (CLAUDE.md section 9). Mirror of `scripts/check_i18n.py`. */

const REPO_ROOT = path.resolve(import.meta.dirname, "..", "..", "..", "..");
const APPS = ["web-crm", "web-portal"] as const;
const DASHES = /[–—]/;

type Messages = { [key: string]: string | Messages };

function load(app: string, locale: string): Messages {
  const file = path.join(REPO_ROOT, "apps", app, "messages", `${locale}.json`);
  return JSON.parse(readFileSync(file, "utf8")) as Messages;
}

function flatten(node: Messages, prefix = ""): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(node)) {
    const full = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") out.set(full, value);
    else for (const [k, v] of flatten(value, full)) out.set(k, v);
  }
  return out;
}

describe.each(APPS)("message catalogues of %s", (app) => {
  const de = flatten(load(app, "de"));
  const en = flatten(load(app, "en"));

  it("has the same keys in de.json and en.json", () => {
    const onlyDe = [...de.keys()].filter((k) => !en.has(k)).sort();
    const onlyEn = [...en.keys()].filter((k) => !de.has(k)).sort();
    expect({ onlyDe, onlyEn }).toEqual({ onlyDe: [], onlyEn: [] });
  });

  it("has no empty values", () => {
    const empty = [...de, ...en].filter(([, v]) => v.trim() === "").map(([k]) => k);
    expect(empty).toEqual([]);
  });

  it("uses no dashes as sentence punctuation in de.json", () => {
    const offenders = [...de].filter(([, v]) => DASHES.test(v)).map(([k, v]) => `${k}: ${v}`);
    expect(offenders).toEqual([]);
  });
});
