import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PrivacyOversight } from "./PrivacyOversight";

const CONSENTS = { items: [{ kind: "marketing", active: 3, revoked: 1, objections: 0, without_proof: 2, contacts_active: 3 }] };
const MONITOR = {
  settings: { access_days: null, erasure_days: 25, warn_days: 7, note: null, configured: true },
  items: [
    { kind: "erasure", request_id: "r1", contact_id: "c1", status: "requested", received_on: "2026-09-01", warn_on: "2026-09-19", due_on: "2026-09-26", state: "overdue" },
  ],
};
const READY = { complete: false, active_services: 2, items: [{ key: "gmail", name: "Google Gmail", entry_id: null, issues: ["Kein Registereintrag"] }], note: "Hinweis G1" };

function route() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/consent-overview")) return jsonResponse(CONSENTS);
    if (url.endsWith("/request-deadlines/monitor")) return jsonResponse(MONITOR);
    if (url.endsWith("/register/readiness")) return jsonResponse(READY);
    return jsonResponse(MONITOR.settings);
  });
}

describe("PrivacyOversight", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows consents, deadlines and readiness", async () => {
    route();
    renderIntl(<PrivacyOversight canApprove={false} />);
    expect(await screen.findByText("Werbung")).toBeInTheDocument();
    expect(await screen.findByText("Frist überschritten")).toBeInTheDocument();
    expect(screen.getByText(/26\.09\.2026/)).toBeInTheDocument();
    expect(screen.getByText("Google Gmail")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Fristen speichern" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Löschung (Tage)")).toBeDisabled();
  });

  it("saves deadlines without default values", async () => {
    const fetchMock = route();
    renderIntl(<PrivacyOversight canApprove />);
    const access = await screen.findByLabelText("Auskunft (Tage)");
    await waitFor(() => expect(screen.getByLabelText("Löschung (Tage)")).toHaveValue(25));
    fireEvent.change(access, { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: "Fristen speichern" }));
    await waitFor(() => {
      const put = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PUT");
      expect(JSON.parse(String((put![1] as RequestInit).body))).toEqual({ access_days: 20, erasure_days: 25, warn_days: 7 });
    });
  });
});
