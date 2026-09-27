import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

import { ContractAllocationValues, type AllocationValueOut } from "./ContractAllocationValues";
import { ContractMandates, type MandateOut } from "./ContractMandates";

const existing: AllocationValueOut = {
  id: "v1",
  contract_id: "c1",
  allocation_key_id: "k1",
  allocation_key_code: "PERS",
  allocation_key_name: "Personen",
  unit_of_measure: "Pers",
  value: "2.00000000",
  valid_from: "2026-01-01",
  valid_to: null,
};

describe("ContractAllocationValues", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists values and records a new one that closes the open predecessor", async () => {
    let body: unknown = null;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "POST" && url === "/api/bff/contracts/c1/allocation-values") {
        body = JSON.parse(String(init.body));
        return jsonResponse({ ...existing, id: "v2", value: "3.00000000", valid_from: "2026-07-01" }, 201);
      }
      return jsonResponse({ detail: "unexpected" }, 500);
    });
    renderIntl(<ContractAllocationValues contractId="c1" values={[existing]} keys={[{ id: "k1", code: "PERS", name: "Personen", unit_of_measure: "Pers" }]} canUpdate startDate="2026-01-01" />);
    expect(screen.getByText("Personen")).toBeInTheDocument();
    expect(screen.getByText("offen")).toBeInTheDocument();

    const form = within(screen.getByTestId("allocation-value-form"));
    await userEvent.type(form.getByLabelText("Wert"), "3");
    await userEvent.clear(form.getByLabelText("Gültig ab"));
    await userEvent.type(form.getByLabelText("Gültig ab"), "2026-07-01");
    await userEvent.click(form.getByRole("button", { name: "Wert erfassen" }));

    await waitFor(() => expect(body).toMatchObject({ allocation_key_id: "k1", value: "3", valid_from: "2026-07-01", valid_to: null }));
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(3));
    // The open predecessor now ends the day before the new value.
    expect(screen.getByText("30.06.2026")).toBeInTheDocument();
    expect(screen.getByText("offen")).toBeInTheDocument();
  });

  it("hides the form without the update permission", () => {
    renderIntl(<ContractAllocationValues contractId="c1" values={[]} keys={[]} canUpdate={false} startDate="2026-01-01" />);
    expect(screen.queryByTestId("allocation-value-form")).not.toBeInTheDocument();
    expect(screen.getByText("Keine Umlagewerte am Vertrag erfasst.")).toBeInTheDocument();
  });
});

describe("ContractMandates", () => {
  it("marks the default mandate and shows payment types and the special levy exclusion", () => {
    const mandate: MandateOut = {
      id: "m1",
      party_id: "p1",
      legal_entity_id: "l1",
      reference: "REF-1",
      creditor_id: "DE98ZZZ09999999999",
      signed_at: "2026-01-01",
      type: "core",
      sequence: "recurring",
      valid_until: null,
      status: "active",
      iban_masked: "DE02 **** **** 2051",
      payment_type_codes: ["rent"],
      exclude_special_levy: true,
    };
    renderIntl(<ContractMandates mandates={[mandate, { ...mandate, id: "m2", reference: "REF-2", payment_type_codes: [], exclude_special_levy: false }]} defaultMandateId="m1" directDebit />);
    expect(screen.getByText("Standardmandat")).toBeInTheDocument();
    expect(screen.getByText("Zusatzmandat")).toBeInTheDocument();
    expect(screen.getByText("rent")).toBeInTheDocument();
    expect(screen.getByText("ohne Sonderumlage")).toBeInTheDocument();
    expect(screen.getByText("alle Ertragsarten")).toBeInTheDocument();
  });
});
