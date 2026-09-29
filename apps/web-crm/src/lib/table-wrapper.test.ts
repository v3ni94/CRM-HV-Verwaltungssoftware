import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

/** Source guard (M31 WP4): no naked `<table` in a component or page. `main` clips horizontal
 *  overflow (`overflow-x-clip`), so a table without a scroll wrapper is cut off silently on a
 *  phone. Every `<table` must be preceded, within the six lines above it, by one of the allowed
 *  wrappers: `overflow-x-auto`, `ui.tableScroll`, `ui.tableCard` or a `ResponsiveList` (whose
 *  `table` prop takes the table). Test files and the worktree folder are skipped. The exception
 *  list is empty; the test also fails when an exception is no longer needed, so it never grows
 *  stale (docs/design/README.md, Handy und Tablet). */

const ROOT = path.resolve(import.meta.dirname, "..");
const WRAPPER = /overflow-x-auto|ui\.tableScroll|ui\.tableCard|ResponsiveList|table=\{/;
const CONTEXT_LINES = 6;
/** Files that may still hold a naked table (relative to src). Empty after the WP3 sweep. */
const EXCEPTIONS: string[] = [];

function listFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === ".claude" || entry === "node_modules") continue;
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...listFiles(full));
    else if (/\.(tsx|jsx)$/.test(entry) && !/\.test\.(tsx|jsx)$/.test(entry)) out.push(full);
  }
  return out;
}

function nakedTables(file: string): number[] {
  const lines = readFileSync(file, "utf8").split("\n");
  const out: number[] = [];
  lines.forEach((line, i) => {
    if (!/<table[\s>]/.test(line) || /^\s*(\*|\/\/|\/\*)/.test(line)) return;
    const above = lines.slice(Math.max(0, i - CONTEXT_LINES), i + 1).join("\n");
    if (!WRAPPER.test(above)) out.push(i + 1);
  });
  return out;
}

describe("every table has a scroll wrapper or a card variant", () => {
  const files = listFiles(ROOT);

  it("finds no naked <table outside the exception list", () => {
    const offenders: string[] = [];
    for (const file of files) {
      const rel = path.relative(ROOT, file);
      if (EXCEPTIONS.includes(rel)) continue;
      for (const line of nakedTables(file)) offenders.push(`${rel}:${line}`);
    }
    expect(offenders, "wrap the table in ui.tableScroll, ui.tableCard, an overflow-x-auto element or a ResponsiveList").toEqual([]);
  });

  it("keeps the exception list minimal", () => {
    const stale = EXCEPTIONS.filter((rel) => {
      const file = path.join(ROOT, rel);
      try {
        return nakedTables(file).length === 0;
      } catch {
        return true;
      }
    });
    expect(stale, "exception no longer needed, remove it").toEqual([]);
  });
});
