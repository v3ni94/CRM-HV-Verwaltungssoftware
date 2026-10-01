import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AcceptanceRegister, type AcceptanceState } from "./AcceptanceRegister";

const submitted = {
  id: "0190a000-0000-7000-8000-000000000001",
  case_id: "D08",
  version: 1,
  title: "Centverteilung",
  inputs: {},
  expected: { summe: "100.00" },
  source: "Anhang D",
  calculation: null,
  status: "submitted" as const,
  approved_by_name: null,
  approved_at: null,
};
const base: AcceptanceState = {
  note: "Benennung offen (V16)",
  cases_total: 58,
  released_total: 0,
  passed_total: 0,
  items: [
    { case_id: "D04", g1_scope: true, current: null, released: null, last_result: null },
    { case_id: "D08", g1_scope: true, current: submitted, released: null, last_result: null },
  ],
};

describe("AcceptanceRegister", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows counts and lets the expert release a submitted version", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.endsWith("/decision")) {
        expect(JSON.parse(String(init?.body))).toEqual({ decision: "approve", name: "Prüferin" });
        return jsonResponse({ ...submitted, status: "approved" });
      }
      return jsonResponse({ ...base, released_total: 1 });
    });
    renderIntl(<AcceptanceRegister initial={base} canManage={false} canApprove />);
    expect(screen.getByTestId("ae01-counts")).toHaveTextContent("0 von 58");
    expect(screen.getByTestId("ae01-note")).toHaveTextContent("V16");
    const approve = screen.getByRole("button", { name: "Freigeben" });
    expect(approve).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Name der fachkundigen Person"), "Prüferin");
    await userEvent.click(approve);
    await waitFor(() => expect(screen.getByTestId("ae01-counts")).toHaveTextContent("1 von 58"));
    expect(calls).toContain(`POST /api/bff/accounting/acceptance/expected/${submitted.id}/decision`);
    expect(screen.queryByRole("button", { name: "Neue Fassung" })).toBeNull();
  });

  it("rejects invalid JSON in the draft form", async () => {
    renderIntl(<AcceptanceRegister initial={base} canManage canApprove={false} />);
    await userEvent.click(screen.getAllByRole("button", { name: "Neue Fassung" })[0]!);
    const expected = screen.getByLabelText("Sollwert (JSON)");
    await userEvent.clear(expected);
    await userEvent.type(expected, "kein json");
    await userEvent.click(screen.getByRole("button", { name: "Entwurf speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("gültiges JSON");
  });
});
