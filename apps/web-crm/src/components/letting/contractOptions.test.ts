import {
  CONTRACTS_PAGE_SIZE,
  loadTenancyOptions,
  type ContractsPage,
} from "./contractOptions";

function pageOf(
  rows: { id: string; number: string }[],
  total: number | null,
): ContractsPage {
  const headers = new Headers();
  if (total !== null) headers.set("x-total-count", String(total));
  return { data: rows, response: { headers } };
}

function rows(from: number, count: number) {
  return Array.from({ length: count }, (_, i) => ({
    id: `c${String(from + i)}`,
    number: `MV-${String(from + i)}`,
  }));
}

describe("loadTenancyOptions", () => {
  it("loads every page until X-Total-Count is reached and keeps the order", async () => {
    const total = CONTRACTS_PAGE_SIZE * 2 + 5;
    const loadPage = vi.fn(async ({ page }: { page: number }) => {
      const start = (page - 1) * CONTRACTS_PAGE_SIZE;
      return pageOf(
        rows(start, Math.min(CONTRACTS_PAGE_SIZE, total - start)),
        total,
      );
    });
    const options = await loadTenancyOptions(loadPage, "2026-09-26");
    expect(options).toHaveLength(total);
    expect(options[0]).toEqual({ id: "c0", label: "MV-0" });
    expect(options[total - 1]?.id).toBe(`c${String(total - 1)}`);
    expect(loadPage).toHaveBeenCalledTimes(3);
    expect(loadPage.mock.calls[0]?.[0]).toEqual({
      kind: "tenancy",
      active_on: "2026-09-26",
      page: 1,
      page_size: CONTRACTS_PAGE_SIZE,
    });
    expect(loadPage.mock.calls[2]?.[0]).toMatchObject({ page: 3 });
  });

  it("stops after one page when the list is complete", async () => {
    const loadPage = vi.fn(async () => pageOf(rows(0, 12), 12));
    expect(await loadTenancyOptions(loadPage, "2026-09-26")).toHaveLength(12);
    expect(loadPage).toHaveBeenCalledTimes(1);
  });

  it("falls back to the page length without a total header and tolerates a missing body", async () => {
    const loadPage = vi.fn(async ({ page: n }: { page: number }) =>
      n === 1
        ? pageOf(rows(0, CONTRACTS_PAGE_SIZE), null)
        : { data: undefined, response: { headers: new Headers() } },
    );
    expect(await loadTenancyOptions(loadPage, "2026-09-26")).toHaveLength(
      CONTRACTS_PAGE_SIZE,
    );
    expect(loadPage).toHaveBeenCalledTimes(2);
  });
});
