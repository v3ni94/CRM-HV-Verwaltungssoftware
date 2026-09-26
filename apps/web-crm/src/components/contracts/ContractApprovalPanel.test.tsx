import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ContractApprovalPanel, type PendingContract } from "./ContractApprovalPanel";

const row = (id: string, kind: "ownership" | "tenancy", amount: string, prop = "p1"): PendingContract => ({
  id,
  number: `V-${id}`,
  kind,
  property_id: prop,
  property_number: prop === "p1" ? "336" : "391",
  property_name: prop === "p1" ? "Gladbacher Straße 95" : "Weidenbruch 1",
  unit_id: `u-${id}`,
  unit_number: `0${id}`,
  party_id: `pa-${id}`,
  party_name: `Partei ${id}`,
  start_date: "2026-01-01",
  monthly_amount: amount,
  source: "immoware24:zuordnung",
  notes: null,
});
const rows = [row("1", "ownership", "269.12"), row("2", "ownership", "300.00"), row("3", "tenancy", "745.00", "p2")];

describe("ContractApprovalPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows sums per kind and filters by kind and property", async () => {
    renderIntl(<ContractApprovalPanel initial={rows} canApprove />);
    const sums = screen.getByTestId("approval-sums");
    expect(sums).toHaveTextContent("3 Verträge");
    expect(sums).toHaveTextContent(/Eigentum: 2 \(569,12 EUR je Monat/);
    expect(sums).toHaveTextContent(/Mietverhältnis: 1 \(745,00 EUR je Monat/);
    await userEvent.selectOptions(screen.getByLabelText("Art"), "tenancy");
    expect(screen.getByTestId("approval-sums")).toHaveTextContent("1 Verträge");
    expect(screen.queryByText("Partei 1")).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Art"), "");
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), "p1");
    expect(screen.getByTestId("approval-sums")).toHaveTextContent("2 Verträge");
  });

  it("approves selected rows after confirmation and asks before approving all", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ approved: 1, ids: ["1"] }))
      .mockResolvedValueOnce(jsonResponse({ approved: 2, ids: ["2", "3"] }));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<ContractApprovalPanel initial={rows} canApprove />);
    await userEvent.click(screen.getByLabelText("Vertrag V-1 auswählen"));
    await userEvent.click(screen.getByRole("button", { name: "Ausgewählte freigeben (1)" }));
    expect(confirm.mock.calls[0]?.[0]).toContain("Annahmen des Imports");
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/bff/contracts/approve");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ ids: ["1"] });
    await waitFor(() => expect(screen.queryByText("Partei 1")).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Alle freigeben" }));
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({ all: true });
    expect(await screen.findByText("Keine Verträge mit ausstehender Freigabe.")).toBeInTheDocument();
  });

  it("rejects a single row and does nothing without confirmation", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ id: "2", approval_status: "rejected", end_date: "2026-01-01" }));
    vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderIntl(<ContractApprovalPanel initial={rows} canApprove />);
    const buttons = screen.getAllByRole("button", { name: "Ablehnen" });
    await userEvent.click(buttons[1]!);
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(buttons[1]!);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/bff/contracts/2/reject-import");
    await waitFor(() => expect(screen.queryByText("Partei 2")).not.toBeInTheDocument());
  });

  it("hides actions without contracts:approve", () => {
    renderIntl(<ContractApprovalPanel initial={rows} canApprove={false} />);
    expect(screen.queryByRole("button", { name: "Alle freigeben" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ablehnen" })).not.toBeInTheDocument();
    expect(screen.getByText(/contracts:approve/)).toBeInTheDocument();
  });
});
