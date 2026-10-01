import { isLegalCode, parseLegalText } from "./legal-texts";

vi.mock("next/headers", () => ({ headers: async () => new Headers() }));

describe("legal texts of the portal (AE29)", () => {
  it("knows only the three codes", () => {
    expect(isLegalCode("impressum")).toBe(true);
    expect(isLegalCode("agb")).toBe(false);
  });

  it("shows a released text with version and terms label", () => {
    const text = parseLegalText("nutzungsbedingungen", {
      released: true,
      version: 2,
      title: "Nutzungsbedingungen",
      body: "Text",
      terms_version: "NB-2",
      external_url: null,
    });
    expect(text).toMatchObject({ released: true, version: 2, body: "Text", termsVersion: "NB-2" });
  });

  it("treats an empty body or an unreleased answer as not released and keeps only https links", () => {
    expect(parseLegalText("impressum", { released: true, body: "  " }).released).toBe(false);
    const open = parseLegalText("impressum", { released: false, body: "geheim", external_url: "javascript:alert(1)" });
    expect(open).toMatchObject({ released: false, body: null, externalUrl: null });
    expect(parseLegalText("datenschutz", { external_url: "https://example.test/dsgvo" }).externalUrl).toBe(
      "https://example.test/dsgvo",
    );
    expect(parseLegalText("datenschutz", null).released).toBe(false);
  });
});
