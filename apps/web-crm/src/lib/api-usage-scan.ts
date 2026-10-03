import fs from "node:fs";
import path from "node:path";

/** Test helper (GAI-110 area, api-usage): finds OpenAPI paths that no UI source file mentions. */

const norm = (p: string) => p.replace(/\{[^}]*\}/g, "{x}");

function walk(dir: string, out: string[]) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === "test") continue;
      walk(full, out);
    } else if (/\.(ts|tsx)$/.test(entry.name) && !/\.(test|spec)\./.test(entry.name) && entry.name !== "api-usage-allowlist.ts") out.push(full);
  }
}

export function sourceLiterals(roots: string[]): Set<string> {
  const files: string[] = [];
  for (const r of roots) if (fs.existsSync(r)) walk(r, files);
  const literals = new Set<string>();
  const re = /["'`](\/[a-z][^"'`\s]*)["'`]/g;
  for (const file of files) {
    const text = fs.readFileSync(file, "utf8");
    for (const m of text.matchAll(re)) {
      const lit = norm((m[1] ?? "").replace(/\$\{[^}]*\}/g, "{x}")).replace(/[?#].*$/, "");
      literals.add(lit);
      // The proxy /api/bff/<x> forwards to /api/v1/<x>.
      if (lit.startsWith("/api/bff/")) literals.add(lit.replace("/api/bff/", "/api/v1/"));
    }
  }
  return literals;
}

export function openApiPaths(openApiFile: string): string[] {
  return Object.keys(JSON.parse(fs.readFileSync(openApiFile, "utf8")).paths as Record<string, unknown>);
}

/** Paths of the OpenAPI document without any literal match (also without the /api/v1 prefix). */
export function uncalledPaths(openApiFile: string, roots: string[]): string[] {
  const literals = sourceLiterals(roots);
  return openApiPaths(openApiFile).filter((p) => {
    const n = norm(p);
    return !literals.has(n) && !literals.has(n.replace("/api/v1", ""));
  });
}
