import { render } from "@testing-library/react";

import { IntlTestProvider } from "@/test/intl";

vi.mock("next-intl/server", async () => {
  const { default: de } = await import("../../../../messages/de.json");
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

describe("HoaPage filters (GAI-110)", () => {
  it("passes management_type and q to the API and offers saved filters of hoa_properties", async () => {
    getMock.mockResolvedValue({ data: { items: [] }, error: undefined, response: new Response("{}", { status: 200 }) });
    const { default: Page } = await import("./page");
    const element = await Page({ searchParams: Promise.resolve({ q: "Linde", art: "hoa_with_sev" }) });
    render(<IntlTestProvider>{element}</IntlTestProvider>);
    expect(getMock).toHaveBeenCalledWith("/api/v1/properties", { params: { query: { page_size: 200, q: "Linde", management_type: "hoa_with_sev" } } });
    await vi.waitFor(() => expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("resource=hoa_properties"))).toBe(true));
  });

  it("ignores an unknown management type", async () => {
    getMock.mockResolvedValue({ data: { items: [] }, error: undefined, response: new Response("{}", { status: 200 }) });
    const { default: Page } = await import("./page");
    await Page({ searchParams: Promise.resolve({ art: "rental" }) });
    expect(getMock).toHaveBeenCalledWith("/api/v1/properties", { params: { query: { page_size: 200 } } });
  });
});
