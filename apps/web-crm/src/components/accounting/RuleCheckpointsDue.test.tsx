import { screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { RuleCheckpointsDue } from "./RuleCheckpointsDue";

describe("RuleCheckpointsDue", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists due check points with the hint that they have no legal effect", async () => {
    const urls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      urls.push(String(input));
      return jsonResponse([
        { id: "r1", rule_id: "W07", version: 2, title: "Prüfpunkt Aufteilung", effective_from: "2026-09-30", status: "draft", change_reason: "Jahresprüfung" },
      ]);
    });
    renderIntl(<RuleCheckpointsDue />);
    expect(await screen.findByText(/W07 Prüfpunkt Aufteilung/)).toBeInTheDocument();
    expect(urls).toEqual(["/api/bff/accounting/rule-versions/due-checkpoints"]);
    expect(screen.getByText("30.09.2026")).toBeInTheDocument();
    expect(screen.getByTestId("rule-checkpoints").textContent).toMatch(/ohne Rechtsfolge/);
  });

  it("shows the empty state and keeps the notice", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    renderIntl(<RuleCheckpointsDue />);
    await waitFor(() => expect(screen.getByText("Keine Prüfpunkte fällig.")).toBeInTheDocument());
    expect(screen.getByTestId("rule-checkpoints").textContent).toMatch(/ohne Rechtsfolge/);
  });

  it("shows an error message when the call fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Fehler" }, 500));
    renderIntl(<RuleCheckpointsDue />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
