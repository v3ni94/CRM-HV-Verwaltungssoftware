import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AiPlausibilityCard } from "./AiPlausibilityCard";

const ID = "0192abcd-0000-7000-8000-000000000021";
const HASH = "abcdef0123456789";
const EMPTY = { latest_run: null, latest: null, proposals: [] };
const RESULT = {
  latest_run: { id: "r1", status: "succeeded", error: null },
  latest: {
    id: "p1",
    created_at: "2026-09-26T10:00:00Z",
    proposed: {
      findings: [
        { field: "totals_mismatch", description: "Summen passen nicht zusammen.", severity: "high", position: null, unit: null },
        { field: "key_without_source", description: "Schlüssel ohne Quelle.", severity: "medium", position: "P1", unit: null },
      ],
      overall: "kritisch",
      summary: "Zwei Hinweise.",
      snapshot_hash: HASH,
      model: "m",
    },
  },
  proposals: [],
};

describe("AiPlausibilityCard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("starts a check and lists findings with severity", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(EMPTY))
      .mockResolvedValueOnce(jsonResponse(RESULT, 202));
    renderIntl(<AiPlausibilityCard kind="statements" id={ID} snapshotHash={HASH} />);
    expect(await screen.findByText("Noch keine Prüfung durchgeführt.")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Prüfung starten"));
    expect(await screen.findByText("Summen passen nicht zusammen.")).toBeInTheDocument();
    expect(screen.getByText("hoch")).toBeInTheDocument();
    expect(screen.getByText("mittel")).toBeInTheDocument();
    expect(screen.getByText("Position P1")).toBeInTheDocument();
    expect(screen.getByText("kritisch")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1]?.[0]).toBe(`/api/bff/statements/${ID}/ai-check`);
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("POST");
  });

  it("is disabled without a snapshot and shows a blocked run", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ latest_run: { id: "r2", status: "blocked", error: "Kein freigegebener KI-Anbieter eingerichtet." }, latest: null, proposals: [] }),
    );
    renderIntl(<AiPlausibilityCard kind="hoa/statements" id={ID} snapshotHash={null} />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Kein freigegebener KI-Anbieter"));
    expect(screen.getByText("Prüfung starten")).toBeDisabled();
  });
});
