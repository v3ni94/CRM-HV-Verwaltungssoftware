import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { nextTargets, StatementStatusActions } from "./StatementStatusActions";

const URL = "/api/bff/billing/owner-statements/0192abcd-0000-7000-8000-000000000022";

describe("nextTargets", () => {
  it("mirrors the API table", () => {
    expect(nextTargets("internally_approved", false)).toEqual(["board_reviewed", "issued"]);
    expect(nextTargets("internally_approved", true)).toEqual(["board_reviewed", "resolved"]);
    expect(nextTargets("resolved", true)).toEqual(["issued"]);
    expect(nextTargets("due", false)).toEqual(["posted"]);
    expect(nextTargets("locked", true)).toEqual([]);
  });
});

describe("StatementStatusActions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("posts the transition with the entry ids", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: "x", status: "posted" }));
    const changed = vi.fn();
    renderIntl(<StatementStatusActions url={URL} status="due" hoa={false} gate="G3" onChanged={changed} />);
    await userEvent.type(screen.getByLabelText("Gebuchte Buchungen (IDs, durch Komma getrennt)"), "a1, b2");
    await userEvent.click(screen.getByText("Als gebucht erfassen"));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    const [path, init] = fetchMock.mock.calls[0]!;
    expect(String(path)).toBe(`${URL}/transition`);
    expect(JSON.parse(String(init?.body))).toEqual({ target: "posted", entry_ids: ["a1", "b2"] });
  });

  it("shows the refusal of the API", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ code: "MHVP-GATE-0001", title: "Freigabestufe nicht erteilt", status: 403, detail: "G3 gesperrt" }, 403),
    );
    renderIntl(
      <StatementStatusActions
        url={URL}
        status="board_reviewed"
        hoa={false}
        gate="G3"
        log={[{ from: "calculated", to: "internally_approved", by: null, at: "2026-10-01T08:00:00Z", note: "geprüft" }]}
        onChanged={vi.fn()}
      />,
    );
    expect(screen.queryByText("Beschluss erfassen")).not.toBeInTheDocument();
    expect(screen.getByText(/geprüft/)).toBeInTheDocument();
    await userEvent.click(screen.getByText("Ausgeben"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("lists the status history and shows an empty state", () => {
    const log = [
      { from: "calculated", to: "internally_approved", by: null, at: "2026-09-01T08:00:00Z", note: "geprüft" },
      { from: "internally_approved", to: "issued", by: null, at: "2026-09-02T08:00:00Z", note: null },
    ];
    const { unmount } = renderIntl(<StatementStatusActions url={URL} status="issued" hoa={false} gate="G3" log={log} onChanged={vi.fn()} />);
    expect(screen.getByText("Statusverlauf")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText(/geprüft/)).toBeInTheDocument();
    unmount();
    renderIntl(<StatementStatusActions url={URL} status="calculated" hoa={false} gate="G3" onChanged={vi.fn()} />);
    expect(screen.getByText("Noch kein Statuswechsel.")).toBeInTheDocument();
  });
});
