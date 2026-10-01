import { serverFetch } from "@/lib/api-server";

/** Page size limit of `GET /api/v1/properties` (platform `PageSize`, le=200). */
export const PROPERTIES_PAGE_SIZE = 200;
const MAX_PAGES = 25;

type Fetcher = (path: string) => Promise<Response>;

/** Loads every property of the tenant page by page (the API rejects page_size above 200
 *  with 422, operator finding PB-AD08-01). Returns `null` when the first page is not ok so
 *  callers can redirect on 401 like before; later failing pages end the loop with what was
 *  loaded. */
export async function fetchAllProperties<T>(
  fetcher: Fetcher = serverFetch,
): Promise<{ response: Response; items: T[] | null }> {
  const items: T[] = [];
  let first: Response | null = null;
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const response = await fetcher(
      `/api/v1/properties?page=${page}&page_size=${PROPERTIES_PAGE_SIZE}`,
    );
    first ??= response;
    if (!response.ok) {
      if (page === 1) return { response, items: null };
      break;
    }
    const body = (await response.json()) as { items?: T[]; total?: number };
    const chunk = body.items ?? [];
    items.push(...chunk);
    const total = typeof body.total === "number" ? body.total : null;
    if (
      chunk.length < PROPERTIES_PAGE_SIZE ||
      (total !== null && items.length >= total)
    )
      break;
  }
  return { response: first as Response, items };
}
