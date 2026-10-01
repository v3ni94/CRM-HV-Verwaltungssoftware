import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { YearCarryoverPanel } from "./YearCarryoverPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
const LEDGER = "0192abcd-0000-7000-8000-000000000001";
const preview = (already: boolean) => ({
  fiscal_year: 2025, start: "2025-01-01", end: "2025-12-31", target_date: "2026-01-01",
  carried: [{ account_id: "a1", number: "1200", name: "Bank", category: "bank", balance: "1234.50" }],
  not_carried: [{ account_id: "a2", number: "4000", name: "Erlöse", category: "revenue", balance: "-500.00" }],
  already_drafted: already, note: "Nur Bank wird übernommen.",
});

describe("YearCarryoverPanel (Q02)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the closing balances and takes them over as drafts after confirmation", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(preview(false)))
      .mockResolvedValueOnce(jsonResponse([{ id: "e1" }, { id: "e2" }], 201));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<YearCarryoverPanel ledgerId={LEDGER} defaultYear={2025} />);
    await userEvent.click(screen.getByRole("button", { name: "Schlussbestände anzeigen" }));
    expect(await screen.findByText("1.234,50 EUR")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/accounting/ledgers/${LEDGER}/year-carryover?fiscal_year=2025`);
    await userEvent.click(screen.getByRole("button", { name: "Als Entwurf übernehmen" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("2 Entwürfe"));
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("POST");
    expect(refresh).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Als Entwurf übernehmen" })).toBeNull();
  });

  it("offers no takeover when drafts exist and rejects an invalid year", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(preview(true)));
    renderIntl(<YearCarryoverPanel ledgerId={LEDGER} defaultYear={2025} />);
    await userEvent.click(screen.getByRole("button", { name: "Schlussbestände anzeigen" }));
    expect(await screen.findByText(/bereits als Entwurf/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Als Entwurf übernehmen" })).toBeNull();
    await userEvent.clear(screen.getByLabelText("Geschäftsjahr (Beginnjahr)"));
    await userEvent.type(screen.getByLabelText("Geschäftsjahr (Beginnjahr)"), "99");
    expect(screen.getByRole("button", { name: "Schlussbestände anzeigen" })).toBeDisabled();
  });
});
