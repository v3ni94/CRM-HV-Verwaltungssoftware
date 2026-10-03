import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ReleaseGatesAdmin, type GateOverview, type GateRequest } from "./ReleaseGatesAdmin";

const tenants = [
  { id: "t-a", name: "Mandant A" },
  { id: "t-b", name: "Mandant B" },
];
const DOC = "01890000-0000-7000-8000-000000000001";
const request: GateRequest = {
  id: "r-1",
  gate: "G2",
  scope: "Pilotobjekt Zahlungen",
  evidence: "Bericht",
  status: "requested",
  requested_by: "u-1",
  decided_by: null,
  decided_at: null,
  decision_comment: null,
  opened_by: null,
  opened_at: null,
  revoked_by: null,
  revoked_at: null,
  revoke_comment: null,
  evidence_document_id: DOC,
  scope_property_ids: null,
  checklist: null,
};
const overview = (rows: GateRequest[]): GateOverview => ({
  tenant_id: "t-a",
  gates: [{ gate: "G2", label: "Zahlungsveranlassung", open: false, scopes: [], partially_open: false }],
  requests: rows,
});
const checklists = [
  {
    gate: "G2",
    label: "Zahlungsveranlassung",
    items: [{ code: "sepa_test", label: "SEPA Testlauf" }],
    functions: [],
    evidence_document_required: true,
  },
];

describe("ReleaseGatesAdmin", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("flags confirmed checklist codes without checkable evidence", () => {
    renderIntl(
      <ReleaseGatesAdmin
        tenants={tenants}
        activeTenantId="t-a"
        initial={overview([{ ...request, checklist_unverified: ["sepa_test"] }])}
        checklists={checklists}
      />,
    );
    expect(screen.getByTestId("unverified-r-1")).toHaveTextContent("sepa_test");
    expect(screen.getByTestId("unverified-r-1")).toHaveTextContent("manuell prüfen");
  });

  it("approves with comment and shows the opening", async () => {
    const approved = { ...request, status: "approved", opened_by: "u-2", opened_at: "2026-10-01T08:00:00Z" };
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/release-gates/requests/r-1/approve")) return jsonResponse(approved);
      if (url.endsWith("/platform/tenants/t-a/release-gates")) return jsonResponse(overview([approved]));
      return jsonResponse({}, 404);
    });
    renderIntl(
      <ReleaseGatesAdmin tenants={tenants} activeTenantId="t-a" initial={overview([request])} checklists={checklists} />,
    );
    expect(screen.getByText("geschlossen")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: DOC })).toHaveAttribute("href", `/dokumente/${DOC}`);
    await userEvent.type(screen.getByLabelText("Kommentar"), "geprüft");
    await userEvent.click(screen.getByRole("button", { name: "Genehmigen" }));
    await waitFor(() => expect(screen.getByText(/u-2, /)).toBeInTheDocument());
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/approve"));
    expect(call?.[0]).toBe("/api/bff/platform/tenants/t-a/release-gates/requests/r-1/approve");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ comment: "geprüft" });
  });

  it("submits a request with checklist and evidence document", async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/tenant/release-gates/requests")) return jsonResponse(request, 201);
      if (url.endsWith("/release-gates")) return jsonResponse(overview([request]));
      return jsonResponse({}, 404);
    });
    renderIntl(<ReleaseGatesAdmin tenants={tenants} activeTenantId="t-a" initial={overview([])} checklists={checklists} />);
    await userEvent.type(screen.getByLabelText("Umfang (Funktionen und Objektgruppe)"), "Pilotobjekt Zahlungen");
    await userEvent.type(screen.getByLabelText("Prüfnachweis"), "Bericht");
    await userEvent.type(screen.getByLabelText(/^Nachweisdokument/), DOC);
    await userEvent.type(screen.getByLabelText("Bestätigung SEPA Testlauf"), "ok");
    await userEvent.click(screen.getByRole("button", { name: "Antrag stellen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/tenant/release-gates/requests"));
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
      gate: "G2",
      evidence_document_id: DOC,
      checklist: { sepa_test: "ok" },
      scope_property_ids: null,
    });
  });

  it("hides request and revoke for a foreign tenant", async () => {
    const approved = { ...request, status: "approved" };
    renderIntl(
      <ReleaseGatesAdmin tenants={tenants} activeTenantId="t-b" initial={overview([approved])} checklists={checklists} />,
    );
    expect(screen.queryByRole("button", { name: "Widerrufen" })).not.toBeInTheDocument();
    expect(screen.getByText(/nur im angemeldeten Mandanten/)).toBeInTheDocument();
  });
});
