/** A77: filter parameters of the audit room. Only these keys reach the API; everything else in
 *  the page query is dropped, values are trimmed and empty values omitted. */
export const AUDIT_FILTER_KEYS = ["account_id", "vendor_contact_id", "date_from", "date_to", "q"] as const;

export type AuditFilterKey = (typeof AUDIT_FILTER_KEYS)[number];

export function filterQuery(params: Partial<Record<AuditFilterKey, string | string[] | null | undefined>>): string {
  const search = new URLSearchParams();
  for (const key of AUDIT_FILTER_KEYS) {
    const value = params[key];
    const first = Array.isArray(value) ? value[0] : value;
    if (first && first.trim().length > 0) search.set(key, first.trim());
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}
