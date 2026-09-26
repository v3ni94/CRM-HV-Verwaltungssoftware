/**
 * Complete list of active tenancies for the rent increase form (performance review
 * 26.09.2026, open item 3): GET /contracts answers at most one page (default 200, page_size up
 * to 1000) and reports the total in X-Total-Count. The select on the letting page needs every
 * active tenancy, so all pages are loaded here, server side, before rendering.
 */

export const CONTRACTS_PAGE_SIZE = 200;
// Upper bound against a runaway loop when the total header is missing or inconsistent.
const MAX_PAGES = 100;

export type ContractOption = { id: string; label: string };

type ContractRow = { id: string; number: string };

/** Result shape of the typed client (`api.GET("/api/v1/contracts", ...)`). */
export type ContractsPage = {
  data?: ContractRow[];
  response: { headers: { get(name: string): string | null } };
};

export type ContractsPageLoader = (query: {
  kind: "tenancy";
  active_on: string;
  page: number;
  page_size: number;
}) => Promise<ContractsPage>;

/** Loads every page of active tenancies on `today` and maps them to select options. */
export async function loadTenancyOptions(
  loadPage: ContractsPageLoader,
  today: string,
): Promise<ContractOption[]> {
  const options: ContractOption[] = [];
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const result = await loadPage({
      kind: "tenancy",
      active_on: today,
      page,
      page_size: CONTRACTS_PAGE_SIZE,
    });
    const rows = result.data ?? [];
    options.push(...rows.map((c) => ({ id: c.id, label: c.number })));
    if (rows.length < CONTRACTS_PAGE_SIZE) break;
    // Without a total header a full page is followed by the next one until a short page.
    const total = Number.parseInt(
      result.response.headers.get("x-total-count") ?? "",
      10,
    );
    if (Number.isFinite(total) && options.length >= total) break;
  }
  return options;
}
