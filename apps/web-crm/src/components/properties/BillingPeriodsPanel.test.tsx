import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { BillingPeriodsPanel } from "./PropertyPanels";

const bff = vi.fn();
vi.mock("@/lib/bff", () => ({ bff: (...args: unknown[]) => bff(...args) }));

const PERIOD = {
  id: "bp1",
  property_id: "p1",
  kind: "heating_costs",
  valid_from: "2025-01-01",
  valid_to: "2025-12-31",
  board_online_audit: false,
  status: "confirmed",
  locked_at: null,
};

describe("BillingPeriodsPanel", () => {
  beforeEach(() => bff.mockReset());

  it("zeigt den Status und sperrt nach dem Abschluss", async () => {
    bff.mockResolvedValue({ ok: true, status: 200, etag: null, data: { ...PERIOD, status: "closed", locked_at: "2026-10-01T08:00:00Z" } });
    renderIntl(<BillingPeriodsPanel periods={[PERIOD]} />);
    expect(screen.getByText(/Bestätigt/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Abschließen und sperren" }));
    await waitFor(() => expect(screen.getByText(/Abgeschlossen/)).toBeInTheDocument());
    expect(bff).toHaveBeenCalledWith("/api/bff/properties/p1/billing-periods/bp1/status", expect.objectContaining({ method: "POST", body: JSON.stringify({ status: "closed" }) }));
    expect(screen.getByText(/gesperrt am/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Abschließen/ })).toBeNull();
  });

  it("meldet einen abgelehnten Wechsel", async () => {
    bff.mockResolvedValue({ ok: false, status: 409, problem: null, message: "Wechsel nicht möglich" });
    renderIntl(<BillingPeriodsPanel periods={[PERIOD]} />);
    await userEvent.click(screen.getByRole("button", { name: "Abschließen und sperren" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wechsel nicht möglich");
    expect(screen.getByText(/Bestätigt/)).toBeInTheDocument();
  });
});
