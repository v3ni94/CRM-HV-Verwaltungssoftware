import { serverFetch } from "@/lib/api-server";

/** Page size limit of every API list (section 12, GAK-301). */
export const LIST_PAGE_SIZE = 200;
const MAX_PAGES = 50;

type Fetcher = (path: string) => Promise<Response>;

/** Loads a list that answers with a plain JSON array page by page (`page`, `page_size`).
 *  The first response is returned so callers can redirect on 401; `items` is null when the
 *  first page failed, later failing pages end the loop with what was loaded. */
export async function fetchAllListPages<T>(
  path: string,
  fetcher: Fetcher = serverFetch,
): Promise<{ response: Response; items: T[] | null }> {
  const sep = path.includes("?") ? "&" : "?";
  const items: T[] = [];
  let first: Response | null = null;
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const response = await fetcher(`${path}${sep}page=${page}&page_size=${LIST_PAGE_SIZE}`);
    first ??= response;
    if (!response.ok) {
      if (page === 1) return { response, items: null };
      break;
    }
    const chunk = (await response.json()) as T[];
    items.push(...chunk);
    if (chunk.length < LIST_PAGE_SIZE) break;
  }
  return { response: first as Response, items };
}
