import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankAccountSelect } from "./BankAccountSelect";
import type { BankAccountOption } from "./bankAccountTypes";

const ACCOUNTS: BankAccountOption[] = [
  {
    id: "0192abcd-0000-7000-8000-000000000011",
    property_id: "0192abcd-0000-7000-8000-000000000001",
    property_number: "801",
    property_name: "Testweg",
    legal_entity_id: "0192abcd-0000-7000-8000-000000000021",
    legal_entity_name: "GdWE Testweg",
    legal_entity_kind: "hoa",
    kind: "hoa",
    iban_masked: "DE02 **** **** 2051",
    bic: null,
    bank_name: "Sparkasse",
    holder: "GdWE Testweg",
    valid_from: "2020-01-01",
    valid_to: null,
    source: "finapi",
    balance: "1234.56",
    balance_as_of: "2026-02-01T00:00:00Z",
    balance_source: "finapi",
    default_for_legal_entity: true,
    assignments: [{ property_id: "0192abcd-0000-7000-8000-000000000001", property_number: "801", property_name: "Testweg", purpose: "hausgeld", is_default: true }],
    recent_transactions: [],
  },
  {
    id: "0192abcd-0000-7000-8000-000000000012",
    property_id: "0192abcd-0000-7000-8000-000000000002",
    property_number: "802",
    property_name: "Mietstraße",
    legal_entity_id: "0192abcd-0000-7000-8000-000000000022",
    legal_entity_name: "Timo Müller",
    legal_entity_kind: "rental_owner",
    kind: "rent",
    iban_masked: "DE89 **** **** 3000",
    bic: null,
    bank_name: "Volksbank",
    holder: "Timo Müller",
    valid_from: "2020-01-01",
    valid_to: null,
    source: "manual",
    balance: null,
    balance_as_of: null,
    balance_source: null,
    default_for_legal_entity: false,
    assignments: [],
    recent_transactions: [],
  },
];

describe("BankAccountSelect", () => {
  afterEach(() => vi.restoreAllMocks());

  it("filters the given options by search text and reports the chosen account", async () => {
    const onChange = vi.fn();
    renderIntl(<BankAccountSelect options={ACCOUNTS} value={null} onChange={onChange} label="Bankkonto" />);
    const input = screen.getByRole("combobox", { name: "Bankkonto" });
    await userEvent.click(input);
    expect(screen.getAllByRole("option")).toHaveLength(2);
    expect(screen.getByText("1.234,56 EUR")).toBeInTheDocument();
    expect(screen.getByText("Standard des Rechtsträgers")).toBeInTheDocument();

    await userEvent.type(input, "volksbank");
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(1);
    const only = options[0]!;
    expect(only).toHaveTextContent("Timo Müller, Volksbank");
    expect(only).toHaveTextContent("Kein Kontostand bekannt");

    await userEvent.click(only);
    expect(onChange).toHaveBeenCalledWith(ACCOUNTS[1]);
  });

  it("shows a hint when the search matches nothing", async () => {
    renderIntl(<BankAccountSelect options={ACCOUNTS} value={null} onChange={() => undefined} />);
    const input = screen.getByRole("combobox");
    await userEvent.type(input, "gibtesnicht");
    expect(screen.getByText("Kein passendes Konto.")).toBeInTheDocument();
  });

  it("loads accounts for a property through the BFF when no options are given", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/bank-account-options")) return jsonResponse([ACCOUNTS[0]]);
      return jsonResponse([]);
    });
    renderIntl(<BankAccountSelect propertyId="0192abcd-0000-7000-8000-000000000001" value={null} onChange={() => undefined} />);
    await userEvent.click(screen.getByRole("combobox"));
    expect(await screen.findByText("GdWE Testweg, Sparkasse (DE02 **** **** 2051)")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/properties/0192abcd-0000-7000-8000-000000000001/bank-account-options");
  });
});
