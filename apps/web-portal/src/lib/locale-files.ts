import { existsSync, readdirSync } from "node:fs";

import { parseLocales } from "./locale";

/** GB14-01: the language list is the set of files <code>.json in the messages directory
 *  (server and tooling only; the browser gets the list through NEXT_PUBLIC_PORTAL_LOCALES). */
export function discoverLocales(dir: string): readonly string[] {
  if (!existsSync(dir)) return parseLocales("");
  const codes = readdirSync(dir)
    .filter((f) => f.endsWith(".json"))
    .map((f) => f.slice(0, -".json".length))
    .sort();
  return parseLocales(codes.join(","));
}
