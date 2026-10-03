import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api-server", () => ({ serverFetch: vi.fn() }));

import { fetchAllListPages, LIST_PAGE_SIZE } from "./list-all";

const ok = (rows: unknown[]) => new Response(JSON.stringify(rows), { status: 200 });

describe("fetchAllListPages", () => {
  it("follows pages of 200 until a short page", async () => {
    const full = Array.from({ length: LIST_PAGE_SIZE }, (_, i) => ({ id: i }));
    const fetcher = vi.fn().mockResolvedValueOnce(ok(full)).mockResolvedValueOnce(ok([{ id: 999 }]));
    const { items } = await fetchAllListPages<{ id: number }>("/api/v1/contracts?kind=ownership", fetcher);
    expect(items).toHaveLength(LIST_PAGE_SIZE + 1);
    expect(fetcher.mock.calls[0]![0]).toBe("/api/v1/contracts?kind=ownership&page=1&page_size=200");
    expect(fetcher.mock.calls[1]![0]).toContain("page=2");
  });

  it("returns null items and the response when the first page fails", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response("", { status: 401 }));
    const { response, items } = await fetchAllListPages("/api/v1/sepa-mandates", fetcher);
    expect(items).toBeNull();
    expect(response.status).toBe(401);
  });

  it("keeps loaded rows when a later page fails", async () => {
    const full = Array.from({ length: LIST_PAGE_SIZE }, (_, i) => i);
    const fetcher = vi.fn().mockResolvedValueOnce(ok(full)).mockResolvedValueOnce(new Response("", { status: 500 }));
    const { items } = await fetchAllListPages<number>("/x", fetcher);
    expect(items).toHaveLength(LIST_PAGE_SIZE);
  });
});
