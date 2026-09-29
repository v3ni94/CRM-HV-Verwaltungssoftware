import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { NoticePeriodHint } from "./NoticePeriodHint";

const CONTRACT = "01920000-0000-7000-8000-0000000000c1";

describe("NoticePeriodHint", () => {
  const calls: string[] = [];
  beforeEach(() => {
    calls.length = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      return jsonResponse({ end_on: "2026-12-31", contract_end_date: null, contract_end_covers: null, verify: true, note: "Orientierung" });
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("asks the API with the entered period and shows the end as orientation", async () => {
    renderIntl(<NoticePeriodHint contractId={CONTRACT} terminationDate="2026-09-05" endDate="2026-11-30" />);
    expect(screen.getByTestId("notice-termination")).toHaveValue("2026-09-05");
    // No default period: without an entered period nothing is computed.
    expect(screen.getByTestId("notice-months")).toHaveValue(null);
    await userEvent.click(screen.getByTestId("notice-compute"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Kündigungsfrist aus dem Vertrag eintragen.");
    expect(calls).toHaveLength(0);
    await userEvent.type(screen.getByTestId("notice-months"), "3");
    await userEvent.click(screen.getByTestId("notice-compute"));
    expect(await screen.findByText("Rechnerisches Ende: 31.12.2026")).toBeInTheDocument();
    expect(calls[0]).toContain("/workspace/notice-period?");
    expect(calls[0]).toContain("termination_on=2026-09-05");
    expect(calls[0]).toContain("months=3");
    expect(calls[0]).toContain("to_month_end=true");
    expect(calls[0]).toContain(`contract_id=${CONTRACT}`);
    // The typed contract end 30.11.2026 lies before the computed end: a hint, no block.
    expect(screen.getByText(/Das eingetragene Vertragsende 30.11.2026 liegt vor dem rechnerischen Ende/)).toBeInTheDocument();
    expect(screen.getAllByText("zu verifizieren").length).toBeGreaterThan(1);
  });

  it("confirms an end date on or after the computed end and needs a termination date", async () => {
    const { unmount } = renderIntl(<NoticePeriodHint contractId={CONTRACT} terminationDate="2026-09-05" endDate="2026-12-31" />);
    await userEvent.type(screen.getByTestId("notice-months"), "3");
    await userEvent.click(screen.getByTestId("notice-compute"));
    expect(await screen.findByText("Das eingetragene Vertragsende 31.12.2026 liegt nicht vor dem rechnerischen Ende.")).toBeInTheDocument();
    unmount();
    renderIntl(<NoticePeriodHint contractId={CONTRACT} terminationDate="" endDate="" />);
    await userEvent.click(screen.getByTestId("notice-compute"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Zugang der Kündigung eintragen.");
    await waitFor(() => expect(calls).toHaveLength(1));
  });
});
