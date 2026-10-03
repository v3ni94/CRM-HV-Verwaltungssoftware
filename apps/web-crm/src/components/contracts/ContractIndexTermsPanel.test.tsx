import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ContractIndexTermsPanel } from "./ContractIndexTermsPanel";

const ID = "01920000-0000-7000-8000-0000000000a3";
const EMPTY = { index_agreement: null, graduated_steps: [], latest_index_month: null, latest_index_value: null };

function mockApi(terms: unknown, proposals: unknown[] = []) {
  const calls: string[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push(`${init?.method ?? "GET"} ${url} ${String(init?.body ?? "")}`);
    if (url.includes("rent-increase-proposals")) return jsonResponse(proposals);
    return jsonResponse(init?.method === "PUT" ? JSON.parse(String(init.body)) : terms);
  });
  return calls;
}

describe("ContractIndexTermsPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves graduated steps as decimal strings", async () => {
    const calls = mockApi(EMPTY);
    renderIntl(<ContractIndexTermsPanel contractId={ID} canUpdate />);
    const user = userEvent.setup();
    await user.click(await screen.findByLabelText("Staffelmiete"));
    await user.click(screen.getByRole("button", { name: "Staffelstufe hinzufügen" }));
    await user.type(screen.getByLabelText("Gültig ab"), "2027-01-01");
    await user.type(screen.getByLabelText("Nettomiete"), "650,5");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(calls.some((c) => c.startsWith("PUT"))).toBe(true));
    const put = calls.find((c) => c.startsWith("PUT"))!;
    expect(put).toContain(`/api/bff/letting/contracts/${ID}/index-terms`);
    expect(put).toContain('"graduated_steps":[{"valid_from":"2027-01-01","net":"650.50"}]');
    expect(put).toContain('"index_agreement":null');
  });

  it("refuses an invalid step amount without calling the API", async () => {
    const calls = mockApi(EMPTY);
    renderIntl(<ContractIndexTermsPanel contractId={ID} canUpdate />);
    const user = userEvent.setup();
    await user.click(await screen.findByLabelText("Staffelmiete"));
    await user.click(screen.getByRole("button", { name: "Staffelstufe hinzufügen" }));
    await user.type(screen.getByLabelText("Gültig ab"), "2027-01-01");
    await user.type(screen.getByLabelText("Nettomiete"), "abc");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/positiven Betrag/);
    expect(calls.some((c) => c.startsWith("PUT"))).toBe(false);
  });

  it("shows the index agreement, latest value and proposals read only", async () => {
    mockApi(
      {
        index_agreement: { index_name: "VPI", base_index: "100.00000000", base_month: "2023-01-01", source: null },
        graduated_steps: [],
        latest_index_month: "2026-08-01",
        latest_index_value: "110.50000000",
      },
      [{ id: ID, basis: "index", current_rent: "600.00", target_rent: "663.00", effective_date: "2026-11-01" }],
    );
    renderIntl(<ContractIndexTermsPanel contractId={ID} canUpdate={false} />);
    expect(await screen.findByTestId("latest-index")).toHaveTextContent("08.2026");
    expect(await screen.findByText(/663,00/)).toBeInTheDocument();
    expect(screen.getByLabelText("Indexreihe")).toHaveValue("VPI");
    expect(screen.queryByRole("button", { name: "Speichern" })).toBeNull();
  });
});
