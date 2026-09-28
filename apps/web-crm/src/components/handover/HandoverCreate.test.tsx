import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HandoverCreate } from "./HandoverCreate";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
}));

const PROPERTY = "01920000-0000-7000-8000-000000000840";
const UNIT = "01920000-0000-7000-8000-000000000005";
const CONTRACT = "01920000-0000-7000-8000-00000000c001";
const PROTOCOL = "01920000-0000-7000-8000-0000000000aa";

describe("HandoverCreate", () => {
  afterEach(() => vi.restoreAllMocks());

  it("offers the contracts of the chosen unit and sends the contract with the protocol", async () => {
    const calls: { url: string; method: string; body: string | null }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? init.body : null });
      if (url.endsWith(`/properties/${PROPERTY}/units`)) return jsonResponse([{ id: UNIT, number: "05", label: "WE 05" }]);
      if (url.startsWith(`/api/bff/contracts?unit_id=${UNIT}`))
        return jsonResponse([
          { id: CONTRACT, number: "MV-0001", kind: "tenancy", party_name: "Mustermann, Erika", start_date: "2025-01-01", end_date: null },
        ]);
      if (url === "/api/bff/handover/protocols" && method === "POST") return jsonResponse({ id: PROTOCOL }, 201);
      return jsonResponse({}, 404);
    });

    renderIntl(<HandoverCreate properties={[{ id: PROPERTY, label: "840 Übergabehaus" }]} />);
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), PROPERTY);
    await screen.findByRole("option", { name: "05 (WE 05)" });
    expect(screen.getByLabelText("Vertrag")).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Einheit"), UNIT);
    await screen.findByRole("option", { name: "MV-0001, Mustermann, Erika, 01.01.2025" });
    await userEvent.selectOptions(screen.getByLabelText("Vertrag"), CONTRACT);
    await userEvent.click(screen.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith(`/makler/uebergabe/${PROTOCOL}`));
    const created = calls.find((c) => c.method === "POST");
    expect(JSON.parse(created?.body ?? "{}")).toEqual({ kind: "rental", unit_id: UNIT, contract_id: CONTRACT });
  });

  it("sends no contract for a manual object", async () => {
    const calls: { url: string; method: string; body: string | null }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? init.body : null });
      if (url === "/api/bff/handover/protocols" && method === "POST") return jsonResponse({ id: PROTOCOL }, 201);
      if (method === "PATCH") return jsonResponse({ id: PROTOCOL });
      return jsonResponse({}, 404);
    });
    renderIntl(<HandoverCreate properties={[]} />);
    await userEvent.click(screen.getByTestId("handover-object-manual"));
    await userEvent.type(screen.getByLabelText("Straße"), "Musterweg");
    await userEvent.click(screen.getByRole("button", { name: "Anlegen" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(JSON.parse(calls.find((c) => c.method === "POST")?.body ?? "{}")).toEqual({ kind: "rental" });
  });
});
