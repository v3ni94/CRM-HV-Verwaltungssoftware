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

function sourceTexts(roots: string[]): { file: string; text: string }[] {
  const files: string[] = [];
  for (const r of roots) if (fs.existsSync(r)) walk(r, files);
  // The BFF allowlist and the changelog name paths without calling them.
  const notCalls = /(app\/api\/bff\/\[\.\.\.path\]\/route|lib\/changelog)\.ts$/;
  return files.filter((f) => !notCalls.test(f.split(path.sep).join("/"))).map((file) => ({ file, text: fs.readFileSync(file, "utf8") }));
}

const escapeRe = (seg: string) => seg.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Reverse check (GAL-301): allowlisted paths that a non-test source file does call after all. The tail of the
 * path (last two segments, plus the resource segment when the tail starts with a parameter) must appear contiguously, with
 * `${...}` for parameters, delimited by slash, quote or backtick. A single static segment counts as a quoted
 * token, so base constants without slash (`const BASE = "payment-orders"` plus `${BASE}/${id}/approve`) are
 * recognised through their last two segments. Heuristic; flagged entries are reviewed by hand.
 */
export function calledPaths(paths: string[], roots: string[]): string[] {
  const texts = sourceTexts(roots);
  return paths.filter((p) => {
    const segs = p.replace(/^\/api\/v1\/?/, "").split("/").filter(Boolean);
    if (segs.length === 0) return false;
    const isParam = (s: string) => s.startsWith("{");
    const tail = segs.slice(-2);
    // A tail that starts with a parameter needs its resource segment, else `${id}/status` matches any resource.
    if (tail.length === 2 && isParam(tail[0] as string) && segs.length > 2) tail.unshift(segs[segs.length - 3] as string);
    if (tail.every(isParam)) return false;
    const body = tail.map((s) => (isParam(s) ? "(?:\\$\\{[^}]*\\}|\\{[^}]*\\})" : escapeRe(s))).join("/");
    // A lone segment is too ambiguous as a bare quoted token (data-testid etc.): it needs a leading slash.
    const lead = tail.length === 1 ? "/" : "[/\"'`]";
    const re = new RegExp("(?:" + lead + "|^)" + body + "(?:[/\"'`?]|$)", "m");
    // Base constant without slash: `const BASE = "payment-orders"` plus `${BASE}/${id}/approve`.
    const first = tail[0] as string;
    const viaConstant = tail.length > 1 && !isParam(first) && !isParam(tail[tail.length - 1] as string);
    const constRe = viaConstant
      ? new RegExp("(?:^|[/\"'`])\\$\\{[^}]*\\}/" + tail.slice(1).map((s) => (isParam(s) ? "(?:\\$\\{[^}]*\\}|\\{[^}]*\\})" : escapeRe(s))).join("/") + "(?:[/\"'`?]|$)", "m")
      : null;
    const quotedFirst = viaConstant ? new RegExp("[\"'`]" + escapeRe(first) + "[\"'`]") : null;
    return texts.some(({ text }) => re.test(text) || (constRe !== null && quotedFirst !== null && constRe.test(text) && quotedFirst.test(text)));
  });
}
