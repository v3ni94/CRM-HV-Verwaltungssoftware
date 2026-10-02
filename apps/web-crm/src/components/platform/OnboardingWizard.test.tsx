import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OnboardingWizard, TenantExport } from "./OnboardingWizard";

async function fillToSummary() {
  await userEvent.type(screen.getByLabelText("Kürzel"), "muster-hv");
  await userEvent.type(screen.getByLabelText("Name des Mandanten"), "Muster HV");
  await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
  await userEvent.type(screen.getByLabelText("Name des Rechtsträgers"), "Muster Verwaltung GmbH");
  await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
  await userEvent.type(screen.getByLabelText("E-Mail des Administrators"), "admin@muster.de");
  await userEvent.type(screen.getByLabelText("Anzeigename"), "Ada Admin");
  await userEvent.type(screen.getByLabelText(/^Startpasswort/), "passwort-12345");
  await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
  await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
}

describe("OnboardingWizard (GAH-407)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("blocks step one with an invalid slug", async () => {
    renderIntl(<OnboardingWizard />);
    await userEvent.type(screen.getByLabelText("Kürzel"), "Falsch Slug");
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByLabelText("Kürzel")).toBeInTheDocument();
  });

  it("validates the admin step and the colour format", async () => {
    renderIntl(<OnboardingWizard />);
    await userEvent.type(screen.getByLabelText("Kürzel"), "muster-hv");
    await userEvent.type(screen.getByLabelText("Name des Mandanten"), "Muster HV");
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    await userEvent.type(screen.getByLabelText("Name des Rechtsträgers"), "Muster GmbH");
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    await userEvent.type(screen.getByLabelText("E-Mail des Administrators"), "ohne-at");
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    expect(await screen.findByText(/mindestens 12 Zeichen angeben/)).toBeInTheDocument();
  });

  it("submits the wizard and shows the draft welcome mail with gates closed", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({
        tenant_id: "t9",
        name: "Muster HV",
        legal_entities: [{ id: "e1", kind: "manager", name: "Muster Verwaltung GmbH" }],
        admin: { email: "admin@muster.de", existed: false, roles: ["tenant_admin"] },
        feature_flags: { ai: false },
        gates: { G1: false, G5: false },
        welcome_email: { to: "admin@muster.de", subject: "Willkommen", body: "Entwurfstext", status: "draft" },
      }),
    );
    renderIntl(<OnboardingWizard />);
    await fillToSummary();
    await userEvent.click(screen.getByRole("button", { name: "Mandant anlegen" }));
    expect(await screen.findByText("Kein Gate geöffnet, keine E-Mail versendet.")).toBeInTheDocument();
    expect(screen.getByText(/G1 geschlossen, G5 geschlossen/)).toBeInTheDocument();
    expect(screen.getByText("Entwurfstext")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe("/api/bff/platform/onboarding");
    expect(JSON.parse(String(init?.body)).slug).toBe("muster-hv");
  });

  it("shows the API error on submit and stays in the wizard", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ code: "X", title: "Kürzel vergeben", status: 409 }, 409));
    renderIntl(<OnboardingWizard />);
    await fillToSummary();
    await userEvent.click(screen.getByRole("button", { name: "Mandant anlegen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mandant anlegen" })).toBeEnabled();
  });
});

describe("TenantExport (GAH-407)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });
  const req = (status: string, extra: object = {}) => ({
    id: "r1", purpose: "access", status, requested_by: "u1", decided_by: null, downloads: 0, created_at: "2026-10-01T10:00:00Z", ...extra,
  });

  it("disables the request without a tenant and shows the empty list", () => {
    renderIntl(<TenantExport tenants={[]} />);
    expect(screen.getByRole("button", { name: "Export beantragen" })).toBeDisabled();
    expect(screen.getByText("Keine Anträge.")).toBeInTheDocument();
  });

  it("lists requests with approve and reject for a requested export", async () => {
    fetchMock.mockImplementation(async () => jsonResponse([req("requested")]));
    renderIntl(<TenantExport tenants={[{ id: "t1", name: "Eins", slug: "eins" }]} />);
    await userEvent.click(screen.getByRole("button", { name: "Aktualisieren" }));
    expect(await screen.findByRole("button", { name: "Freigeben" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ablehnen" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "ZIP herunterladen" })).not.toBeInTheDocument();
  });

  it("offers the download only for an approved export", async () => {
    fetchMock.mockImplementation(async () => jsonResponse([req("approved", { job_status: "ready" })]));
    renderIntl(<TenantExport tenants={[{ id: "t1", name: "Eins", slug: "eins" }]} />);
    await userEvent.click(screen.getByRole("button", { name: "Aktualisieren" }));
    const link = await screen.findByRole("link", { name: "ZIP herunterladen" });
    expect(link).toHaveAttribute("href", "/api/bff/platform/tenants/t1/export-requests/r1/download");
  });

  it("shows the error when the request is refused", async () => {
    fetchMock.mockImplementation(async (input, init) =>
      init?.method === "POST" ? jsonResponse({ code: "X", title: "Verweigert", status: 403 }, 403) : jsonResponse([]),
    );
    renderIntl(<TenantExport tenants={[{ id: "t1", name: "Eins", slug: "eins" }]} />);
    await userEvent.click(screen.getByRole("button", { name: "Export beantragen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
