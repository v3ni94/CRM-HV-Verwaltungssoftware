import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { FinApiConnections } from "./FinApiConnections";

const CONNECTION = {
  id: "0192abcd-0000-7000-8000-000000000001",
  bank_connection_id: "0192abcd-0000-7000-8000-000000000002",
  bank_name: "Sparkasse",
  status: "active",
  web_form_url: null,
  web_form_status: "FINISHED",
  last_error: null,
  auto_update_enabled: false,
  accounts: [
    {
      id: "0192abcd-0000-7000-8000-000000000003",
      finapi_account_id: "1001",
      account_holder_name: "GdWE Testweg",
      account_type: "checking",
      account_name: "Hausgeldkonto",
      property_bank_account_id: "0192abcd-0000-7000-8000-000000000004",
      balance_booked: "1234.56",
      balance_available: null,
      balance_currency: "EUR",
      balance_fetched_at: null,
      last_transactions_fetch_at: null,
    },
  ],
};

function mockLoad() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/config")) return jsonResponse({ configured: true, auto_fetch_enabled: false });
    if (url.endsWith("/connections")) return jsonResponse([CONNECTION]);
    return jsonResponse({});
  });
}

describe("FinApiConnections", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the bank name, status and account row for a connected bank", async () => {
    mockLoad();
    renderIntl(<FinApiConnections />);
    expect(await screen.findByText("Sparkasse")).toBeInTheDocument();
    expect(screen.getByText("Verbunden")).toBeInTheDocument();
    expect(screen.getByText("Hausgeldkonto")).toBeInTheDocument();
  });

  it("posts the wizard's bank name and opens the returned WebForm URL", async () => {
    const fetchMock = mockLoad();
    const openMock = vi.spyOn(window, "open").mockImplementation(() => null);
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/config")) return jsonResponse({ configured: true, auto_fetch_enabled: false });
      if (url.endsWith("/connections") && method === "GET") return jsonResponse([]);
      if (url.endsWith("/connections") && method === "POST") {
        expect(JSON.parse(String(init?.body))).toEqual({ bank_name: "Sparkasse Musterstadt" });
        return jsonResponse({ ...CONNECTION, web_form_url: "https://webform.finapi.io/wf-1" });
      }
      return jsonResponse({});
    });
    renderIntl(<FinApiConnections />);
    await screen.findByText("Noch keine Bankverbindung.");
    await userEvent.type(screen.getByLabelText("Bankname"), "Sparkasse Musterstadt");
    await userEvent.click(screen.getByRole("button", { name: "Verbinden" }));
    await waitFor(() => expect(openMock).toHaveBeenCalledWith("https://webform.finapi.io/wf-1", "_blank", "noopener"));
  });

  it("sends the date range to the per-account fetch endpoint", async () => {
    const fetchMock = mockLoad();
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/config")) return jsonResponse({ configured: true, auto_fetch_enabled: false });
      if (url.endsWith("/connections") && method === "GET") return jsonResponse([CONNECTION]);
      if (url.includes("/accounts/") && url.endsWith("/fetch")) {
        expect(JSON.parse(String(init?.body))).toEqual({ since: "2026-01-01", until: "2026-02-28" });
        return jsonResponse({ id: "run-1", status: "queued" });
      }
      return jsonResponse({});
    });
    renderIntl(<FinApiConnections />);
    await screen.findByText("Hausgeldkonto");
    const controls = screen.getAllByTestId("fetch-range");
    const accountControl = controls[controls.length - 1]!;
    await userEvent.type(within(accountControl).getByLabelText("Von"), "2026-01-01");
    await userEvent.type(within(accountControl).getByLabelText("Bis"), "2026-02-28");
    await userEvent.click(within(accountControl).getByRole("button", { name: "Umsätze abrufen" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/accounts/"), expect.anything()),
    );
  });

  it("offers a per-bank fetch once at least one account is assigned", async () => {
    const fetchMock = mockLoad();
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/config")) return jsonResponse({ configured: true, auto_fetch_enabled: false });
      if (url.endsWith("/connections") && method === "GET") return jsonResponse([CONNECTION]);
      if (url.includes("/connections/") && url.endsWith("/fetch")) {
        expect(JSON.parse(String(init?.body))).toEqual({ since: null, until: null });
        return jsonResponse([{ id: "run-1", status: "queued" }]);
      }
      return jsonResponse({});
    });
    renderIntl(<FinApiConnections />);
    await screen.findByText("Umsätze aller zugeordneten Konten abrufen");
    await userEvent.click(screen.getByRole("button", { name: "Umsätze aller zugeordneten Konten abrufen" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringMatching(/\/connections\/.+\/fetch$/),
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });
});
