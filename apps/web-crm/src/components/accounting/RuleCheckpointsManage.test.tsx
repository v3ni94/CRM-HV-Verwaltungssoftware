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

  it("confirms a check point with name and date", async () => {
    const calls: { u: string; b?: string }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push({ u: `${init?.method ?? "GET"} ${String(input)}`, b: init?.body as string | undefined });
      if ((init?.method ?? "GET") === "GET")
        return jsonResponse([
          { id: "c1", title: "Nachrüstfrist", effective_from: "2026-10-15", source_status: "Q1", change_reason: "", state: "due", days_until: 0 },
        ]);
      return jsonResponse({});
    });
    renderIntl(<RuleCheckpointsManage />);
    await screen.findByText("Nachrüstfrist");
    fireEvent.click(screen.getByRole("button", { name: "Bestätigen" }));
    const ok = screen.getByRole("button", { name: "Bestätigen" });
    expect(ok).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Bestätigt durch"), { target: { value: "RA Muster" } });
    fireEvent.change(screen.getByLabelText("Bestätigt am"), { target: { value: "2026-10-02" } });
    fireEvent.click(ok);
    await waitFor(() => expect(calls.some((c) => c.u === "POST /api/bff/accounting/rule-versions/c1/confirm")).toBe(true));
    expect(JSON.parse(calls.find((c) => c.u.endsWith("/confirm"))?.b ?? "{}")).toEqual({ confirmed_by: "RA Muster", confirmed_on: "2026-10-02" });
  });
});
