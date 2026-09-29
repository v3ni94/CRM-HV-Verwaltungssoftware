import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AssetReportActions, AssetReportCreate, LoanAllocationForm } from "./AssetReportForms";

const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push }) }));
const ID = "0192abcd-0000-7000-8000-000000000091";

describe("M24-02 asset report and M24-03 loan display forms", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates an asset report draft with the reserve values and opens it", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: ID }, 201));
    renderIntl(<AssetReportCreate ledgerId="l1" basePath="/weg/p" />);
    await userEvent.type(screen.getByLabelText("Stichtag"), "2025-12-31");
    await userEvent.clear(screen.getByLabelText("Rücklage Anfangsbestand 01.01."));
    await userEvent.type(screen.getByLabelText("Rücklage Anfangsbestand 01.01."), "2000,00");
    await userEvent.click(screen.getByText("Vermögensbericht anlegen"));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/weg/p/vermoegensbericht/${ID}`));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/hoa/asset-reports");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toMatchObject({
      ledger_id: "l1",
      as_of: "2025-12-31",
      reserve_opening: "2000.00",
      reserve_withdrawals: "0.00",
    });
  });

  it("calculates and saves manual items with a decimal comma, hides actions once issued", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: ID }));
    renderIntl(<AssetReportActions id={ID} status="draft" manualItems={[{ label: "Heizöl", amount: "350,00", note: null }]} />);
    await userEvent.click(screen.getByText("Berechnen und abstimmen"));
    await waitFor(() => expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/hoa/asset-reports/${ID}/calculate`));
    await userEvent.click(screen.getByText("Positionen speichern"));
    await waitFor(() => expect(fetchMock.mock.calls[1]?.[0]).toBe(`/api/bff/hoa/asset-reports/${ID}`));
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({ manual_items: [{ label: "Heizöl", amount: "350.00", note: null }] });
    expect(screen.queryByText("Ausgabe freigeben (G4)")).toBeNull();
  });

  it("shows issue and pdf only when calculated and nothing editable when issued", () => {
    renderIntl(<AssetReportActions id={ID} status="calculated" manualItems={[]} />);
    expect(screen.getByText("Ausgabe freigeben (G4)")).toBeTruthy();
    expect(screen.getByText("PDF-Entwurf").getAttribute("href")).toBe(`/api/bff/hoa/asset-reports/${ID}/pdf`);
    // In app file: same tab, so an installed app keeps its session (ADR 0017).
    expect(screen.getByText("PDF-Entwurf")).not.toHaveAttribute("target");
  });

  it("saves the loan display with key, components and basis via PUT", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: ID }));
    renderIntl(
      <LoanAllocationForm
        statementId="s1"
        loans={[{ id: "d1", label: "Sparkasse DL-A" }]}
        keys={[{ id: "k1", code: "MEA", name: "Miteigentumsanteile" }]}
        current={[]}
      />,
    );
    await userEvent.click(screen.getByText("Position hinzufügen"));
    expect((screen.getByText("Darlehensausweis speichern") as HTMLButtonElement).disabled).toBe(true);
    await userEvent.selectOptions(screen.getByLabelText("Darlehen"), "d1");
    await userEvent.selectOptions(screen.getByLabelText("Verteilerschlüssel"), "k1");
    await userEvent.type(screen.getByLabelText("Grundlage (Beschluss, Vertrag)"), "Beschluss 12.05.2025 TOP 4");
    await userEvent.click(screen.getByLabelText("Tilgung"));
    await userEvent.click(screen.getByText("Darlehensausweis speichern"));
    await waitFor(() => expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/hoa/statements/s1/loan-allocation"));
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PUT");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({
      loans: [{ loan_id: "d1", allocation_key_id: "k1", components: ["interest"], basis: "Beschluss 12.05.2025 TOP 4" }],
    });
  });
});
