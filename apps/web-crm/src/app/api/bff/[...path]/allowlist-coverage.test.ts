// @vitest-environment node
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

const serverFetch = vi.fn();
vi.mock("@/lib/api-server", () => ({ serverFetch: (...args: unknown[]) => serverFetch(...args) }));

import { DELETE, GET, PATCH, POST, PUT } from "./route";

/** Regression check (operator 27.09.2026, "Erledigungsarten konnten nicht geladen werden"):
 *  every `/api/bff/...` call the CRM makes with a resolvable path must be covered by the proxy
 *  allowlist, otherwise the screen breaks with 404 in production. Paths are taken from string
 *  and template literals under `src/`; `${...}` segments count as resolvable only when the
 *  expression is an id (`id`, `fooId`, `x.id`, `foo_id`), which the allowlist matches as UUID.
 *  Literals with other dynamic parts (action names, query builders) and paths handed to local
 *  helpers are skipped here and covered by the explicit cases in route.test.ts. */

const SRC = path.resolve(import.meta.dirname, "../../../..");
const SAMPLE_ID = "01920000-0000-7000-8000-00000000000a";
/** Paperless documents (`dms-documents/{id}`) carry numeric ids. */
const SAMPLE_NUMERIC_ID = "42";
const ID_SLOT = "\u0000id\u0000";
const LITERAL = /(["'`])\/api\/bff\/((?:[^"'`$\\]|\$\{[^{}]*\})*)\1/g;
const ID_EXPR = /(^|[._])id$|Id$|\bid\)?$/;
const HANDLERS = { GET, POST, PUT, PATCH, DELETE } as const;

function listFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...listFiles(full));
    else if (/\.(tsx?)$/.test(entry) && !/\.test\.tsx?$/.test(entry)) out.push(full);
  }
  return out;
}

type Call = { method: keyof typeof HANDLERS; path: string; where: string };

/** Cuts the query at the first `?` outside a `${...}` expression (a ternary inside the
 *  expression is part of the path, e.g. `settlements${save ? "" : "/preview"}`). */
function withoutQuery(raw: string): string {
  let depth = 0;
  for (let i = 0; i < raw.length; i++) {
    if (raw.startsWith("${", i)) depth++;
    else if (raw[i] === "}" && depth > 0) depth--;
    else if (raw[i] === "?" && depth === 0) return raw.slice(0, i);
  }
  return raw;
}

function resolvePath(raw: string): string | null {
  let unresolved = false;
  const resolved = withoutQuery(raw).replace(/\$\{([^{}]*)\}/g, (_, expr: string) => {
    if (ID_EXPR.test(expr.trim())) return ID_SLOT;
    unresolved = true;
    return "";
  });
  if (unresolved || resolved === "" || resolved.endsWith("/")) return null;
  return resolved;
}

async function forwarded(method: keyof typeof HANDLERS, path: string): Promise<boolean> {
  const headers = { host: "crm.localhost", origin: "http://crm.localhost", "content-type": "application/json" };
  const init: RequestInit = { method, headers };
  if (method === "POST" || method === "PUT" || method === "PATCH") init.body = "{}";
  const req = new Request(`http://crm.localhost/api/bff/${path}`, init);
  const res = await HANDLERS[method](req, { params: Promise.resolve({ path: path.split("/") }) });
  return res.status !== 404;
}

/** Only direct `bff(...)` calls and download links are checked; a path handed to a local
 *  helper (`call(path)`, `run(path, "PATCH")`) carries its method elsewhere. */
function isDirectCall(before: string): "bff" | "link" | null {
  if (/\bbff\s*(?:<[^()]*>)?\s*\(\s*$/.test(before)) return "bff";
  if (/(?:\bhref=\{?|\bhref:|window\.open\()\s*$/.test(before)) return "link";
  return null;
}

/** The argument list of the call that starts right after the path literal, up to its closing
 *  parenthesis (strings, template literals and nested brackets are skipped). */
function callTail(tail: string): string {
  let depth = 0;
  let quote: string | null = null;
  for (let i = 0; i < tail.length; i++) {
    const c = tail[i]!;
    if (quote) {
      if (c === "\\") i++;
      else if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") quote = c;
    else if (c === "(" || c === "{" || c === "[") depth++;
    else if (c === "}" || c === "]") depth--;
    else if (c === ")") {
      if (depth === 0) return tail.slice(0, i);
      depth--;
    }
  }
  return tail;
}

function methodAfter(tail: string): keyof typeof HANDLERS | null {
  const args = callTail(tail);
  const match = args.match(/method:\s*["'`](GET|POST|PUT|PATCH|DELETE)["'`]/);
  if (match) return match[1] as keyof typeof HANDLERS;
  return /method:/.test(args) ? null : "GET";
}

/** Resolves module constants such as `const BASE = "/api/bff/accounting/datev"` where they
 *  start a template literal (`${BASE}/exports`) or are passed to `bff(...)` directly, so those
 *  calls are checked too (review 27.09.2026: the DATEV download links were missed). Line
 *  numbers stay the same because the values contain no line breaks. */
function inlineBaseConstants(content: string): string {
  let out = content;
  for (const match of content.matchAll(/\bconst ([A-Za-z_][A-Za-z0-9_]*) = "(\/api\/bff\/[^"]*)";/g)) {
    const [, name, value] = match;
    out = out
      .replace(new RegExp("`\\$\\{" + name + "\\}", "g"), "`" + value)
      .replace(new RegExp("(\\bbff\\s*(?:<[^()]*>)?\\s*\\()\\s*" + name + "\\b", "g"), `$1"${value}"`)
      .replace(new RegExp("(\\bhref=\\{)" + name + "\\}", "g"), `$1"${value}"}`);
  }
  return out;
}

function collectCalls(): Call[] {
  const calls: Call[] = [];
  for (const file of listFiles(SRC)) {
    if (file.includes(`${path.sep}api${path.sep}bff${path.sep}`)) continue;
    const content = inlineBaseConstants(readFileSync(file, "utf8"));
    for (const match of content.matchAll(LITERAL)) {
      const kind = isDirectCall(content.slice(Math.max(0, match.index - 400), match.index));
      if (kind === null) continue;
      const resolved = resolvePath(match[2]!);
      if (resolved === null) continue;
      const method = kind === "link" ? "GET" : methodAfter(content.slice(match.index + match[0].length, match.index + match[0].length + 600));
      if (method === null) continue;
      const line = content.slice(0, match.index).split("\n").length;
      calls.push({ method, path: resolved, where: `${path.relative(SRC, file)}:${line}` });
    }
  }
  return calls;
}

/** GAH-410: the source scan runs once (beforeAll), calls are deduplicated by method and path and
 *  checked in one test per area (first path segment), so no single test needs a longer timeout. */
let scanned: Call[] | null = null;
function scanOnce(): Call[] {
  scanned ??= collectCalls();
  return scanned;
}

function dedupe(calls: Call[]): Call[] {
  const seen = new Map<string, Call>();
  for (const call of calls) {
    const key = `${call.method} ${call.path}`;
    if (!seen.has(key)) seen.set(key, call);
  }
  return [...seen.values()];
}

const area = (call: Call) => call.path.split("/")[0]!;

describe("BFF allowlist coverage", () => {
  let calls: Call[] = [];
  let areas: string[] = [];

  beforeAll(() => {
    calls = dedupe(scanOnce());
    areas = [...new Set(calls.map(area))].sort();
  });

  beforeEach(() => {
    serverFetch.mockReset();
    serverFetch.mockImplementation(async () => new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
  });

  it("finds the calls it is meant to check", () => {
    expect(calls.length).toBeGreaterThan(150);
    expect(calls).toContainEqual(expect.objectContaining({ method: "GET", path: "tickets/resolution-kinds" }));
    expect(calls).toContainEqual(expect.objectContaining({ method: "POST", path: "mail/mail-approval/deputies" }));
    expect(calls).toContainEqual(expect.objectContaining({ method: "GET", path: "accounting/datev/sample-batch" }));
    expect(new Set(calls.map((c) => `${c.method} ${c.path}`)).size).toBe(calls.length);
  });

  it("splits the calls into several areas", () => {
    expect(areas.length).toBeGreaterThan(10);
    expect(areas).toEqual(expect.arrayContaining(["accounting", "banking", "tickets"]));
  });

  it.each([...new Set(collectAreas())].sort())("forwards every resolvable CRM call of area %s instead of answering 404", async (name) => {
    const blocked: string[] = [];
    for (const call of calls.filter((c) => area(c) === name)) {
      const variants = [SAMPLE_ID, SAMPLE_NUMERIC_ID].map((id) => call.path.split(ID_SLOT).join(id));
      let ok = false;
      for (const path of variants) ok = ok || (await forwarded(call.method, path));
      if (!ok) blocked.push(`${call.method} ${variants[0]} (${call.where})`);
    }
    expect(blocked).toEqual([]);
  });
});

/** Test titles need the areas at collection time; the scan result is cached, so the source
 *  files are read only once per file. */
function collectAreas(): string[] {
  return dedupe(scanOnce()).map(area);
}
