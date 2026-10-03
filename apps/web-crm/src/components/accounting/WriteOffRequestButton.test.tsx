import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { OpenItemsTable } from "./OpenItemsTable";
import { WRITE_OFF_REQUESTED, WriteOffRequestButton } from "./WriteOffRequestButton";

const m = messages.WriteOffs;

describe("WriteOffRequestButton (AP12, GAL-302)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("requests a write off with reason and date and announces it", async () => {
    const calls: { url: string; body: unknown }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push({ url: String(input), body: init?.body });
      return jsonResponse({ id: "w1" }, 201);
    });
    const heard = vi.fn();
    window.addEventListener(WRITE_OFF_REQUESTED, heard);
    renderIntl(<WriteOffRequestButton openItemId="i1" today="2026-10-03" />);
    await userEvent.click(screen.getByRole("button", { name: m.request }));
    expect(screen.getByText(m.requestHint)).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: m.requestSubmit });
    expect(submit).toBeDisabled();
    await userEvent.type(screen.getByLabelText(m.reason), "Schuldner unbekannt verzogen");
    await userEvent.click(submit);
    await waitFor(() => expect(screen.getByTestId("write-off-requested-i1")).toBeInTheDocument());
    expect(JSON.parse(String(calls[0]!.body))).toEqual({
      open_item_id: "i1",
      effective_on: "2026-10-03",
      reason: "Schuldner unbekannt verzogen",
    });
    expect(heard).toHaveBeenCalled();
    window.removeEventListener(WRITE_OFF_REQUESTED, heard);
  });

  it("shows the API error and keeps the form", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ title: "Konflikt", detail: "Es liegt bereits ein Vorschlag vor.", status: 409 }, 409),
    );
    renderIntl(<WriteOffRequestButton openItemId="i1" today="2026-10-03" />);
    await userEvent.click(screen.getByRole("button", { name: m.request }));
    await userEvent.type(screen.getByLabelText(m.reason), "Schuldner unbekannt verzogen");
    await userEvent.click(screen.getByRole("button", { name: m.requestSubmit }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByTestId("write-off-request-form-i1")).toBeInTheDocument();
  });

  it("appears in the open items table only for open receivables", () => {
    const rows = [
      { id: "r1", account_number: "140001", kind: "receivable", due_date: "2026-08-01", amount: "10.00", remaining: "10.00" },
      { id: "p1", account_number: "160001", kind: "payable", due_date: "2026-08-01", amount: "10.00", remaining: "10.00" },
    ];
    renderIntl(<OpenItemsTable rows={rows} canRequestWriteOff today="2026-10-03" />);
    expect(screen.getByTestId("write-off-request-r1")).toBeInTheDocument();
    expect(screen.queryByTestId("write-off-request-p1")).toBeNull();
  });

  it("is hidden in the open items table without permission", () => {
    const rows = [{ id: "r1", account_number: "140001", kind: "receivable", due_date: "2026-08-01", amount: "10.00", remaining: "10.00" }];
    renderIntl(<OpenItemsTable rows={rows} />);
    expect(screen.queryByTestId("write-off-request-r1")).toBeNull();
  });
});
