// @vitest-environment node
const serverFetch = vi.fn();
vi.mock("@/lib/api-server", () => ({ serverFetch: (...args: unknown[]) => serverFetch(...args) }));

import { PATCH, PUT } from "@/app/api/bff/[...path]/route";

import { BUSINESS_RULES } from "./business-rules";

const ctx = (path: string) => ({ params: Promise.resolve({ path: path.split("/") }) });

/** Every write path of the central page "Fachliche Regeln" must be on the BFF allow list (the
 *  page adds none of its own); the GETs run on the server and need no BFF entry. */
describe("business rules and the BFF allow list", () => {
  beforeEach(() => {
    serverFetch.mockReset();
    serverFetch.mockResolvedValue(new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
  });

  // Rules that address one item build their path from the document: use a sample chart list.
  const sample = [{ id: "01920000-0000-7000-8000-00000000000a", version: 1 }];
  const resolved = BUSINESS_RULES.filter((r) => r.write).map((r) => ({
    method: r.write!.method,
    path: typeof r.write!.path === "function" ? r.write!.path(sample) : r.write!.path,
  }));
  const writes = [...new Map(resolved.map((w) => [`${w.method} ${w.path}`, w])).values()];

  it("has write rules to test", () => {
    expect(writes.length).toBeGreaterThan(10);
  });

  it.each(writes.map((w) => [w.method, w.path] as const))("forwards %s %s", async (method, path) => {
    const req = new Request(`http://crm.localhost/api/bff/${path}`, {
      method,
      headers: { host: "crm.localhost", origin: "http://crm.localhost" },
      body: "{}",
    });
    const res = await (method === "PATCH" ? PATCH : PUT)(req, ctx(path));
    expect(res.status).toBe(200);
    expect(serverFetch.mock.calls[0]![0]).toBe(`/api/v1/${path}`);
  });
});
