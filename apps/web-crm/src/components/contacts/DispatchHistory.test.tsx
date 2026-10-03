import { fireEvent, screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DispatchHistory } from "./DispatchHistory";

const ID = "11111111-1111-7111-8111-111111111111";

describe("DispatchHistory (GAL-307)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the status history of the dispatch", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse([{ id: "e1", job_id: "j1", status: "submitted", source: "provider", detail: "angenommen", occurred_at: "2026-10-01T10:00:00Z" }]),
    );
    renderIntl(<DispatchHistory dispatchId={ID} />);
    fireEvent.click(screen.getByRole("button", { name: "Verlauf anzeigen" }));
    expect(await screen.findByText(/submitted · provider · angenommen/)).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0]![0])).toBe(`/api/bff/postal/dispatches/${ID}/history`);
  });

  it("shows an empty state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]));
    renderIntl(<DispatchHistory dispatchId={ID} />);
    fireEvent.click(screen.getByRole("button", { name: "Verlauf anzeigen" }));
    expect(await screen.findByText("Kein Verlauf vom Postdienst vorhanden.")).toBeInTheDocument();
  });
});
