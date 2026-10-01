import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PositionContext } from "./PositionContext";

describe("PositionContext", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("loads the context on demand and lists missing documents", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({
        booking: { booking_date: "2025-06-01", text: "Gartenpflege", reference: null, lines: [{ account_number: "4100", account_name: "Garten", debit: "120.00", credit: "0.00" }] },
        invoice: { number: "R-1", invoice_date: "2025-06-01", service_from: null, service_to: null, gross: "120.00", vendor_name: "Grün GmbH" },
        order: null,
        contract: null,
        payment: null,
        allocation: null,
        previous_year: { account: "4100 Garten", current: "120.00", previous: "100.00", difference: "20.00" },
        missing: ["Zur Rechnung liegt kein Zahlungsauftrag vor."],
        note: "Hinweis",
      }),
    );
    renderIntl(<PositionContext engagementId="e1" itemId="p1" />);
    await user.click(screen.getByRole("button"));
    await waitFor(() => expect(screen.getByTestId("position-context")).toBeInTheDocument());
    expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).toBe("/api/bff/portal/board/engagements/e1/positions/p1/context");
    expect(screen.getByText(/Grün GmbH/)).toBeInTheDocument();
    expect(screen.getByTestId("position-missing")).toHaveTextContent("kein Zahlungsauftrag");
  });
});
