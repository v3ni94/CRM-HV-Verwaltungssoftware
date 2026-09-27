/** Validation of the `next` target that is carried through the login chain
 *  (middleware, /anmelden, second factor, /mandant). Only same-origin relative paths are
 *  accepted so the parameter can never act as an open redirect. */
const SAFE_NEXT_PATTERN = /^\/[A-Za-z0-9._~/-]*(\?[^#\s]*)?$/;

export const DEFAULT_NEXT = "/start";

export function safeNext(raw: string | null | undefined, fallback = DEFAULT_NEXT): string {
  if (!raw) return fallback;
  const path = raw.split("?", 1)[0] ?? "";
  if (
    !raw.startsWith("/") ||
    raw.startsWith("//") ||
    raw.includes("\\") ||
    path.includes(":") ||
    !SAFE_NEXT_PATTERN.test(raw)
  )
    return fallback;
  return raw;
}

/** Appends a validated `next` to a login step path; the default target is not carried. */
export function withNext(base: string, next: string | null | undefined): string {
  const target = safeNext(next);
  return target === DEFAULT_NEXT ? base : `${base}?next=${encodeURIComponent(target)}`;
}
