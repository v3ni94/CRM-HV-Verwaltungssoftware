import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PrivacyAdmin } from "./PrivacyAdmin";

const PROFILE = { id: "p1", data_type: "contact", retention_months: 36, start_rule: "Ende Kalenderjahr", basis_note: null, released: false, released_at: null };
const REQUEST = {
  id: "r1",
  contact_id: "c1",
  status: "requested",
  received_on: "2026-09-30",
  reason: null,
  blockers: [{ code: "retention_running", detail: "Die Aufbewahrungsfrist läuft." }],
  decided_at: null,
  executed_at: null,
};

function route(extra: Record<string, unknown> = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    for (const [key, value] of Object.entries(extra)) if (url.includes(key)) return jsonResponse(value);
    if (url.includes("deletion-profiles")) return jsonResponse([PROFILE]);
    if (url.includes("erasure-requests")) return jsonResponse([REQUEST]);
    if (url.includes("privacy/register")) return jsonResponse([]);
    return jsonResponse({});
  });
}

describe("PrivacyAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists profiles and requests with lock reasons", async () => {
    route();
    renderIntl(<PrivacyAdmin canManage canApprove />);
    expect(await screen.findByTestId("privacy-profile-row")).toHaveTextContent("Entwurf");
    expect(await screen.findByTestId("privacy-erasure-row")).toHaveTextContent("Die Aufbewahrungsfrist läuft.");
  });

  it("hides change actions without permissions", async () => {
    route();
    renderIntl(<PrivacyAdmin canManage={false} canApprove={false} />);
    await screen.findByTestId("privacy-profile-row");
    expect(screen.queryByRole("button", { name: "Freigeben" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Profil speichern" })).not.toBeInTheDocument();
  });

  it("releases a profile via the API", async () => {
    const fetchMock = route();
    renderIntl(<PrivacyAdmin canManage canApprove />);
    await screen.findByTestId("privacy-profile-row");
    const buttons = screen.getAllByRole("button", { name: "Freigeben" });
    fireEvent.click(buttons[0]!);
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/deletion-profiles/p1/release"))).toBe(true));
  });

  it("generates the records draft and offers the download", async () => {
    route({ "processing-records": { title: "Verzeichnis", status: "Entwurf", review_notice: "Nicht geprüft.", markdown: "# Verzeichnis" } });
    renderIntl(<PrivacyAdmin canManage canApprove />);
    await screen.findByTestId("privacy-profile-row");
    fireEvent.click(screen.getByRole("button", { name: "Entwurf erzeugen" }));
    expect(await screen.findByTestId("privacy-records-draft")).toHaveTextContent("# Verzeichnis");
    expect(screen.getByText("Nicht geprüft.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Entwurf herunterladen" })).toBeInTheDocument();
  });

  it("offers the PDF draft and opens the editor of a register entry", async () => {
    const entry = {
      id: "g1", kind: "sub_processor", name: "Google Gmail", role: null, purpose: null, data_categories: [], data_subjects: [], recipients: null,
      third_country: false, third_country_status: "open", third_country_countries: null, third_country_note: null, avv_status: "none", avv_confirmed_on: null,
      avv_document_id: null, retention_note: null, legal_review_status: "open", legal_reviewed_on: null, active: true, legal_basis: null, responsibilities: {},
      responsibility_note: null, processor_ids: [], source_key: "gmail", source_detail: "Aus Mandantenkonfiguration erkannt (aktiv).",
    };
    route({ "config-sources": [], "privacy/register": [entry] });
    renderIntl(<PrivacyAdmin canManage canApprove />);
    const row = await screen.findByTestId("privacy-register-row");
    expect(row).toHaveTextContent("Aus Konfiguration");
    expect(screen.getByTestId("privacy-records-pdf")).toHaveAttribute("href", "/api/bff/privacy/processing-records/pdf");
    fireEvent.click(screen.getByRole("button", { name: "Bearbeiten" }));
    expect(await screen.findByTestId("privacy-register-editor")).toBeInTheDocument();
  });
});
