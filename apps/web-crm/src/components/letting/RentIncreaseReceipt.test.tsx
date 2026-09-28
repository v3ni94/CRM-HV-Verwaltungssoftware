import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { RentIncreaseReceipt } from "./RentIncreaseReceipt";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

const CASE = "01920000-0000-7000-8000-0000000000r1";

describe("RentIncreaseReceipt", () => {
  const calls: { url: string; method: string; body: unknown }[] = [];
  beforeEach(() => {
    calls.length = 0;
    refresh.mockClear();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push({ url: String(input), method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
      return jsonResponse({ id: CASE, received_on: "2026-10-02", status: "draft" });
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("records the access date through the receipt action", async () => {
    renderIntl(<RentIncreaseReceipt caseId={CASE} status="draft" receivedOn={null} canRecord />);
    expect(screen.getByText("Noch kein Zugangsdatum erfasst.")).toBeInTheDocument();
    await userEvent.type(screen.getByTestId("receipt-date"), "2026-10-02");
    await userEvent.click(screen.getByRole("button", { name: "Zugangsdatum erfassen" }));
    expect(await screen.findByText("Zugangsdatum gespeichert.")).toBeInTheDocument();
    expect(calls[0].url).toBe(`/api/bff/letting/rent-increases/${CASE}/actions`);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].body).toEqual({ action: "receipt", received_on: "2026-10-02" });
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("shows the recorded date and hides the form without the permission or after the case closed", () => {
    renderIntl(<RentIncreaseReceipt caseId={CASE} status="applied" receivedOn="2026-10-02" canRecord />);
    expect(screen.getByText("Erfasst: 02.10.2026")).toBeInTheDocument();
    expect(screen.queryByTestId("receipt-date")).not.toBeInTheDocument();
  });
});
