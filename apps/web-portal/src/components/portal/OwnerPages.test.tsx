import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { HoaAccountTable, formatEur, runningBalances } from "./HoaAccountTable";
import { PropertyContactList } from "./PropertyContactList";
import { ResolutionList } from "./ResolutionList";
import type { HoaAccount, PortalResolution, PropertyContacts } from "./types";

const resolution: PortalResolution = {
  id: "r1",
  number: 3,
  decided_on: "2026-06-20",
  subject: "Sanierung Dach",
  wording: "Das Dach wird saniert.",
  status: "positive",
  kind: "meeting",
  majority_basis: "einfache Mehrheit der Stimmen",
  votes: { principle: "head", yes: "2", no: "0", abstain: "0" },
  legal_entity_name: "WEG Portalstraße 5",
};

describe("ResolutionList", () => {
  it("renders subject, wording, date in TT.MM.JJJJ, result and status", () => {
    renderIntl(<ResolutionList rows={[resolution]} />);
    expect(screen.getByText("Beschluss 3: Sanierung Dach")).toBeInTheDocument();
    expect(screen.getByText("Das Dach wird saniert.")).toBeInTheDocument();
    expect(screen.getByText("angenommen")).toBeInTheDocument();
    expect(screen.getByText(/Beschlossen am 20\.06\.2026/)).toBeInTheDocument();
    expect(screen.getByText(/Ja 2, Nein 0, Enthaltung 0/)).toBeInTheDocument();
    expect(screen.getByText(/Versammlung/)).toBeInTheDocument();
  });

  it("shows the empty notice without rows", () => {
    renderIntl(<ResolutionList rows={[]} />);
    expect(screen.getByText("Keine verkündeten Beschlüsse vorhanden.")).toBeInTheDocument();
  });
});

const contacts: PropertyContacts = {
  property_id: "p1",
  property_number: "851",
  property_name: "WEG Portalstraße",
  address: "Portalstraße 5, 40721 Hilden",
  manager_name: "Verwalter Müller",
  contacts: [{ category: "caretaker", name: "Hausmeisterdienst GmbH", phones: ["+492103111111"] }],
};

describe("PropertyContactList", () => {
  it("renders manager, address and caretaker with phone link", () => {
    renderIntl(<PropertyContactList rows={[contacts]} />);
    expect(screen.getByText("851 WEG Portalstraße")).toBeInTheDocument();
    expect(screen.getByText("Portalstraße 5, 40721 Hilden")).toBeInTheDocument();
    expect(screen.getByText("Verwaltung")).toBeInTheDocument();
    expect(screen.getByText("Verwalter Müller")).toBeInTheDocument();
    expect(screen.getByText("Hausmeister")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "+492103111111" })).toHaveAttribute("href", "tel:+492103111111");
  });

  it("falls back to the central contact without a manager", () => {
    renderIntl(<PropertyContactList rows={[{ ...contacts, manager_name: null, contacts: [] }]} />);
    expect(screen.getByText("Zentrale Erreichbarkeit der Hausverwaltung")).toBeInTheDocument();
    expect(screen.getByText("Weitere Ansprechpartner sind für dieses Objekt nicht hinterlegt.")).toBeInTheDocument();
  });
});

const account: HoaAccount = {
  note: "Kontoübersicht aus gebuchten Einträgen. Keine Abrechnung, keine Rechtsfolge.",
  legacy_note: null,
  contracts: [
    {
      contract_number: "E-0001",
      charges: "1250.00",
      credits: "100.00",
      balance: "1150.00",
      note: null,
      entries: [
        { booking_date: "2026-01-05", due_date: "2026-01-05", text: "Hausgeld Januar", kind: "receivable", direction: "charge", amount: "1250.00", reversed: false },
        { booking_date: "2026-01-20", due_date: null, text: "Zahlung", kind: "debtor_payment", direction: "credit", amount: "100.00", reversed: false },
      ],
    },
  ],
};

describe("HoaAccountTable", () => {
  it("formats amounts as 1.234,56 EUR and dates as TT.MM.JJJJ with the legal note", () => {
    renderIntl(<HoaAccountTable account={account} />);
    expect(screen.getByText(/Keine Abrechnung, keine Rechtsfolge/)).toBeInTheDocument();
    expect(screen.getByText("Vertrag E-0001")).toBeInTheDocument();
    expect(screen.getAllByText("05.01.2026")).toHaveLength(2); // card and table row
    expect(screen.getAllByText("1.250,00 EUR")).toHaveLength(3); // card, table, sum
    expect(screen.getAllByText("100,00 EUR")).toHaveLength(2); // table, sum (card shows -100,00)
    expect(screen.getByText("-100,00 EUR")).toBeInTheDocument();
    expect(screen.getByText("1.150,00 EUR")).toBeInTheDocument();
    expect(screen.getByText("(offener Betrag)")).toBeInTheDocument();
  });

  it("renders a card per booking below md with running balance and the table from md (O01)", () => {
    renderIntl(<HoaAccountTable account={account} />);
    const cards = screen.getByTestId("hoa-cards");
    expect(cards.className).toContain("md:hidden");
    const items = cards.querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0]?.textContent).toContain("Hausgeld Januar");
    expect(items[0]?.textContent).toContain("Saldo danach 1.250,00 EUR");
    expect(items[1]?.textContent).toContain("Saldo danach 1.150,00 EUR");
    const table = screen.getByRole("table", { name: /Gebuchte Sollstellungen und Zahlungen E-0001/ });
    expect(table.parentElement?.className).toContain("hidden");
    expect(table.parentElement?.className).toContain("md:block");
  });

  it("runningBalances adds charges and subtracts credits in cents", () => {
    expect(runningBalances(account.contracts[0]!.entries)).toEqual(["1250.00", "1150.00"]);
    expect(runningBalances([])).toEqual([]);
  });

  it("shows the ledger note without amounts when no ledger exists", () => {
    const empty: HoaAccount = {
      ...account,
      contracts: [{ contract_number: "E-0002", charges: null, credits: null, balance: null, note: "Noch kein Buchungskreis.", entries: [] }],
    };
    renderIntl(<HoaAccountTable account={empty} />);
    expect(screen.getByText("Noch kein Buchungskreis.")).toBeInTheDocument();
    expect(screen.queryByText("Saldo")).not.toBeInTheDocument();
  });

  it("formatEur uses German grouping", () => {
    expect(formatEur("1234.5")).toBe("1.234,50 EUR");
    expect(formatEur("-12.3")).toBe("-12,30 EUR");
  });
});
