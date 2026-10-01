import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { csvHeaders, HeatingImportPanel } from "./HeatingImportPanel";

const PID = "0192abcd-0000-7000-8000-000000000001";
const UID = "0192abcd-0000-7000-8000-000000000002";
const SID = "0192abcd-0000-7000-8000-000000000003";
const IID = "0192abcd-0000-7000-8000-000000000004";

function imp(over: Record<string, unknown> = {}) {
  return {
    id: IID,
    property_id: PID,
    statement_id: null,
    document_id: "d1",
    provider_name: "Messdienst Nord",
    period_from: "2025-01-01",
    period_to: "2025-12-31",
    document_total: "2250.00",
    user_mapping: { "101": { unit_id: UID } },
    rows: [{ user_number: "101", heating_base: "100.00", heating_consumption: "900.00", hot_water_base: "50.00", hot_water_consumption: "200.00", co2_landlord: "0.00", co2_tenant: "0.00" }],
    csv_meta: null,
    status: "draft",
    check_result: null,
    duplicate_ack_reason: null,
    applied_at: null,
    ...over,
  };
}

type Call = { url: string; method: string; body: unknown };

function mock(calls: Call[], state: { row: ReturnType<typeof imp>; checkResult?: unknown }) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: typeof init?.body === "string" ? JSON.parse(init.body) : null });
    if (url.includes("/heating-cost-imports") && method === "POST" && url.endsWith("/check")) return jsonResponse({ ...state.row, status: "checked", check_result: state.checkResult });
    if (url.includes("/heating-cost-imports") && method === "POST" && url.endsWith("/apply")) return jsonResponse({ ...state.row, status: "applied" });
    if (url.includes("/heating-cost-imports")) return jsonResponse([state.row]);
    if (url.includes("/units")) return jsonResponse([{ id: UID, number: "WE 1" }]);
    if (url.includes("/contracts")) return jsonResponse([]);
    if (url.endsWith("/statements")) return jsonResponse([{ id: SID, property_id: PID, period_from: "2025-01-01", period_to: "2025-12-31", status: "draft", version: 1 }]);
    if (url.endsWith("/properties")) return jsonResponse([{ id: PID, number: "001", name: "Parkstraße" }]);
    return jsonResponse({});
  });
}

describe("HeatingImportPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("reads CSV headers without guessing", () => {
    expect(csvHeaders('﻿"Nr";Heizung\r\n1;2', ";")).toEqual(["Nr", "Heizung"]);
  });

  it("lists imports and hides the form without accounting:create", async () => {
    mock([], { row: imp() });
    renderIntl(<HeatingImportPanel permissions={["accounting:read"]} />);
    expect(await screen.findByText("Messdienst Nord")).toBeInTheDocument();
    expect(screen.getByText("2.250,00 EUR")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import anlegen" })).not.toBeInTheDocument();
  });

  it("checks, shows findings and applies a checked import to a draft statement", async () => {
    const calls: Call[] = [];
    const state = { row: imp(), checkResult: { grand_total: "2250.00", findings: [] as string[] } };
    mock(calls, state);
    const user = userEvent.setup();
    renderIntl(<HeatingImportPanel permissions={["accounting:read", "accounting:create"]} />);
    await user.click(await screen.findByRole("button", { name: "Öffnen" }));
    await user.click(await screen.findByRole("button", { name: "Prüfen" }));
    expect(await screen.findByTestId("hci-clean")).toHaveTextContent("2.250,00 EUR");
    // The list refetch is not triggered; the checked row exposes the apply step.
    const select = await screen.findByTestId("hci-statement");
    await user.selectOptions(select, SID);
    await user.click(screen.getByRole("button", { name: "In Abrechnung übernehmen" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/apply"))).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/apply"))?.body).toEqual({ statement_id: SID });
    expect(await screen.findByText("Der Import ist übernommen und gesperrt.")).toBeInTheDocument();
  });

  it("shows blocking findings of the check", async () => {
    const state = { row: imp(), checkResult: { findings: ["Originaldokument der Messdienstabrechnung fehlt."] } };
    mock([], state);
    const user = userEvent.setup();
    renderIntl(<HeatingImportPanel permissions={["accounting:read", "accounting:create"]} />);
    await user.click(await screen.findByRole("button", { name: "Öffnen" }));
    await user.click(await screen.findByRole("button", { name: "Prüfen" }));
    expect(await screen.findByTestId("hci-findings")).toHaveTextContent("Originaldokument der Messdienstabrechnung fehlt.");
  });

  it("requires every CSV column to be mapped before upload", async () => {
    const calls: Call[] = [];
    mock(calls, { row: imp({ rows: [], user_mapping: {} }) });
    const user = userEvent.setup();
    renderIntl(<HeatingImportPanel permissions={["accounting:read", "accounting:create"]} />);
    await user.click(await screen.findByRole("button", { name: "Öffnen" }));
    const file = new File(["Nr;HG;HV;WG;WV;CL;CM\n101;1;2;3;4;0;0\n"], "m.csv", { type: "text/csv" });
    await user.upload(await screen.findByTestId("hci-csv-file"), file);
    const upload = await screen.findByRole("button", { name: "CSV übernehmen" });
    expect(upload).toBeDisabled();
    const map: Record<string, string> = { user_number: "Nr", heating_base: "HG", heating_consumption: "HV", hot_water_base: "WG", hot_water_consumption: "WV", co2_landlord: "CL", co2_tenant: "CM" };
    for (const [f, h] of Object.entries(map)) await user.selectOptions(screen.getByTestId(`hci-col-${f}`), h);
    expect(upload).toBeEnabled();
  });
});
