import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { StatementDiffPanel } from "./StatementDiffPanel";

const ID = "0192abcd-0000-7000-8000-0000000023c1";
const d = (o: string, n: string, delta: string) => ({ old: o, new: n, delta });

describe("StatementDiffPanel (GAJ-104)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads and shows the difference to the previous version", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({
        version: 2,
        tenants: [{ contract_id: "c1", unit_number: "W1", status: "changed", costs: d("100.00", "120.00", "20.00"), advances_paid: d("0.00", "0.00", "0.00"), balance: d("-100.00", "-120.00", "-20.00") }],
        positions: [{ label: "Hausmeister", old: "100.00", new: "120.00", delta: "20.00" }],
      }),
    );
    renderIntl(<StatementDiffPanel statementId={ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Differenz zur Vorversion anzeigen" }));
    expect(await screen.findByText("Hausmeister")).toBeInTheDocument();
    expect(screen.getByText("geändert")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/statements/${ID}/diff`);
  });

  it("shows an empty state and API problems", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ version: 2, tenants: [], positions: [] }))
      .mockResolvedValueOnce(jsonResponse({ title: "Konflikt", status: 409, detail: "Keine Vorversion vorhanden." }, 409));
    renderIntl(<StatementDiffPanel statementId={ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Differenz zur Vorversion anzeigen" }));
    expect(await screen.findByText("Keine Unterschiede.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Differenz zur Vorversion anzeigen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
