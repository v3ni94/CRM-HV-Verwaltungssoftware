import type { ReactElement } from "react";
import { cleanup } from "@testing-library/react";
import { axe } from "vitest-axe";

import { renderIntl } from "@/test/intl";
import { resetRoutes, route, setFallbackRoute } from "@/test/serverPage";

declare global {
  interface ImportMeta {
    glob<T>(pattern: string): Record<string, () => Promise<T>>;
  }
}

vi.mock("@/lib/api-server", async () => (await import("@/test/serverPage")).apiServerMock());
vi.mock("next/navigation", async () => (await import("@/test/serverPage")).navigationMock());
vi.mock("next-intl/server", async () => (await import("@/test/serverPage")).intlServerMock());

/** GAH-304: axe-core over every page under app/(portal) in its locked state (the API answers
 *  403 to every call, so each page renders its title and notice). The content states are
 *  covered by Accessibility.axe.test.tsx on the client components. Client components that
 *  need router or browser APIs are stubbed; the page frame, headings and notices are real. */
const pages = import.meta.glob<{ default: (props: unknown) => Promise<ReactElement> | ReactElement }>("./**/page.tsx");

const PARAMS = { id: "x1", statementId: "s1", contractId: "c1" };
const props = { searchParams: Promise.resolve({}), params: Promise.resolve(PARAMS) };

/** Locked state first (403); pages that raise on a failed call get an empty 200 answer so the
 *  empty state is checked. Redirect and not found have no markup. */
async function renderPage(page: (p: unknown) => Promise<ReactElement> | ReactElement) {
  let last: unknown;
  for (const hit of ANSWERS) {
    resetRoutes();
    for (const [path, body] of Object.entries(ROUTES)) route(path, 200, body);
    setFallbackRoute(hit);
    try {
      return renderIntl(await page(props)).container;
    } catch (error) {
      if (error instanceof Error && /^NEXT_(REDIRECT|NOT_FOUND)/.test(error.message)) return null;
      cleanup();
      last = error;
    }
  }
  throw last;
}

const ROUTES: Record<string, unknown> = {
  "/api/v1/portal/me": { contact_id: "c1", roles: ["tenant"], contracts: [] },
  "/api/v1/portal/notices": [],
};

/** Superset of the empty list shapes the pages read (items, rows, lists). */
const EMPTY = { items: [], texts: {}, note: "", enabled: false, years: [], contracts: [], roles: [], lines: [] };
const ANSWERS = [
  { status: 403, body: { detail: "forbidden" } },
  { status: 200, body: EMPTY },
  { status: 200, body: [] },
];

beforeEach(() => {
  resetRoutes();
  setFallbackRoute({ status: 403, body: { detail: "forbidden" } });
});

/** Detail pages that need a complete record to render (no empty state). Their client
 *  components are covered by Accessibility.axe.test.tsx (HandoverFill) and their own tests. */
const NEEDS_RECORD = new Set(["./pruefung/[id]/page.tsx", "./uebergabe/[id]/page.tsx"]);

describe("axe over all portal pages (locked state)", () => {
  it("finds the pages", () => {
    expect(Object.keys(pages).length).toBeGreaterThanOrEqual(30);
  });

  it.each(Object.keys(pages).filter((f) => !NEEDS_RECORD.has(f)))("%s has no WCAG violations", async (file) => {
    const mod = await pages[file]!();
    const container = await renderPage(mod.default);
    if (!container) return;
    const results = await axe(container, { rules: { region: { enabled: false } } });
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });
});
