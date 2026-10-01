import { screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { RetentionStatusCard, type RetentionStatus } from "./RetentionStatusCard";

const DOC = "01920000-0000-7000-8000-00000000000d";
const BASE: RetentionStatus = {
  document_id: DOC,
  retention_until: "2027-12-31",
  retention_hold_reason: null,
  retention_hold_kind: null,
  procedure_hold: null,
  ticket_hold: null,
  permanent_record: false,
  deletion_blocker: "Die Aufbewahrungsfrist ist nicht abgelaufen.",
};

describe("RetentionStatusCard", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("reads the status through the BFF and shows period, resolution reference and blocker", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ...BASE, retention_resolution_id: "res-1" }));
    renderIntl(<RetentionStatusCard documentId={DOC} />);
    await waitFor(() => expect(screen.getByTestId("retention-status")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/documents/${DOC}/retention-status`);
    expect(screen.getByText(/31\.12\.2027/)).toBeInTheDocument();
    expect(screen.getByTestId("retention-resolution")).toHaveTextContent("res-1");
    expect(screen.getByText("Keine Sperre")).toBeInTheDocument();
    expect(screen.queryByTestId("retention-four-eyes")).toBeNull();
  });

  it("shows hold reason, kind and the four eyes note for a manual and an automatic hold", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ...BASE,
        retention_hold_reason: "Anfechtung",
        retention_hold_kind: "litigation",
        procedure_hold: "Rechtsstreit (Prozess)",
        hold_set_by_four_eyes_required: true,
        deletion_blocker: "Löschungssperre: Anfechtung",
      }),
    );
    renderIntl(<RetentionStatusCard documentId={DOC} />);
    await waitFor(() => expect(screen.getByTestId("retention-holds")).toBeInTheDocument());
    expect(screen.getByText("Manuelle Löschungssperre")).toBeInTheDocument();
    expect(screen.getByText("Automatische Sperre durch offenes Verfahren")).toBeInTheDocument();
    expect(screen.getByText("Sperrgrund: Rechtsstreit")).toBeInTheDocument();
    expect(screen.getByTestId("retention-blocker")).toHaveTextContent("Löschung gesperrt: Löschungssperre: Anfechtung");
    expect(screen.getByTestId("retention-four-eyes")).toBeInTheDocument();
  });

  it("shows an alert when the status cannot be loaded", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "nicht gefunden" }, 404));
    renderIntl(<RetentionStatusCard documentId={DOC} />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
