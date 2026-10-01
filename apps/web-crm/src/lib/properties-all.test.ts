import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api-server", () => ({ serverFetch: vi.fn() }));

import { fetchAllProperties, PROPERTIES_PAGE_SIZE } from "./properties-all";

function page(items: unknown[], total: number, ok = true): Response {
  return new Response(ok ? JSON.stringify({ items, total }) : "", {
    status: ok ? 200 : 401,
  });
}

describe("fetchAllProperties", () => {
  it("walks all pages with the API page size limit", async () => {
    const calls: string[] = [];
    const first = Array.from({ length: PROPERTIES_PAGE_SIZE }, (_, i) => ({
      id: `a${i}`,
    }));
    const fetcher = vi.fn(async (path: string) => {
      calls.push(path);
      return calls.length === 1
        ? page(first, 203)
        : page([{ id: "b1" }, { id: "b2" }, { id: "b3" }], 203);
    });
    const result = await fetchAllProperties<{ id: string }>(fetcher);
    expect(result.items).toHaveLength(203);
    expect(calls).toEqual([
      `/api/v1/properties?page=1&page_size=${PROPERTIES_PAGE_SIZE}`,
      `/api/v1/properties?page=2&page_size=${PROPERTIES_PAGE_SIZE}`,
    ]);
    expect(calls.some((c) => c.includes("page_size=500"))).toBe(false);
  });

  it("stops after one short page and returns null items on a failed first page", async () => {
    const one = vi.fn(async () => page([{ id: "x" }], 1));
    expect((await fetchAllProperties(one)).items).toEqual([{ id: "x" }]);
    expect(one).toHaveBeenCalledTimes(1);
    const failed = vi.fn(async () => page([], 0, false));
    const result = await fetchAllProperties(failed);
    expect(result.items).toBeNull();
    expect(result.response.status).toBe(401);
  });
});
