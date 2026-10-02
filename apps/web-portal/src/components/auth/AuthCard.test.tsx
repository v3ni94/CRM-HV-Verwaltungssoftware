import { render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";

import { AuthCard } from "./AuthCard";
import { NEUTRAL_BRANDING, type PortalBranding } from "@/lib/branding";

let branding: PortalBranding = NEUTRAL_BRANDING;

vi.mock("next-intl/server", async () => {
  const { intlServerMock } = await import("@/test/serverPage");
  return { ...intlServerMock(), getLocale: async () => "de" };
});
vi.mock("@/lib/branding", async (orig) => ({
  ...(await orig<typeof import("@/lib/branding")>()),
  fetchPortalBranding: async () => branding,
}));
// BrandMark and LegalLinks are async server components; the stubs expose what AuthCard passes on.
vi.mock("@/components/shell/Branding", () => ({
  BrandMark: ({ branding: b, fallback }: { branding: PortalBranding; fallback: string }) => (
    <div>
      <p>{b.name ?? fallback}</p>
      {b.hasLogoLight ? <span role="img" aria-label="Logo" data-src="/api/branding-logo/light" /> : null}
    </div>
  ),
  LegalLinks: () => <nav data-testid="legal-links" />,
}));
vi.mock("@/components/shell/LanguageSwitch", () => ({ LanguageSwitch: () => <div data-testid="language-switch" /> }));

async function show() {
  return render(await AuthCard({ title: "Anmelden", children: <p>Formularinhalt</p> }));
}

describe("AuthCard", () => {
  beforeEach(() => {
    branding = NEUTRAL_BRANDING;
  });

  it("frames the content with the title as the single h1 and the neutral product name", async () => {
    await show();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Anmelden");
    expect(screen.getByText("MH Verwaltungsplattform")).toBeInTheDocument();
    expect(screen.getByText("Formularinhalt")).toBeInTheDocument();
    expect(screen.getByTestId("language-switch")).toBeInTheDocument();
    expect(screen.getByTestId("legal-links")).toBeInTheDocument();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("shows the tenant name and logo when the tenant configured them", async () => {
    branding = { ...NEUTRAL_BRANDING, name: "Beispiel Verwaltung", hasLogoLight: true };
    await show();
    expect(screen.getByText("Beispiel Verwaltung")).toBeInTheDocument();
    expect(screen.getByRole("img")).toHaveAttribute("data-src", "/api/branding-logo/light");
  });

  it("has no axe violations", async () => {
    const { container } = await show();
    const results = await axe(container, { rules: { region: { enabled: false } } });
    expect(results.violations).toEqual([]);
  });
});
