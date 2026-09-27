import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OpenItemsTable } from "./OpenItemsTable";

describe("OpenItemsTable", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sums the remaining amounts in cents", () => {
    renderIntl(
      <OpenItemsTable
        rows={[
          { id: "1", account_number: "10001", kind: "receivable", due_date: "2026-03-03", amount: "300.00", remaining: "0.10" },
          { id: "2", account_number: "10002", kind: "receivable", due_date: "2026-03-03", amount: "50.00", remaining: "0.20" },
        ]}
      />,
    );
    expect(screen.getByTestId("open-total").textContent).toMatch(/0,30\s€|0,30\sEUR/);
  });

  it("saves the notice-received date via PATCH when editable", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ notice_received_on: "2026-09-20" }));
    renderIntl(
      <OpenItemsTable
        canEdit
        rows={[{ id: "1", account_number: "10001", kind: "receivable", due_date: "2026-03-03", amount: "300.00", remaining: "0.10", notice_received_on: null }]}
      />,
    );
    const input = screen.getByLabelText("Zugang des Schreibens: 10001");
    await userEvent.type(input, "2026-09-20");
    await userEvent.tab();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/bff/accounting/open-items/1/notice-received");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({ notice_received_on: "2026-09-20" });
  });

  it("shows the date read-only without edit permission", () => {
    renderIntl(
      <OpenItemsTable
        rows={[{ id: "1", account_number: "10001", kind: "receivable", due_date: "2026-03-03", amount: "300.00", remaining: "0.10", notice_received_on: "2026-09-20" }]}
      />,
    );
    expect(screen.queryByLabelText("Zugang des Schreibens: 10001")).not.toBeInTheDocument();
    expect(screen.getByText("20.09.2026")).toBeInTheDocument();
  });
});
