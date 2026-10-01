import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ReservePayments } from "./ReservePayments";

const LEDGER = "0192abcd-0000-7000-8000-000000000801";

describe("Reserve payments (AE08)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows planned, bound and proposal per reserve", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        mode: "plan_ratio_proposal",
        paid_unassigned: "100.00",
        reserves: [
          { reserve_id: "a", name: "Dach", planned: "1200.00", paid_bound: "0.00", open_bound: "1200.00", paid_proposal: "33.33" },
        ],
      }),
    );
    renderIntl(<ReservePayments ledgerId={LEDGER} year={2025} />);
    await userEvent.click(screen.getByRole("button", { name: "Soll und Ist laden" }));
    await waitFor(() => expect(screen.getByRole("table")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/hoa/ledgers/${LEDGER}/reserve-payments?year=2025`);
    expect(screen.getByText(/33,33/)).toBeInTheDocument();
    expect(screen.getByText("Vorschlag nach Planverhältnis")).toBeInTheDocument();
  });

  it("hides the proposal column in the default variant", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ mode: "bound_only", paid_unassigned: "0.00", reserves: [] }),
    );
    renderIntl(<ReservePayments ledgerId={LEDGER} year={2025} />);
    await userEvent.click(screen.getByRole("button", { name: "Soll und Ist laden" }));
    await waitFor(() => expect(screen.getByRole("table")).toBeInTheDocument());
    expect(screen.queryByText("Vorschlag nach Planverhältnis")).toBeNull();
  });
});
