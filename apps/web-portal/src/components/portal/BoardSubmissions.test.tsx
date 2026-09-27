import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BoardSubmissions } from "./BoardSubmissions";
import type { PortalBoardSubmission } from "./types";

const open: PortalBoardSubmission = {
  id: "s1",
  kind: "consent",
  title: "Fassade sanieren",
  note: "Bitte Votum bis zur Frist",
  amount: "7500.00",
  due_on: "2026-10-15",
  status: "open",
  overdue: false,
  can_vote: true,
  tally: { approve: 0, reject: 0, comment: 0 },
  member_count: 3,
  my_votes: [],
  created_at: "2026-09-27T10:00:00Z",
};

describe("BoardSubmissions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the empty state", () => {
    renderIntl(<BoardSubmissions initial={[]} />);
    expect(screen.getByText("Keine Vorlage vorhanden.")).toBeInTheDocument();
  });

  it("sends an approval with comment and shows the own vote afterwards", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      expect(String(input)).toBe("/api/bff/portal/board/submissions/s1/votes");
      const body = JSON.parse(String(init?.body));
      expect(body).toEqual({ vote: "approve", comment: "Einverstanden" });
      return jsonResponse(
        {
          ...open,
          tally: { approve: 1, reject: 0, comment: 0 },
          my_votes: [{ id: "v1", vote: "approve", comment: "Einverstanden", created_at: "2026-10-01T10:00:00Z" }],
        },
        201,
      );
    });
    renderIntl(<BoardSubmissions initial={[open]} />);
    expect(screen.getByText("Fassade sanieren")).toBeInTheDocument();
    expect(screen.getByText("Um Votum")).toBeInTheDocument();
    expect(screen.getByText(/Rückmeldung bis 15.10.2026/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Kommentar senden" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Kommentar (bei Kommentar Pflicht)"), "Einverstanden");
    await userEvent.click(screen.getByRole("button", { name: "Zustimmen" }));
    await waitFor(() => expect(screen.getByText("Rückmeldung gespeichert.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Zustimmung: Einverstanden")).toBeInTheDocument();
    expect(screen.getByText(/Bisher: 1 Zustimmung, 0 Ablehnung, 0 Kommentar von 3 Mitgliedern/)).toBeInTheDocument();
  });

  it("offers no vote after the deadline or after closing", () => {
    renderIntl(<BoardSubmissions initial={[{ ...open, id: "s2", overdue: true, can_vote: false }, { ...open, id: "s3", status: "closed", can_vote: false }]} />);
    expect(screen.queryByRole("button", { name: "Zustimmen" })).toBeNull();
    expect(screen.getAllByText("Eine Rückmeldung ist nicht mehr möglich.")).toHaveLength(2);
    expect(screen.getByText(/Frist abgelaufen/)).toBeInTheDocument();
    expect(screen.getByText(/abgeschlossen/)).toBeInTheDocument();
  });
});
