import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DepositList, type DepositRow } from "./DepositList";

const row = (over: Partial<DepositRow>): DepositRow => ({
  id: "d1",
  contract_id: "c1",
  contract_number: "MV-0001",
  property_id: "p1",
  property_number: "P001",
  unit_id: "u1",
  unit_number: "W01",
  party_name: "Erika Mieter",
  kind: "savings_book",
  status: "active",
  amount_due: "1500.00",
  received: "1500.00",
  balance: "1500.00",
  outstanding: "0.00",
  valid_from: "2026-01-01",
  valid_to: null,
  contract_end_date: null,
  ...over,
});

describe("DepositList", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists deposits per tenancy and filters by status and open amount", async () => {
    const rows = [
      row({}),
      row({ id: "d2", contract_number: "MV-0002", property_id: "p2", property_number: "P002", status: "open", received: "0.00", balance: "0.00", outstanding: "900.00" }),
    ];
    renderIntl(<DepositList rows={rows} />);
    expect(screen.getByText("MV-0001")).toBeInTheDocument();
    expect(screen.getByText("MV-0002")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Nur mit offenem Sollbetrag"));
    expect(screen.queryByText("MV-0001")).toBeNull();
    expect(screen.getByText("MV-0002")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Nur mit offenem Sollbetrag"));
    await userEvent.selectOptions(screen.getByTestId("deposit-filter-property"), "p1");
    expect(screen.queryByText("MV-0002")).toBeNull();
    await userEvent.selectOptions(screen.getByTestId("deposit-filter-status"), "settled");
    expect(screen.getByText("Keine Einträge vorhanden.")).toBeInTheDocument();
  });

  it("shows account, legal entity, interest and the block note on demand", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockResolvedValueOnce(jsonResponse([{ id: "d1", property_bank_account_id: "a1", interest_rule: "Sparbuchzins" }]))
      .mockResolvedValueOnce(
        jsonResponse([{ id: "a1", legal_entity_id: "e1", kind: "deposit", iban_masked: "DE00 **** 1234", bank_name: "Sparkasse", holder: "Hausverwaltung Müller GmbH Mietkautionen", segregated: true }]),
      )
      .mockResolvedValueOnce(jsonResponse([{ id: "e1", name: "Vermieter Musterstraße 1" }]))
      .mockResolvedValueOnce(
        jsonResponse([
          { id: "i1", amount: "10.10", status: "confirmed" },
          { id: "i2", amount: "5.05", status: "confirmed" },
          { id: "i3", amount: "7.00", status: "draft" },
          { id: "i4", amount: "9.00", status: "discarded" },
        ]),
      );
    renderIntl(<DepositList rows={[row({})]} />);
    await userEvent.click(screen.getByRole("button", { name: "Konto und Zinsen" }));
    const detail = await screen.findByTestId("deposit-detail");
    await waitFor(() => expect(within(detail).getByTestId("deposit-entity")).toHaveTextContent("Vermieter Musterstraße 1"));
    expect(within(detail).getByTestId("deposit-account")).toHaveTextContent("Sparkasse DE00 **** 1234");
    expect(within(detail).getByTestId("deposit-interest-confirmed")).toHaveTextContent("15,15 EUR");
    expect(within(detail).getByTestId("deposit-block")).toHaveTextContent("nicht Objektgeld: getrennt");
  });

  it("flags a deposit without account", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([{ id: "d1", property_bank_account_id: null, interest_rule: null }]));
    renderIntl(<DepositList rows={[row({})]} />);
    await userEvent.click(screen.getByRole("button", { name: "Konto und Zinsen" }));
    expect(await screen.findByText("Kein Kautionskonto zugeordnet")).toBeInTheDocument();
    expect(screen.getByTestId("deposit-block")).toHaveTextContent("Prüfhinweis");
  });
});
