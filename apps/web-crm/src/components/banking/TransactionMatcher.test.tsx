import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TransactionMatcher } from "./TransactionMatcher";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const TX = "0192abcd-0000-7000-8000-000000000002";
const OI = "0192abcd-0000-7000-8000-000000000003";
const LEDGER = "0192abcd-0000-7000-8000-000000000004";
const CONTRACT = "0192abcd-0000-7000-8000-000000000005";

function proposals(extra: Partial<{ ai: unknown[]; enabled: boolean }> = {}) {
  return {
    stage1: [
      {
        source: "rule",
        kind: "debtor_payment",
        confidence: 0.9,
        reasoning: ["Bankregel „Hausgeld“ trifft zu"],
        account_number: "1400",
        rule_id: "r1",
        splits: [{ open_item_id: OI, amount: "250.00", contract_id: CONTRACT }],
        unambiguous: false,
      },
      {
        source: "match",
        kind: "partial",
        confidence: 0.65,
        reasoning: ["Vertragsnummer im Verwendungszweck", "Teilzahlung"],
        account_number: "1400",
        splits: [{ open_item_id: OI, amount: "250.00", contract_id: CONTRACT }],
        unambiguous: false,
      },
    ],
    ai: extra.ai ?? [],
    ai_stage: {
      enabled: extra.enabled ?? false,
      blocked_reason: extra.enabled
        ? null
        : "KI-Kontierung ist nicht freigegeben: Mandantenschalter aus.",
    },
    note: "Vorschläge, keine Buchung.",
    ledger_id: LEDGER,
  };
}

describe("TransactionMatcher", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows source, confidence and reasoning per proposal and books the proposed split", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(proposals()))
      .mockResolvedValueOnce(
        jsonResponse({ journal_entry_id: "x", number: "2026-1" }, 201),
      );
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<TransactionMatcher txId={TX} amount="250.00" />);
    await userEvent.click(screen.getByText("Vorschläge"));
    expect(await screen.findByText("Regel")).toBeInTheDocument();
    expect(screen.getByText("Abgleich")).toBeInTheDocument();
    expect(screen.getByText("Konfidenz 90 %")).toBeInTheDocument();
    expect(screen.getByText("Konfidenz 65 %")).toBeInTheDocument();
    expect(screen.getByText("Teilzahlung")).toBeInTheDocument();
    expect(screen.getByText(/KI-Stufe nicht aktiv/)).toBeInTheDocument();
    const openItemLinks = screen.getAllByRole("link", { name: "Offener Posten" });
    expect(openItemLinks[0]).toHaveAttribute("href", `/buchhaltung/${LEDGER}#open-item-${OI}`);
    const contractLinks = screen.getAllByRole("link", { name: "Vertrag" });
    expect(contractLinks[0]).toHaveAttribute("href", `/vertraege/${CONTRACT}`);
    // In app pages open in the same tab (ADR 0017).
    expect(openItemLinks[0]).not.toHaveAttribute("target");
    expect(contractLinks[0]).not.toHaveAttribute("target");
    await userEvent.click(screen.getAllByText("Zuordnen und buchen")[1]!);
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string);
    expect(body).toEqual({
      settlements: [{ open_item_id: OI, amount: "250.00" }],
    });
  });

  it("lists AI proposals with source KI and confidence when the stage is active", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(
        proposals({
          enabled: true,
          ai: [
            {
              id: "p1",
              decision: "open",
              source: "ai",
              kind: "posting",
              confidence: 0.42,
              reasoning: "Betrag und Zweck passen zu O1.",
              account_number: "1400",
              proposed: { splits: [] },
            },
          ],
        }),
      ),
    );
    renderIntl(<TransactionMatcher txId={TX} amount="250.00" />);
    await userEvent.click(screen.getByText("Vorschläge"));
    expect(await screen.findByText("KI")).toBeInTheDocument();
    expect(screen.getByText("Konfidenz 42 %")).toBeInTheDocument();
    expect(screen.getByText(/KI-Stufe aktiv/)).toBeInTheDocument();
  });

  it("ignores only with a reason", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    vi.spyOn(window, "prompt").mockReturnValue("ab");
    renderIntl(<TransactionMatcher txId={TX} amount="10.00" />);
    await userEvent.click(screen.getByText("Ignorieren"));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the object period lock and disables the book buttons (GAH-401)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ ...proposals(), object_period_lock: { locked: true, code: "MHVP-ACC-0030" } }),
    );
    renderIntl(<TransactionMatcher txId={TX} amount="250.00" />);
    await userEvent.click(screen.getByText("Vorschläge"));
    expect(await screen.findByTestId("period-lock-hint")).toHaveTextContent("MHVP-ACC-0030");
    for (const b of screen.getAllByRole("button", { name: "Zuordnen und buchen" })) expect(b).toBeDisabled();
  });
});
