import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { RuleCheckpointsManage } from "./RuleCheckpointsManage";

describe("RuleCheckpointsManage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists, adds and withdraws check points", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push(`${init?.method ?? "GET"} ${String(input)}`);
      if ((init?.method ?? "GET") === "GET")
        return jsonResponse([
          { id: "c1", title: "Nachrüstfrist", effective_from: "2026-10-15", source_status: "Q1", change_reason: "", state: "upcoming", days_until: 14 },
        ]);
      return jsonResponse({}, 201);
    });
    renderIntl(<RuleCheckpointsManage />);
    expect(await screen.findByText("Nachrüstfrist")).toBeInTheDocument();
    expect(screen.getByText("in Vorfrist")).toBeInTheDocument();
    expect(screen.getByTestId("rule-checkpoints-manage").textContent).toMatch(/ohne Rechtsfolge/);
    fireEvent.click(screen.getByRole("button", { name: "Zurückziehen" }));
    await waitFor(() =>
      expect(calls).toContain("POST /api/bff/accounting/rule-versions/c1/withdraw"),
    );
  });
});
