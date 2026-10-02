/**
 * Tenant branding in the CRM at runtime (GAI-109, section 4.2 white label).
 *
 * The layout loads `GET /api/v1/tenant/branding` (BFF allow list: tenant/branding) and sets the
 * colours as CSS variables, but only when the tenant switch `branding.crm_apply` is on (default
 * off, so the neutral product look stays unless the tenant decides otherwise). Colours count only
 * as valid #RRGGBB values; everything else is ignored, nothing is invented. The logo is not
 * applied yet (open point AJ31: logo route needs a binary BFF path).
 */

export type CrmBranding = {
  apply: boolean;
  primaryColor: string | null;
  accentColor: string | null;
  hasLogoLight: boolean;
  hasLogoDark: boolean;
};

export const NEUTRAL_CRM_BRANDING: CrmBranding = {
  apply: false,
  primaryColor: null,
  accentColor: null,
  hasLogoLight: false,
  hasLogoDark: false,
};

const HEX = /^#[0-9A-Fa-f]{6}$/;

function hex(value: unknown): string | null {
  return typeof value === "string" && HEX.test(value) ? value.toUpperCase() : null;
}

/** Maps the API answer; unknown shapes yield the neutral branding. */
export function parseCrmBranding(raw: unknown): CrmBranding {
  if (!raw || typeof raw !== "object") return NEUTRAL_CRM_BRANDING;
  const data = raw as { branding?: Record<string, unknown>; has_logo_light?: unknown; has_logo_dark?: unknown };
  const b = data.branding ?? {};
  return {
    apply: b.crm_apply === true,
    primaryColor: hex(b.primary_color),
    accentColor: hex(b.accent_color),
    hasLogoLight: data.has_logo_light === true,
    hasLogoDark: data.has_logo_dark === true,
  };
}

function luminance(color: string): number {
  const channel = (offset: number) => {
    const v = parseInt(color.slice(offset, offset + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

/** Readable text colour on the given background (dark ink or white by relative luminance). */
export function readableOn(color: string): string {
  return luminance(color) > 0.4 ? "#1A1A1A" : "#FFFFFF";
}

/** CSS custom properties of the tenant; empty while the switch is off or nothing is configured. */
export function crmBrandingCssVars(branding: CrmBranding): Record<string, string> {
  const vars: Record<string, string> = {};
  if (!branding.apply) return vars;
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
