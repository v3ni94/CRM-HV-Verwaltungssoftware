import { describe, expect, it } from "vitest";

import { crmBrandingCssVars, crmBrandingLogoSrc, NEUTRAL_CRM_BRANDING, parseCrmBranding, readableOn } from "./branding";

const answer = (extra: Record<string, unknown>) => ({
  branding: { primary_color: "#1a2b3c", accent_color: "#ffcc00", ...extra },
  has_logo_light: true,
});

describe("CRM tenant branding (GAI-109)", () => {
  it("sets no variables while the switch is off (default)", () => {
    expect(crmBrandingCssVars(parseCrmBranding(answer({})))).toEqual({});
    expect(crmBrandingCssVars(parseCrmBranding(answer({ crm_apply: false })))).toEqual({});
  });

  it("sets primary and accent variables with readable foreground when the switch is on", () => {
    const vars = crmBrandingCssVars(parseCrmBranding(answer({ crm_apply: true })));
    expect(vars["--mhvp-color-primary"]).toBe("#1A2B3C");
    expect(vars["--mhvp-color-primary-fg"]).toBe("#FFFFFF");
    expect(vars["--mhvp-color-accent"]).toBe("#FFCC00");
    expect(vars["--mhvp-color-accent-fg"]).toBe("#1A1A1A");
  });

  it("ignores invalid colours and unknown shapes", () => {
    const vars = crmBrandingCssVars(parseCrmBranding(answer({ crm_apply: true, primary_color: "red", accent_color: "url(x)" })));
    expect(vars).toEqual({});
    expect(parseCrmBranding(null)).toEqual(NEUTRAL_CRM_BRANDING);
    expect(parseCrmBranding("x")).toEqual(NEUTRAL_CRM_BRANDING);
    expect(readableOn("#FFFFFF")).toBe("#1A1A1A");
  });
});

describe("CRM shell logo (AK15)", () => {
  const on = { ...NEUTRAL_CRM_BRANDING, apply: true, hasLogoLight: true };
  it("uses the BFF logo only with switch and logo", () => {
    expect(crmBrandingLogoSrc(on, "/x.png")).toBe("/api/bff/tenant/branding/logo/light");
    expect(crmBrandingLogoSrc({ ...on, apply: false }, "/x.png")).toBe("/x.png");
    expect(crmBrandingLogoSrc({ ...on, hasLogoLight: false }, "/x.png")).toBe("/x.png");
  });
});
