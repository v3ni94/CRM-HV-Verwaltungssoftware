import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PeriodLockPanel, type PeriodLockRow } from "./PeriodLockPanel";

const row: PeriodLockRow = {
  id: "11111111-1111-1111-1111-111111111111",
  ledger_id: "22222222-2222-2222-2222-222222222222",
  property_id: "33333333-3333-3333-3333-333333333333",
  period_from: "2026-04-01",
  period_to: "2026-06-30",
  source: "manual",
  reason: "Abschluss Q2",
  active: true,
  release_requested_by: null,
  release_request_reason: null,
};

describe("PeriodLockPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows conservative defaults and the lock with German dates", () => {
    renderIntl(<PeriodLockPanel initialSettings={null} initialRows={[row]} canApprove canSettings />);
    expect(screen.getByText(/01\.04\.2026 bis 30\.06\.2026/)).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toHaveValue("ledger_only");
    expect(screen.getAllByRole("checkbox").every((box) => !(box as HTMLInputElement).checked)).toBe(true);
    // Release is hidden while the switch is off.
    expect(screen.queryByText("Aufhebung beantragen")).not.toBeInTheDocument();
  });

  it("saves the switches", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ lock_mode: "object_period", auto_lock_on_close: false, reopen_enabled: false }),
    );
    renderIntl(<PeriodLockPanel initialSettings={null} initialRows={[]} canApprove canSettings />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "object_period");
    await userEvent.click(screen.getByRole("button", { name: "Schalter speichern" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Schalter gespeichert."));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/bff/accounting/period-locks/settings");
    expect(init?.method).toBe("PUT");
  });

  it("offers the release request only with the switch on", () => {
    renderIntl(
      <PeriodLockPanel
        initialSettings={{ lock_mode: "object_period", auto_lock_on_close: false, reopen_enabled: true }}
        initialRows={[row]}
        canApprove
        canSettings={false}
      />,
    );
    expect(screen.getByRole("button", { name: "Aufhebung beantragen" })).toBeInTheDocument();
  });
});
