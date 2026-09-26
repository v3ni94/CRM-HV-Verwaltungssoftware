import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { FinanceCreate, ItemForm, ReconciliationNotes, ResolutionSelect } from "./FinanceForms";

const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push }) }));
const ID = "0192abcd-0000-7000-8000-000000000090";

describe("W10 finance forms", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates a loan draft with the loan account and opens it", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: ID }, 201));
    renderIntl(<FinanceCreate kind="loan" ledgerId="l1" basePath="/weg/p" loanAccounts={[{ id: "a1", number: "008500", name: "Darlehen" }]} />);
    await userEvent.type(screen.getByLabelText("Darlehensgeber"), "Sparkasse");
    await userEvent.type(screen.getByLabelText("Darlehensbetrag"), "20000,00");
    await userEvent.type(screen.getByLabelText("Zinssatz in Prozent"), "3,5");
    await userEvent.type(screen.getByLabelText("Beginn"), "2025-04-01");
    await userEvent.type(screen.getByLabelText("Zweck"), "Dachsanierung");
    await userEvent.selectOptions(screen.getByLabelText("Darlehenskonto"), "a1");
    await userEvent.click(screen.getByText("Darlehen anlegen"));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/weg/p/darlehen/${ID}`));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/hoa/loans");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toMatchObject({
      ledger_id: "l1",
      principal: "20000.00",
      interest_rate_percent: "3.5",
      account_id: "a1",
    });
  });

  it("refuses a measure classification without facts and legal basis", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: ID }, 201));
    renderIntl(<FinanceCreate kind="measure" ledgerId="l1" basePath="/weg/p" />);
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Fassade");
    await userEvent.type(screen.getByLabelText("Kostenrahmen"), "30000");
    await userEvent.selectOptions(screen.getByLabelText("Einordnung"), "maintenance");
    expect(screen.getByText("Maßnahme anlegen")).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Sachverhalt und Rechtsgrund"), "Erhaltung nach Beschluss");
    expect(screen.getByText("Maßnahme anlegen")).toBeEnabled();
  });

  it("sends a loan item with its journal entry reference", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: "i1", booked: true }, 201));
    renderIntl(<ItemForm target="loans" id={ID} kinds={["disbursement", "repayment", "interest", "fee"]} />);
    await userEvent.selectOptions(screen.getByLabelText("Art"), "repayment");
    await userEvent.type(screen.getByLabelText("Datum"), "2025-05-02");
    await userEvent.type(screen.getByLabelText("Betrag"), "1000");
    await userEvent.type(screen.getByLabelText("Journalbuchung (ID)"), "j1");
    await userEvent.click(screen.getByText("Position erfassen"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/hoa/loans/${ID}/items`);
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({
      kind: "repayment",
      booking_date: "2025-05-02",
      amount: "1000",
      journal_entry_id: "j1",
      note: null,
    });
  });

  it("creates a claim with a resolution of the community (A79)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: ID }, 201));
    renderIntl(
      <FinanceCreate kind="claim" ledgerId="l1" basePath="/weg/p" resolutions={[{ id: "r1", number: 3, decided_on: "10.04.2025", subject: "Sanierung Keller" }]} />,
    );
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Wasserschaden");
    await userEvent.type(screen.getByLabelText("Schadensdatum"), "2025-03-02");
    await userEvent.selectOptions(screen.getByLabelText("Beschluss"), "r1");
    expect(screen.getByText("Nr. 3 · 10.04.2025 · Sanierung Keller")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Versicherungsfall anlegen"));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/weg/p/versicherung/${ID}`));
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toMatchObject({ ledger_id: "l1", title: "Wasserschaden", resolution_id: "r1" });
  });

  it("assigns a resolution to an existing claim with PATCH", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: ID }));
    renderIntl(<ResolutionSelect claimId={ID} resolutionId={null} resolutions={[{ id: "r1", number: 3, decided_on: "10.04.2025", subject: "Sanierung Keller" }]} />);
    expect(screen.getByText("Beschluss zuordnen")).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Beschluss"), "r1");
    await userEvent.click(screen.getByText("Beschluss zuordnen"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/hoa/insurance-claims/${ID}`);
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ resolution_id: "r1" });
  });

  it("offers the takeover code migration_opening as explained difference (A80)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: ID }));
    renderIntl(<ReconciliationNotes statementId={ID} notes={[{ code: "migration_opening", amount: "800.00", note: "Vorperiode Altsystem" }]} />);
    expect(screen.getByLabelText("Art")).toHaveValue("migration_opening");
    expect(screen.getByText("Übernahme aus Altsystem (Vorperiode)")).toBeInTheDocument();
  });

  it("saves the explained differences of the reconciliation with PUT", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: ID }));
    renderIntl(<ReconciliationNotes statementId={ID} notes={[]} />);
    expect(screen.getByText("Erklärungen speichern")).toBeEnabled();
    await userEvent.click(screen.getByText("Zeile hinzufügen"));
    expect(screen.getByText("Erklärungen speichern")).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Betrag mit Vorzeichen"), "300,00");
    await userEvent.type(screen.getByLabelText("Begründung"), "Heizkostenabrechnung 2025");
    await userEvent.click(screen.getByText("Erklärungen speichern"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/hoa/statements/${ID}/reconciliation-notes`);
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PUT");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({
      notes: [{ code: "heating_accrual", amount: "300.00", note: "Heizkostenabrechnung 2025" }],
    });
  });
});

describe("W10 finance forms usability (review 26.09.2026)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("explains a malformed amount and the missing fields instead of a silent disabled button", async () => {
    renderIntl(<ItemForm target="loans" id={ID} kinds={["disbursement", "repayment"]} />);
    expect(screen.getByText("Bitte ausfüllen: Datum, Betrag")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Betrag"), "12,345");
    expect(screen.getByText("Betrag im Format 1.234,56 ohne Vorzeichen.")).toBeInTheDocument();
    expect(screen.getByLabelText("Betrag")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Position erfassen")).toBeDisabled();
  });

  it("confirms a recorded item and returns the focus to the date field", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: "i1", booked: false }, 201));
    renderIntl(<ItemForm target="loans" id={ID} kinds={["disbursement"]} />);
    await userEvent.type(screen.getByLabelText("Datum"), "2025-05-02");
    await userEvent.type(screen.getByLabelText("Betrag"), "250,00");
    await userEvent.click(screen.getByText("Position erfassen"));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Gespeichert."));
    expect(screen.getByLabelText("Betrag")).toHaveValue("");
    expect(screen.getByLabelText("Datum")).toHaveFocus();
  });

  it("names the missing loan fields while the create button is disabled", async () => {
    renderIntl(<FinanceCreate kind="loan" ledgerId="l1" basePath="/weg/p" />);
    expect(screen.getByText("Bitte ausfüllen: Darlehensgeber, Darlehensbetrag, Zinssatz in Prozent, Beginn, Zweck")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Darlehensbetrag"), "abc");
    expect(screen.getByText(/Zahl im Format 1.234,56. \(Darlehensbetrag\)/)).toBeInTheDocument();
  });

  it("shows the API error of a failed status change", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Statuswechsel nicht erlaubt", status: 409 }, 409));
    const { StatusSelect } = await import("./FinanceForms");
    renderIntl(<StatusSelect target="measures" id={ID} status="planned" options={["planned", "resolved"]} group="measureStatus" />);
    await userEvent.selectOptions(screen.getByLabelText("Status"), "resolved");
    await userEvent.click(screen.getByText("Status setzen"));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Statuswechsel nicht erlaubt"));
  });
});
