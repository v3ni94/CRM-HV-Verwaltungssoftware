/**
 * Legal texts of the tenant of the portal host (AE29, M21-04): imprint, privacy notice and terms
 * of use, public and read only. The API returns only the approved version (release by a second
 * person); without one the answer carries `released: false` and the marker, the portal then shows
 * the marker or the external https link of the branding. Nothing is invented here.
 */
import { headers } from "next/headers";

import { LEGAL_CODES, type LegalCode } from "./branding";
import { apiBaseUrl } from "./session";

export type LegalText = {
  code: LegalCode;
  released: boolean;
  version: number | null;
  title: string | null;
  body: string | null;
  externalUrl: string | null;
  /** Label of the terms version of the consent policy (only for the terms text). */
  termsVersion: string | null;
};

export function isLegalCode(value: string): value is LegalCode {
  return (LEGAL_CODES as readonly string[]).includes(value);
}

function httpsUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    return new URL(value).protocol === "https:" ? value : null;
  } catch {
    return null;
  }
}

/** Maps the API answer; a released text needs a non-empty body, otherwise it counts as not released. */
export function parseLegalText(code: LegalCode, raw: unknown): LegalText {
  const data = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const body = typeof data.body === "string" && data.body.trim() ? data.body : null;
  const released = data.released === true && body !== null;
  return {
    code,
    released,
    version: released && typeof data.version === "number" ? data.version : null,
    title: released && typeof data.title === "string" ? data.title : null,
    body: released ? body : null,
    externalUrl: httpsUrl(data.external_url),
    termsVersion: typeof data.terms_version === "string" && data.terms_version ? data.terms_version : null,
  };
}

/** Text of the tenant that owns the requested portal host; `null` when the API cannot be reached. */
export async function fetchLegalText(code: LegalCode): Promise<LegalText | null> {
  try {
    const h = await headers();
    const host = h.get("x-forwarded-host") ?? h.get("host");
    if (!host) return null;
    // no-store: the answer depends on the host header (never serve one tenant's text to another).
    const response = await fetch(`${apiBaseUrl()}/api/v1/tenant/legal-texts/${code}`, {
      headers: { "x-portal-host": host },
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    if (response.status === 404) return parseLegalText(code, {});
    if (!response.ok) return null;
    return parseLegalText(code, await response.json());
  } catch {
    return null;
  }
}
