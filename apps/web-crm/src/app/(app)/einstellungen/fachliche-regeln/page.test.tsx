import { render, screen, within } from "@testing-library/react";

import { IntlTestProvider } from "@/test/intl";

// Renders the server component /einstellungen/fachliche-regeln end to end with a mocked API.
vi.mock("next-intl/server", async () => {
  const { default: de } = await import("../../../../../messages/de.json");
  return {
    getTranslations: async (namespace: string) => (key: string, values: Record<string, unknown> = {}) => {
      const raw = `${namespace}.${key}`.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], de);
      if (typeof raw !== "string") throw new Error(`INSUFFICIENT_PATH ${namespace}.${key}`);
      return raw.replace(/\{(\w+)\}/g, (_, name: string) => String(values[name] ?? ""));
    },
  };
});
const { notFound } = vi.hoisted(() => ({
  notFound: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));
vi.mock("next/navigation", () => ({ notFound, useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
const { serverFetch, permissions } = vi.hoisted(() => ({ serverFetch: vi.fn(), permissions: { list: [] as string[] } }));
vi.mock("@/lib/api-server", () => ({
  serverFetch: (...args: unknown[]) => serverFetch(...args),
  redirectIfUnauthenticated: () => undefined,
  serverApi: () => ({ GET: vi.fn() }),
}));
vi.mock("@/lib/me", () => ({
  getMe: async () => ({ data: { user_id: "u1", permissions: permissions.list }, error: undefined, response: new Response("{}") }),
}));
vi.mock("@/lib/bff", () => ({ bff: async () => ({ ok: false, message: "offline" }) }));

import BusinessRulesPage from "./page";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

describe("Fachliche Regeln page", () => {
  beforeEach(() => {
    serverFetch.mockReset();
    notFound.mockClear();
  });

  it("reads each endpoint once, shows the values and marks an unreadable endpoint", async () => {
    permissions.list = ["tenant_settings:read", "tenant_settings:update", "accounting:read"];
    serverFetch.mockImplementation(async (path: string) => {
      if (path === "/api/v1/hoa/plan-change-settings") return json({ mode: "due_now" });
      if (path === "/api/v1/hoa/reserve-policy") return json({ opening_lock_mode: "locked" });
      if (path === "/api/v1/billing/advance-rule") return json({ detail: "forbidden" }, 403);
      return json({});
    });
    render(<IntlTestProvider>{await BusinessRulesPage()}</IntlTestProvider>);
    expect(screen.getByRole("heading", { name: "Fachliche Regeln", level: 1 })).toBeInTheDocument();
    const paths = serverFetch.mock.calls.map((c) => c[0] as string);
    expect(new Set(paths).size).toBe(paths.length);
    expect(paths).toContain("/api/v1/billing/deadline-settings");
    expect(paths.every((p) => p.startsWith("/api/v1/"))).toBe(true);
    // a rule needing contracts:read is not even requested
    expect(paths).not.toContain("/api/v1/accounting/rent-invoices/numbering-mode");
    const plan = within(document.getElementById("plan-change-mode")!);
    expect(plan.getByTestId("current-plan-change-mode")).toHaveTextContent("Differenz sofort fällig");
    expect(plan.getByText("Entscheidung offen")).toBeInTheDocument();
    expect(plan.getByText("M12-L2, P07-01")).toBeInTheDocument();
    expect(within(document.getElementById("advance-open-mode")!).getByTestId("current-advance-open-mode")).toHaveTextContent("nicht lesbar");
  });

  it("answers 404 without a permission that shows any rule", async () => {
    permissions.list = ["tickets:update"];
    await expect(BusinessRulesPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalled();
    expect(serverFetch).not.toHaveBeenCalled();
  });
});
