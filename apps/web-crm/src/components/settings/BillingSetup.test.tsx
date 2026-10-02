import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CostTypeAccountsAdmin } from "./CostTypeAccountsAdmin";
import { HeatingRuleTablesAdmin } from "./HeatingRuleTablesAdmin";

describe("HeatingRuleTablesAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists tables and saves with source, rejecting invalid JSON", async () => {
    const calls: { m: string; u: string; b?: string }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push({ m: init?.method ?? "GET", u: String(input), b: init?.body as string | undefined });
      if ((init?.method ?? "GET") === "GET") return jsonResponse([]);
      return jsonResponse({ id: "t1" });
    });
    renderIntl(<HeatingRuleTablesAdmin canManage />);
    expect(await screen.findByText("Keine Regeltabelle hinterlegt.")).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Speichern" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Gültig ab"), { target: { value: "2026-01-01" } });
    fireEvent.change(screen.getByLabelText("Quelle"), { target: { value: "Amtliche Quelle" } });
    fireEvent.change(screen.getByLabelText(/Zeilen \(JSON\)/), { target: { value: "{kaputt" } });
    await userEvent.click(save);
    expect(await screen.findByText("Die Zeilen sind kein gültiges JSON.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Zeilen \(JSON\)/), { target: { value: "[]" } });
    await userEvent.click(save);
    await waitFor(() => expect(calls.some((c) => c.m === "PUT")).toBe(true));
    const put = calls.find((c) => c.m === "PUT");
    expect(put?.u).toBe("/api/bff/billing/heating-rule-tables");
    expect(JSON.parse(put?.b ?? "{}")).toMatchObject({ kind: "co2_steps", valid_from: "2026-01-01", source: "Amtliche Quelle", review_status: "zu_pruefen" });
  });
});

describe("CostTypeAccountsAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("maps a cost account to a catalogue entry", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.endsWith("/accounting/ledgers")) return jsonResponse([{ id: "L1", name: "WEG Haus" }]);
      if (url.endsWith("/billing/operating-cost-types")) return jsonResponse({ items: [{ code: "grundsteuer", label: "Grundsteuer" }] });
      if (url.includes("/accounts?ledger_id=")) return jsonResponse([{ account_id: "A1", number: "4100", name: "Steuern", operating_cost_type: null, operating_cost_type_label: null, suggested_operating_cost_type: null }]);
      return jsonResponse({});
    });
    renderIntl(<CostTypeAccountsAdmin canManage />);
    const ledger = await screen.findByRole("option", { name: "WEG Haus" });
    await userEvent.selectOptions(ledger.closest("select") as HTMLSelectElement, "L1");
    const select = await screen.findByLabelText("Kostenart 4100");
    await screen.findByRole("option", { name: "Grundsteuer" });
    await userEvent.selectOptions(select, "grundsteuer");
    await waitFor(() => expect(calls).toContain("PUT /api/bff/billing/operating-cost-types/accounts/A1"));
  });
});
