/**
 * CSRF protection of mutating BFF route handlers: SameSite=Strict cookies plus a strict
 * same-origin check of the Origin header.
 */
import { problemJson } from "./problem";

export function originAllowed(request: Request): boolean {
  const origin = request.headers.get("origin");
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  if (!origin || !host) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

/** Returns a 403 problem response when the Origin check fails, otherwise null. */
export function rejectForeignOrigin(request: Request): Response | null {
  if (originAllowed(request)) return null;
  return problemJson(403, "Anfrage abgelehnt", "Die Anfrage stammt nicht von dieser Anwendung.");
}
