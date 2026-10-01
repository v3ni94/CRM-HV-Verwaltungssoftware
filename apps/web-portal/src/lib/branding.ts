/**
 * Tenant branding of the portal (B26, M21-04, section 14 White-Label je Mandant).
 *
 * The API resolves the tenant from the portal host (`GET /api/v1/tenant/branding`, public) and
 * returns only branding data. Everything is optional: an empty or unreachable branding leaves
 * the portal neutral, nothing is invented. Colours are applied only when they are valid
 * #RRGGBB values; links only when they are https URLs.
 */
import { headers } from "next/headers";

import { apiBaseUrl } from "./session";

export type PortalBranding = {
  name: string | null;
  primaryColor: string | null;
  accentColor: string | null;
  imprintUrl: string | null;
  privacyUrl: string | null;
  hasLogoLight: boolean;
  hasLogoDark: boolean;
  /** Codes of the legal texts the tenant has released (AE29, only known codes). */
  legalReleased: LegalCode[];
};

export const LEGAL_CODES = ["impressum", "datenschutz", "nutzungsbedingungen"] as const;
export type LegalCode = (typeof LEGAL_CODES)[number];

export const NEUTRAL_BRANDING: PortalBranding = {
  name: null,
  primaryColor: null,
  accentColor: null,
  imprintUrl: null,
  privacyUrl: null,
  hasLogoLight: false,
  hasLogoDark: false,
  legalReleased: [],
};

const HEX = /^#[0-9A-Fa-f]{6}$/;

function hex(value: unknown): string | null {
  return typeof value === "string" && HEX.test(value) ? value.toUpperCase() : null;
}

function httpsUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    return new URL(value).protocol === "https:" ? value : null;
  } catch {
    return null;
  }
}

function text(value: unknown, max: number): string | null {
  return typeof value === "string" && value.trim() ? value.trim().slice(0, max) : null;
}

/** Maps the API answer to the validated branding; unknown shapes yield the neutral branding. */
export function parseBranding(raw: unknown): PortalBranding {
  if (!raw || typeof raw !== "object") return NEUTRAL_BRANDING;
  const data = raw as {
    name?: unknown;
    branding?: Record<string, unknown>;
    has_logo_light?: unknown;
    has_logo_dark?: unknown;
    legal_texts_released?: unknown;
  };
  const b = data.branding ?? {};
  return {
    name: text(b.portal_name, 80),
    primaryColor: hex(b.primary_color),
    accentColor: hex(b.accent_color),
    imprintUrl: httpsUrl(b.imprint_url),
    privacyUrl: httpsUrl(b.privacy_url),
    hasLogoLight: data.has_logo_light === true,
    hasLogoDark: data.has_logo_dark === true,
    legalReleased: Array.isArray(data.legal_texts_released)
      ? LEGAL_CODES.filter((code) => (data.legal_texts_released as unknown[]).includes(code))
      : [],
  };
}

export type LegalLink = { code: LegalCode; href: string; external: boolean };

/** Footer links to the legal texts (AE29): a released text of the tenant is shown on the portal
 *  page /rechtliches/<code>; without a release the https link of the branding stands in, and
 *  without either there is no link (nothing invented). */
export function legalLinks(branding: PortalBranding): LegalLink[] {
  const links: LegalLink[] = [];
  for (const code of LEGAL_CODES) {
    if (branding.legalReleased.includes(code)) {
      links.push({ code, href: `/rechtliches/${code}`, external: false });
      continue;
    }
    const url = code === "impressum" ? branding.imprintUrl : code === "datenschutz" ? branding.privacyUrl : null;
    if (url) links.push({ code, href: url, external: true });
  }
  return links;
}

function luminance(color: string): number {
  const channel = (offset: number) => {
    const v = parseInt(color.slice(offset, offset + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  }
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

/** Readable text colour on the given background (dark ink or white by relative luminance). */
export function readableOn(color: string): string {
  return luminance(color) > 0.4 ? "#1A1A1A" : "#FFFFFF";
}

/** CSS custom properties that replace the neutral tokens; empty when nothing is configured. */
export function brandingCssVars(branding: PortalBranding): Record<string, string> {
  const vars: Record<string, string> = {};
  if (branding.primaryColor) {
    vars["--mhvp-color-primary"] = branding.primaryColor;
    vars["--mhvp-color-primary-hover"] = branding.primaryColor;
    vars["--mhvp-color-primary-fg"] = readableOn(branding.primaryColor);
  }
  if (branding.accentColor) {
    vars["--mhvp-color-accent"] = branding.accentColor;
    vars["--mhvp-color-accent-fg"] = readableOn(branding.accentColor);
  }
  return vars;
}

/** Branding of the tenant that owns the requested portal host; neutral on every failure. */
export async function fetchPortalBranding(): Promise<PortalBranding> {
  try {
    const h = await headers();
    const host = h.get("x-forwarded-host") ?? h.get("host");
    if (!host) return NEUTRAL_BRANDING;
    // no-store: the answer depends on the host header, a shared fetch cache must never serve
    // one tenant's branding to another host.
    const response = await fetch(`${apiBaseUrl()}/api/v1/tenant/branding`, {
      headers: { "x-portal-host": host },
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    if (!response.ok) return NEUTRAL_BRANDING;
    return parseBranding(await response.json());
  } catch {
    return NEUTRAL_BRANDING;
  }
}
