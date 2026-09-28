import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { contractLabel, HandoverContractLink } from "./HandoverContractLink";

const BASE = "/api/bff/handover/protocols/01920000-0000-7000-8000-000000000060";
const UNIT = "01920000-0000-7000-8000-000000000005";
const OLD = "01920000-0000-7000-8000-00000000c001";
const NEW = "01920000-0000-7000-8000-00000000c002";

describe("HandoverContractLink", () => {
  afterEach(() => vi.restoreAllMocks());

  it("builds the label without dashes", () => {
    expect(
      contractLabel({ id: OLD, number: "MV-0001", kind: "tenancy", party_name: "Mustermann, Erika", start_date: "2025-01-01", end_date: "2026-09-30" }),
    ).toBe("MV-0001, Mustermann, Erika, 01.01.2025 bis 30.09.2026");
  });

  it("shows the linked contract and saves a new link through the patch", async () => {
    const calls: { url: string; method: string; body: string | null }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? init.body : null });
      if (url.startsWith("/api/bff/contracts?unit_id="))
        return jsonResponse([
          { id: OLD, number: "MV-0001", kind: "tenancy", party_name: "Mustermann, Erika", start_date: "2025-01-01", end_date: "2026-09-30" },
          { id: NEW, number: "MV-0002", kind: "tenancy", party_name: "Neu, Max", start_date: "2026-10-01", end_date: null },
        ]);
      if (method === "PATCH") return jsonResponse({ id: "x" });
      return jsonResponse({}, 404);
    });
    const onChanged = vi.fn(async () => {});
    renderIntl(
      <HandoverContractLink
        base={BASE}
        unitId={UNIT}
        contract={{ id: OLD, number: "MV-0001", kind: "tenancy", party_name: "Mustermann, Erika", start_date: "2025-01-01", end_date: "2026-09-30", unit_id: UNIT }}
        disabled={false}
        onChanged={onChanged}
        onError={vi.fn()}
      />,
    );
    expect(screen.getByRole("link", { name: "MV-0001, Mustermann, Erika, 01.01.2025 bis 30.09.2026" })).toHaveAttribute("href", `/vertraege/${OLD}`);
    expect(screen.getByText("(Mietvertrag)")).toBeInTheDocument();
    await screen.findByRole("option", { name: "MV-0002, Neu, Max, 01.10.2026" });
    expect(screen.getByRole("button", { name: "Verknüpfung speichern" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Vertrag der Einheit"), NEW);
    await userEvent.click(screen.getByRole("button", { name: "Verknüpfung speichern" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    const patch = calls.find((c) => c.method === "PATCH");
    expect(patch?.url).toBe(BASE);
    expect(JSON.parse(patch?.body ?? "{}")).toEqual({ contract_id: NEW });
  });

  it("asks for a unit first and hides the picker on a locked protocol", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    const { unmount } = renderIntl(
      <HandoverContractLink base={BASE} unitId={null} contract={null} disabled={false} onChanged={vi.fn(async () => {})} onError={vi.fn()} />,
    );
    expect(screen.getByText("Kein Vertrag verknüpft.")).toBeInTheDocument();
    expect(screen.getByText("Zur Verknüpfung zuerst eine Einheit aus dem Bestand wählen.")).toBeInTheDocument();
    unmount();
    renderIntl(
      <HandoverContractLink base={BASE} unitId={UNIT} contract={null} disabled onChanged={vi.fn(async () => {})} onError={vi.fn()} />,
    );
    expect(screen.queryByLabelText("Vertrag der Einheit")).not.toBeInTheDocument();
  });
});
