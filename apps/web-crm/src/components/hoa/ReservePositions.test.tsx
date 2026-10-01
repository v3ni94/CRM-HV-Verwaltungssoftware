import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ReserveMovementList, ReservePosition } from "./ReservePositions";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
const DACH = "0192abcd-0000-7000-8000-000000000601";
const STATEMENT = "0192abcd-0000-7000-8000-000000000602";
const reserve = { id: DACH, name: "Dach", purpose: null, opening_balance: "10000.00", opening_year: 2024 };

describe("Reserve positions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the development per year", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        years: [
          { year: 2025, opening: "10000.00", contributions: "0.00", contribution_basis: "planned", withdrawals: "1500.00", taxes: "0.00", fees: "5.00", interest: "20.00", closing: "8515.00", source: "plan" },
        ],
      }),
    );
    renderIntl(<ReservePosition reserve={reserve} year={2025} />);
    await userEvent.click(screen.getByRole("button", { name: "Entwicklung anzeigen" }));
    await waitFor(() => expect(screen.getByRole("table")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/hoa/reserves/${DACH}/development?year=2025`);
    expect(screen.getByText(/8\.515,00/)).toBeInTheDocument();
  });

  it("patches name and opening balance with a dot amount", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: DACH }));
    renderIntl(<ReservePosition reserve={reserve} year={2025} />);
    await userEvent.click(screen.getByRole("button", { name: "Ändern" }));
    const opening = screen.getByLabelText("Anfangsbestand (erfasst)");
    await userEvent.clear(opening);
    await userEvent.type(opening, "9000,50");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ name: "Dach", opening_balance: "9000.50", opening_year: 2024, bank_account_id: null, account_id: null });
    expect(refresh).toHaveBeenCalled();
  });

  it("sends bank account and ledger account chosen in the edit form", async () => {
    const BANK = "0192abcd-0000-7000-8000-000000000611";
    const ACC = "0192abcd-0000-7000-8000-000000000612";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: DACH }));
    renderIntl(
      <ReservePosition
        reserve={reserve}
        year={2025}
        bankAccounts={[{ id: BANK, label: "Sparkasse DE12 ****" }]}
        accounts={[{ id: ACC, label: "1360 Rücklage Dach" }]}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Ändern" }));
    await userEvent.selectOptions(screen.getByLabelText("Bankkonto der Rücklage"), BANK);
    await userEvent.selectOptions(screen.getByLabelText("Buchungskonto der Rücklage"), ACC);
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toMatchObject({ bank_account_id: BANK, account_id: ACC });
  });

  it("lists movements and removes one in the draft", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([{ id: "m1", reserve_id: DACH, kind: "fee", amount: "5.00", purpose: "Kontoführung", receipt_linked: false }]))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    renderIntl(<ReserveMovementList statementId={STATEMENT} reserves={[reserve]} editable />);
    await userEvent.click(screen.getByRole("button", { name: "Einträge anzeigen" }));
    await waitFor(() => expect(screen.getByText("Beleg fehlt", { exact: false })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Entfernen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe(`/api/bff/hoa/statements/${STATEMENT}/reserve-movements/m1`);
    await waitFor(() => expect(screen.queryByText("Kontoführung", { exact: false })).not.toBeInTheDocument());
  });
});
