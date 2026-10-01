import { screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AssistantLogPanel } from "./AssistantLogPanel";

const ROW = {
  id: "l1",
  account_id: "a1",
  question: "Wie hoch ist das Hausgeld? [TELEFON]",
  answer: "Das Hausgeld beträgt 250 EUR.",
  mode: "ai",
  status: "answered",
  reason_code: null,
  technical_reason: null,
  sources: [{ document_id: "d1", title: "Wirtschaftsplan" }],
  scope_documents: 2,
  created_at: "2026-10-01T10:00:00Z",
};

describe("AssistantLogPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the masked questions with result, source count and reason", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse([
        ROW,
        { ...ROW, id: "l2", mode: "search", status: "search_hits", question: "Hausgeld", sources: [], technical_reason: "Kein Anbieter freigegeben", reason_code: "provider_not_released" },
      ]),
    );
    renderIntl(<AssistantLogPanel />);
    const panel = await screen.findByTestId("assistant-log");
    expect(await screen.findByText("Wie hoch ist das Hausgeld? [TELEFON]")).toBeInTheDocument();
    expect(fetchMock.mock.calls.at(0)?.[0]).toBe("/api/bff/portal-admin/assistant/log?limit=20");
    expect(panel).toHaveTextContent("KI, beantwortet (1 Quelle)");
    expect(panel).toHaveTextContent("Suche, Treffer");
    expect(panel).toHaveTextContent("Kein Anbieter freigegeben");
  });

  it("shows the empty state and API errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse([]));
    const first = renderIntl(<AssistantLogPanel />);
    expect(await screen.findByText("Noch keine Fragen protokolliert.")).toBeInTheDocument();
    first.unmount();
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ code: "MHVP-AUTH-0003", title: "Keine Berechtigung", status: 403 }, 403));
    renderIntl(<AssistantLogPanel />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
