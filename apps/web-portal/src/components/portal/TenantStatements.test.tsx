import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { TenantStatementDetail, TenantStatementList, euro, type TenantStatementDetailData } from "./TenantStatements";

const item = {
  statement_id: "11111111-1111-1111-1111-111111111111",
  contract_id: "22222222-2222-2222-2222-222222222222",
  period_from: "2025-01-01",
  period_to: "2025-12-31",
  version: 1,
  status: "issued",
  unit_number: "01",
  costs: "300.00",
  advances_paid: "250.00",
  balance: "50.00",
  has_pdf: true,
};

const detail: TenantStatementDetailData = {
  ...item,
  positions: [{ label: "Grundsteuer", basis: "Wohnfläche", allocation_key: "Wohnfläche", amount_total: "400.00", own_share: "200.00" }],
  explanations: {
    key: { code: "portal_tenant_statement_key", released: true, text: "Freigegebener Text Schlüssel" },
    consumption: { code: "c", released: false, text: "Erläuterung noch nicht freigegeben." },
    advance: { code: "a", released: false, text: "Erläuterung noch nicht freigegeben." },
    balance: { code: "b", released: false, text: "Erläuterung noch nicht freigegeben." },
  },
  delivered_at: null,
  read_receipt: { first: "2026-10-02T08:00:00Z", last: "2026-10-02T08:00:00Z" },
  receipt_note: "Indiz für den Abruf.",
  note: "Hinweis",
};

describe("TenantStatements", () => {
  it("formats amounts in German format", () => {
    expect(euro("1234.5")).toBe("1.234,50 EUR");
  });

  it("shows the empty note when nothing is released", () => {
    renderIntl(<TenantStatementList items={[]} note="Nicht freigeschaltet." />);
    expect(screen.getByText("Nicht freigeschaltet.")).toBeInTheDocument();
    expect(screen.getByText("Keine ausgegebene Abrechnung vorhanden.")).toBeInTheDocument();
  });

  it("lists own statements with result and link", () => {
    renderIntl(<TenantStatementList items={[item]} note="Hinweis" />);
    expect(screen.getByText("Abrechnung 01.01.2025 bis 31.12.2025, Einheit 01")).toBeInTheDocument();
    expect(screen.getByText("Nachzahlung 50,00 EUR")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Abrechnung ansehen" })).toHaveAttribute(
      "href",
      `/nebenkosten/${item.statement_id}/${item.contract_id}`,
    );
  });

  it("renders detail with share, explanations, placeholder and PDF link", () => {
    renderIntl(<TenantStatementDetail data={{ ...detail, balance: "-20.00" }} />);
    expect(screen.getByTestId("ts-balance")).toHaveTextContent("Guthaben 20,00 EUR");
    expect(screen.getByText("200,00 EUR")).toBeInTheDocument();
    expect(screen.getByTestId("ts-explanation-key")).toHaveTextContent("Freigegebener Text Schlüssel");
    expect(screen.getByTestId("ts-explanation-balance")).toHaveTextContent("Erläuterung noch nicht freigegeben.");
    expect(screen.getByRole("link", { name: "Abrechnung als PDF herunterladen" })).toHaveAttribute(
      "href",
      `/api/portal-files/portal/tenant-statements/${item.statement_id}/contracts/${item.contract_id}/pdf`,
    );
    expect(screen.getByText(/Erstmals abgerufen am 02.10.2026/)).toBeInTheDocument();
  });
});
