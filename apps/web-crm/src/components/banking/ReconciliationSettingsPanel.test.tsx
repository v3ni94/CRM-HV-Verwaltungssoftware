import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ReconciliationSettingsPanel } from "./ReconciliationSettingsPanel";

const doc = {
  clearing_account_number: null,
  reconciliation_basis: "booking_date",
  clearing_account_options: [{ number: "009999", name: "Durchlaufposten WEG", category: "transit" }],
};

describe("ReconciliationSettingsPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the defaults and saves clearing account and basis (AO02)", async () => {
    const bodies: unknown[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (init?.method === "PUT") {
        const body = JSON.parse(String(init.body));
        bodies.push(body);
        return jsonResponse({ ...doc, ...body });
      }
      expect(String(input)).toContain("/banking/reconciliation-settings");
      return jsonResponse(doc);
    });
    renderIntl(<ReconciliationSettingsPanel />);
    const clearing = await screen.findByLabelText("Klärungskonto");
    await waitFor(() => expect(clearing).not.toBeDisabled());
    expect(clearing).toHaveValue("");
    await userEvent.selectOptions(clearing, "009999");
    await userEvent.selectOptions(screen.getByLabelText("Abstimmungsbasis"), "bank_date");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Einstellungen gespeichert."));
    expect(bodies).toEqual([{ clearing_account_number: "009999", reconciliation_basis: "bank_date" }]);
  });

  it("shows the error of a refused save", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "PUT") return jsonResponse({ title: "Forbidden", detail: "Keine Berechtigung." }, 403);
      return jsonResponse(doc);
    });
    renderIntl(<ReconciliationSettingsPanel />);
    const button = await screen.findByRole("button", { name: "Speichern" });
    await waitFor(() => expect(button).not.toBeDisabled());
    await userEvent.click(button);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
