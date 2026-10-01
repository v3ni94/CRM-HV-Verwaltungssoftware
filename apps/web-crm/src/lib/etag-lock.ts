/**
 * Optimistic lock for contracts, tickets, documents and incoming invoices (S12-04, Q13).
 *
 * The API answers GET on these records with an ETag and rejects a write with a stale
 * If-Match with 412. The CRM remembers the ETag of the last GET per record and sends it on
 * the locked write (contract notes, ticket and document PATCH, invoice PUT). Any other write
 * below the record (comments, transitions, links) may change the record without returning a
 * new ETag; it drops the remembered value, so the next locked write goes without If-Match
 * (the API treats the header as optional) instead of failing with a false conflict.
 */

const UUID = "[0-9a-fA-F-]{36}";
const ROOTS: RegExp[] = [
  new RegExp(`^/api/bff/contracts/${UUID}`),
  new RegExp(`^/api/bff/tickets/${UUID}`),
  new RegExp(`^/api/bff/documents/${UUID}`),
  new RegExp(`^/api/bff/accounting/invoices/${UUID}`),
];
// Writes that check If-Match, as [method, path pattern].
const LOCKED_WRITES: [string, RegExp][] = [
  ["PATCH", new RegExp(`^/api/bff/contracts/${UUID}/notes$`)],
  ["PATCH", new RegExp(`^/api/bff/tickets/${UUID}$`)],
  ["PATCH", new RegExp(`^/api/bff/documents/${UUID}$`)],
  ["PUT", new RegExp(`^/api/bff/accounting/invoices/${UUID}$`)],
];

const store = new Map<string, string>();

function pathOf(url: string): string {
  return url.split(/[?#]/, 1)[0] ?? url;
}

/** Record root (`/api/bff/tickets/<id>`) of a locked record, or null. */
export function lockRoot(url: string): string | null {
  const path = pathOf(url);
  for (const root of ROOTS) {
    const match = root.exec(path);
    if (match) return match[0];
  }
  return null;
}

function isLockedWrite(method: string, url: string): boolean {
  const path = pathOf(url);
  return LOCKED_WRITES.some(([m, pattern]) => m === method && pattern.test(path));
}

/** If-Match value to send with this request, or null. */
export function ifMatchFor(method: string, url: string): string | null {
  const root = lockRoot(url);
  if (!root || !isLockedWrite(method.toUpperCase(), url)) return null;
  return store.get(root) ?? null;
}

/** Remember or drop the ETag after a response. */
export function rememberEtag(method: string, url: string, ok: boolean, etag: string | null): void {
  const root = lockRoot(url);
  if (!root) return;
  const verb = method.toUpperCase();
  const path = pathOf(url);
  if (verb === "GET") {
    if (ok && etag && path === root) store.set(root, etag);
    return;
  }
  if (ok && etag && isLockedWrite(verb, url)) store.set(root, etag);
  else store.delete(root);
}

/** Test helper. */
export function resetEtags(): void {
  store.clear();
}
