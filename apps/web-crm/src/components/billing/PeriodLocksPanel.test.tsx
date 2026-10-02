import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PeriodLocksPanel } from "./PeriodLocksPanel";

const PROPERTY = "0192abcd-0000-7000-8000-000000000041";
const STATEMENT = "0192abcd-0000-7000-8000-000000000042";
const LEDGER = "0192abcd-0000-7000-8000-000000000043";
const LOCK = {
  id: "0192abcd-0000-7000-8000-000000000044",
  period_from: "2025-01-01",
  period_to: "2025-12-31",
  source: "manual",
  reason: "Jahresabschluss",
  active: true,
};

function mockFetch(handler: (url: string, init?: RequestInit) => Response) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => handler(String(input), init));
}

describe("PeriodLocksPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists active locks and states that the statement is locked", async () => {
    const fetchMock = mockFetch((url) =>
      url.includes("/statements/")
        ? jsonResponse({ locks: [LOCK], auto_lock_on_close: true, lock_mode: "hard" })
        : jsonResponse([LOCK]),
    );
    renderIntl(<PeriodLocksPanel propertyId={PROPERTY} statementId={STATEMENT} />);
    expect(await screen.findByText(/01\.01\.2025 bis 31\.12\.2025, Jahresabschluss/)).toBeInTheDocument();
    expect(await screen.findByTestId("statement-period-lock")).toHaveTextContent("besteht eine aktive Periodensperre");
    expect(fetchMock.mock.calls.map((c) => String(c[0]))).toEqual([
      `/api/bff/accounting/period-locks?property_id=${PROPERTY}&active=true`,
      `/api/bff/statements/${STATEMENT}/period-lock`,
    ]);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows the empty state and no create form without ledger and period", async () => {
    mockFetch(() => jsonResponse([]));
    renderIntl(<PeriodLocksPanel propertyId={PROPERTY} />);
    expect(await screen.findByText("Keine aktive Periodensperre für dieses Objekt.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Grund der Sperre")).not.toBeInTheDocument();
  });

  it("creates a lock only with a reason of at least three characters", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    mockFetch((url, init) => {
      calls.push([url, init]);
      return jsonResponse(init?.method === "POST" ? { id: LOCK.id } : []);
    });
    renderIntl(<PeriodLocksPanel propertyId={PROPERTY} ledgerId={LEDGER} periodFrom="2025-01-01" periodTo="2025-12-31" />);
    const button = await screen.findByRole("button", { name: "Zeitraum 01.01.2025 bis 31.12.2025 sperren" });
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Grund der Sperre"), "ab");
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Grund der Sperre"), "c ");
    await userEvent.click(button);
    expect(await screen.findByText("Periodensperre angelegt.")).toBeInTheDocument();
    const post = calls.find(([, init]) => init?.method === "POST")!;
    expect(post[0]).toBe("/api/bff/accounting/period-locks");
    expect(JSON.parse(String(post[1]!.body))).toEqual({
      ledger_id: LEDGER,
      property_id: PROPERTY,
      period_from: "2025-01-01",
      period_to: "2025-12-31",
      reason: "abc",
    });
  });

  it("shows the API error and no success message when creating fails", async () => {
    mockFetch((url, init) =>
      init?.method === "POST" ? jsonResponse({ title: "Keine Freigabeberechtigung", status: 403 }, 403) : jsonResponse([]),
    );
    renderIntl(<PeriodLocksPanel propertyId={PROPERTY} ledgerId={LEDGER} periodFrom="2025-01-01" periodTo="2025-12-31" />);
    await userEvent.type(await screen.findByLabelText("Grund der Sperre"), "Prüfung");
    await userEvent.click(screen.getByRole("button", { name: /sperren/ }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByText("Periodensperre angelegt.")).not.toBeInTheDocument();
  });
});
