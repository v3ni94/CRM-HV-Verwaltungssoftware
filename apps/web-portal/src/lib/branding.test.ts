import { brandingCssVars, NEUTRAL_BRANDING, parseBranding, readableOn } from "./branding";

vi.mock("next/headers", () => ({ headers: async () => new Headers() }));

describe("portal branding", () => {
  it("is neutral for empty or malformed answers", () => {
    expect(parseBranding(null)).toEqual(NEUTRAL_BRANDING);
    expect(parseBranding("x")).toEqual(NEUTRAL_BRANDING);
    expect(parseBranding({ name: "T", branding: {} })).toEqual(NEUTRAL_BRANDING);
    expect(brandingCssVars(NEUTRAL_BRANDING)).toEqual({});
  });

  it("accepts only valid colours and https links", () => {
    const b = parseBranding({
      branding: {
        portal_name: "  Mein Portal ",
        primary_color: "#112233",
        accent_color: "red",
        imprint_url: "https://example.test/impressum",
        privacy_url: "javascript:alert(1)",
      },
      has_logo_light: true,
      has_logo_dark: false,
    });
    expect(b).toMatchObject({
      name: "Mein Portal",
      primaryColor: "#112233",
      accentColor: null,
      imprintUrl: "https://example.test/impressum",
      privacyUrl: null,
      hasLogoLight: true,
      hasLogoDark: false,
    });
  });

  it("maps colours to the neutral tokens with a readable foreground", () => {
    const vars = brandingCssVars({ ...NEUTRAL_BRANDING, primaryColor: "#112233", accentColor: "#F5C400" });
    expect(vars["--mhvp-color-primary"]).toBe("#112233");
    expect(vars["--mhvp-color-primary-fg"]).toBe("#FFFFFF");
    expect(vars["--mhvp-color-accent"]).toBe("#F5C400");
    expect(vars["--mhvp-color-accent-fg"]).toBe("#1A1A1A");
    expect(readableOn("#FFFFFF")).toBe("#1A1A1A");
    expect(readableOn("#000000")).toBe("#FFFFFF");
  });
});
