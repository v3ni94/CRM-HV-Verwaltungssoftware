import { screen } from "@testing-library/react";
import type { ReactElement } from "react";

import { renderIntl } from "@/test/intl";
import { de, resetRoutes, route, stubProps } from "@/test/serverPage";

const cookieValues = vi.hoisted(() => ({ portal_view: undefined as string | undefined }));

vi.mock("@/lib/api-server", async () => (await import("@/test/serverPage")).apiServerMock());
vi.mock("next/navigation", async () => (await import("@/test/serverPage")).navigationMock());
vi.mock("next-intl/server", async () => (await import("@/test/serverPage")).intlServerMock());
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: (name: string) => (cookieValues[name as "portal_view"] ? { value: cookieValues[name as "portal_view"] } : undefined) }),
}));
vi.mock("@/lib/branding", async (orig) => ({
  ...(await orig<typeof import("@/lib/branding")>()),
  fetchPortalBranding: async () => (await import("@/lib/branding")).NEUTRAL_BRANDING,
}));
vi.mock("@/components/shell/InstallHint", async () => (await import("@/test/serverPage")).stubModule(["InstallHint"]));
vi.mock("@/components/shell/LogoutButton", async () => (await import("@/test/serverPage")).stubModule(["LogoutButton"]));
vi.mock("@/components/shell/RoleSwitcher", async () => (await import("@/test/serverPage")).stubModule(["RoleSwitcher"]));
vi.mock("@/components/shell/PortalNav", async () => (await import("@/test/serverPage")).stubModule(["PortalNav"]));
vi.mock("@/components/shell/LanguageSwitch", async () => (await import("@/test/serverPage")).stubModule(["LanguageSwitch"]));
vi.mock("@/components/shell/ThemeToggle", async () => (await import("@/test/serverPage")).stubModule(["ThemeSwitch"]));
vi.mock("@/components/shell/Branding", async () => (await import("@/test/serverPage")).stubModule(["BrandMark", "LegalLinks"]));

import PortalLayout from "./layout";
import PortalLoading from "./loading";
import PortalNotFound from "./not-found";

async function show(Page: unknown, props: unknown = {}) {
  return renderIntl(await (Page as (p: unknown) => Promise<ReactElement>)(props));
}

async function renderLayout() {
  await show(PortalLayout, { children: <p>Inhalt der Seite</p> });
  return stubProps<{ links: { href: string; label: string }[] }>(screen.getByTestId("PortalNav")).links.map((l) => l.href);
}

const me = (extra: Record<string, unknown>) => ({ contact_id: "c", contracts: [], ...extra });

beforeEach(() => {
  resetRoutes();
  cookieValues.portal_view = undefined;
  route("/api/v1/portal/terms", 200, { terms_version: null, accepted: true });
});

describe("PortalLayout", () => {
  it("frames the content with skip link, main landmark, footer and security link", async () => {
    route("/api/v1/portal/me", 200, me({ roles: ["tenant"] }));
    const links = await renderLayout();
    expect(screen.getByRole("link", { name: de("Portal", "skipToContent") })).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("main")).toHaveTextContent("Inhalt der Seite");
    expect(screen.getByRole("link", { name: de("Portal", "accessibilityLink") })).toHaveAttribute("href", "/barrierefreiheit");
    expect(links).toContain("/sicherheit");
    expect(links).toContain("/dokumente");
    expect(links).not.toContain("/beschluesse");
    expect(links).not.toContain("/auftraege");
  });

  it("shows owner pages only to owners", async () => {
    route("/api/v1/portal/me", 200, me({ roles: ["owner"], portal_roles: ["owner"] }));
    const links = await renderLayout();
    expect(links).toEqual(expect.arrayContaining(["/beschluesse", "/hausgeldkonto", "/belege", "/vorlagen"]));
  });

  it("limits a provider to orders and framework contracts", async () => {
    route("/api/v1/portal/me", 200, me({ roles: ["provider"] }));
    const links = await renderLayout();
    expect(links).toEqual(["/auftraege", "/rahmenvertraege", "/sicherheit"]);
  });

  it("limits a pure board account to the audit room", async () => {
    route("/api/v1/portal/me", 200, me({ roles: ["board"] }));
    const links = await renderLayout();
    expect(links).toEqual(["/pruefung", "/sicherheit"]);
  });

  it("narrows the navigation to a chosen portal role and ignores unknown values", async () => {
    route("/api/v1/portal/me", 200, me({ roles: ["owner"], portal_roles: ["owner", "service_provider"] }));
    cookieValues.portal_view = "service_provider";
    expect(await renderLayout()).toEqual(["/auftraege", "/rahmenvertraege", "/sicherheit"]);
    document.body.innerHTML = "";
    cookieValues.portal_view = "admin";
    const links = await renderLayout();
    expect(links).toContain("/beschluesse");
    expect(links).not.toContain("/auftraege");
  });

  it("offers the assistant only with the chat bot switch", async () => {
    route("/api/v1/portal/me", 200, me({ roles: ["tenant"], features: { chat_bot_enabled: true } }));
    expect(await renderLayout()).toContain("/assistent");
  });

  it("falls back to the tenant navigation when /me fails", async () => {
    route("/api/v1/portal/me", 500);
    const links = await renderLayout();
    expect(links).toContain("/dokumente");
    expect(links).not.toContain("/beschluesse");
  });

  it("sends the account to the terms mask while an unaccepted version is published", async () => {
    route("/api/v1/portal/terms", 200, { terms_version: "2026-1", accepted: false });
    route("/api/v1/portal/me", 200, me({ roles: ["tenant"] }));
    await expect(show(PortalLayout, { children: null })).rejects.toThrow("NEXT_REDIRECT:/nutzungsbedingungen");
  });

  it("never blocks the page when the terms query fails", async () => {
    route("/api/v1/portal/terms", 500);
    route("/api/v1/portal/me", 200, me({ roles: ["tenant"] }));
    await renderLayout();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });
});

describe("PortalLoading and PortalNotFound", () => {
  it("loading announces the state politely", async () => {
    await show(PortalLoading);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText(de("Portal", "loading"))).toBeInTheDocument();
  });

  it("not found shows a German notice with a way back", async () => {
    await show(PortalNotFound);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(de("Portal", "notFoundTitle"));
    expect(screen.getByRole("link", { name: de("Portal", "toStart") })).toHaveAttribute("href", "/start");
  });
});
