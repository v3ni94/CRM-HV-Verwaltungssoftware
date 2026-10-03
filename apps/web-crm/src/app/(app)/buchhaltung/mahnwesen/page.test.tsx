import { render } from "@testing-library/react";

import { IntlTestProvider } from "@/test/intl";

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
const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));
vi.mock("@/lib/api-server", () => ({
  serverApi: () => ({ GET: getMock }),
  redirectIfUnauthenticated: () => undefined,
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
const fetchMock = vi.fn();
beforeEach(() => {
  getMock.mockReset();
  fetchMock.mockReset();
  fetchMock.mockImplementation(() => Promise.resolve(new Response("[]", { status: 200, headers: { "content-type": "application/json" } })));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("DunningPage filters (GAI-110)", () => {
  it("passes status and run_date to the API and offers saved filters of dunning_cases", async () => {
    getMock.mockResolvedValue({ data: [], error: undefined, response: new Response("[]", { status: 200 }) });
    const { default: Page } = await import("./page");
    const element = await Page({ searchParams: Promise.resolve({ status: "approved", run_date: "2026-03-20" }) });
    render(<IntlTestProvider>{element}</IntlTestProvider>);
    expect(getMock).toHaveBeenCalledWith("/api/v1/accounting/dunning-runs", { params: { query: { "filter[status]": "approved", "filter[run_date]": "2026-03-20" } } });
    expect((document.getElementById("run-status") as HTMLSelectElement).value).toBe("approved");
    await vi.waitFor(() => expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("resource=dunning_cases"))).toBe(true));
  });

  it("ignores unknown status and malformed dates", async () => {
    getMock.mockResolvedValue({ data: [], error: undefined, response: new Response("[]", { status: 200 }) });
    const { default: Page } = await import("./page");
    await Page({ searchParams: Promise.resolve({ status: "x", run_date: "morgen" }) });
    expect(getMock).toHaveBeenCalledWith("/api/v1/accounting/dunning-runs", { params: { query: {} } });
  });
});
