import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TransactionMatcher } from "./TransactionMatcher";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const TX = "0192abcd-0000-7000-8000-000000000002";
const OI = "0192abcd-0000-7000-8000-000000000003";

describe("TransactionMatcher", () => {
  afterEach(() => vi.restoreAllMocks());

  it("books a partial payment against the remaining amount after confirmation", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse({
          candidates: [{ open_item_id: OI, remaining: "300.00", score: 90, reasons: ["Betrag passt"] }],
          unambiguous_open_item_id: OI,
          note: "Vorschlag, keine Buchung.",
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ journal_entry_id: "x", number: "2026-1" }, 201));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<TransactionMatcher txId={TX} amount="250.00" />);
    await userEvent.click(screen.getByText("Vorschläge"));
    expect(await screen.findByText("eindeutig")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Zuordnen und buchen"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string);
    expect(body).toEqual({ settlements: [{ open_item_id: OI, amount: "250.00" }] });
  });

  it("ignores only with a reason", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    vi.spyOn(window, "prompt").mockReturnValue("ab");
    renderIntl(<TransactionMatcher txId={TX} amount="10.00" />);
    await userEvent.click(screen.getByText("Ignorieren"));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
