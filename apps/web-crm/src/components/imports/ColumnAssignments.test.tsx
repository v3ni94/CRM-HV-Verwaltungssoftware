import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ColumnAssignments } from "./ColumnAssignments";

const rows = [
  { id: "01920000-0000-7000-8000-000000000001", report_type: "units", header: "Einh.", target_field: "number", use_count: 3, last_used_at: null },
  { id: "01920000-0000-7000-8000-000000000002", report_type: "units", header: "Notiz", target_field: null, use_count: 1, last_used_at: null },
];
const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("ColumnAssignments", () => {
  it("lists the remembered assignments and removes one after confirmation", async () => {
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
      init?.method === "DELETE" ? new Response(null, { status: 204 }) : jsonResponse(rows),
    );
    vi.stubGlobal("confirm", () => true);
    renderIntl(<ColumnAssignments />);
    const table = await screen.findByTestId("column-assignments");
    expect(table).toHaveTextContent("Einh.");
    expect(table).toHaveTextContent("wird nicht importiert");
    await userEvent.click(screen.getAllByRole("button", { name: "Entfernen" })[0] as HTMLElement);
    await waitFor(() => expect(screen.queryByText("Einh.")).not.toBeInTheDocument());
    const call = fetchMock.mock.calls.find((c) => c[1]?.method === "DELETE");
    expect(String(call?.[0])).toBe("/api/bff/imports/immoware24/column-assignments/01920000-0000-7000-8000-000000000001");
  });

  it("shows the empty state", async () => {
    fetchMock.mockImplementation(async () => jsonResponse([]));
    renderIntl(<ColumnAssignments />);
    expect(await screen.findByText("Keine Zuordnungen gemerkt.")).toBeInTheDocument();
  });
});
