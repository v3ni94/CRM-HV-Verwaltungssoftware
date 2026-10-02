import { fireEvent, screen, waitFor } from "@testing-library/react";

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

describe("RetentionStatusCard resolution select", () => {
  const fm = vi.fn<typeof fetch>();
  beforeEach(() => {
    fm.mockReset();
    vi.stubGlobal("fetch", fm);
  });

  it("shows the resolution select only with a legal entity", async () => {
    fm.mockResolvedValueOnce(jsonResponse(BASE));
    renderIntl(<RetentionStatusCard documentId={DOC} />);
    await waitFor(() => expect(screen.getByTestId("retention-status")).toBeInTheDocument());
    expect(screen.queryByTestId("retention-resolution-select")).toBeNull();
  });

  it("shows the resolution select for a document linked to a legal entity", async () => {
    fm.mockResolvedValueOnce(jsonResponse(BASE));
    fm.mockResolvedValueOnce(jsonResponse([]));
    renderIntl(<RetentionStatusCard documentId={DOC} legalEntityId="e1" />);
    await waitFor(() => expect(screen.getByTestId("retention-resolution-select")).toBeInTheDocument());
  });
});

describe("RetentionStatusCard hold actions (GAG-26)", () => {
  const fm = vi.fn<typeof fetch>();
  beforeEach(() => {
    fm.mockReset();
    vi.stubGlobal("fetch", fm);
  });

  it("offers no hold action without write permission", async () => {
    fm.mockResolvedValueOnce(jsonResponse(BASE));
    renderIntl(<RetentionStatusCard documentId={DOC} />);
    await waitFor(() => expect(screen.getByTestId("retention-status")).toBeInTheDocument());
    expect(screen.queryByTestId("retention-hold-set")).toBeNull();
    expect(screen.queryByTestId("retention-hold-clear")).toBeNull();
  });

  it("sets a hold with kind and reason through the BFF and reloads the status", async () => {
    fm.mockResolvedValueOnce(jsonResponse(BASE));
    fm.mockResolvedValueOnce(jsonResponse({}));
    fm.mockResolvedValueOnce(jsonResponse({ ...BASE, retention_hold_reason: "Anfechtung Beschluss", retention_hold_kind: "litigation" }));
    renderIntl(<RetentionStatusCard documentId={DOC} canSetHold />);
    await waitFor(() => expect(screen.getByTestId("retention-hold-set")).toBeInTheDocument());
    const button = screen.getByRole("button", { name: "Sperre setzen" });
    fireEvent.change(screen.getByLabelText(/Begründung/), { target: { value: "kurz" } });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Art der Sperre"), { target: { value: "litigation" } });
    fireEvent.change(screen.getByLabelText(/Begründung/), { target: { value: "Anfechtung Beschluss" } });
    fireEvent.click(button);
    await waitFor(() => expect(screen.getByText("Manuelle Löschungssperre")).toBeInTheDocument());
    const [url, init] = fm.mock.calls[1]!;
    expect(String(url)).toBe(`/api/bff/documents/${DOC}/hold`);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ reason: "Anfechtung Beschluss", kind: "litigation" });
    expect(screen.queryByTestId("retention-hold-set")).toBeNull();
  });

  it("lifts a hold with a reason and shows the four eyes refusal of the API", async () => {
    const held = { ...BASE, retention_hold_reason: "Anfechtung", retention_hold_kind: "litigation" };
    fm.mockResolvedValueOnce(jsonResponse(held));
    fm.mockResolvedValueOnce(jsonResponse({ detail: "Eine zweite Person muss aufheben." }, 409));
    renderIntl(<RetentionStatusCard documentId={DOC} canSetHold canClearHold />);
    await waitFor(() => expect(screen.getByTestId("retention-hold-clear")).toBeInTheDocument());
    expect(screen.queryByTestId("retention-hold-set")).toBeNull();
    fireEvent.change(screen.getByLabelText(/Begründung/), { target: { value: "Verfahren beendet" } });
    fireEvent.click(screen.getByRole("button", { name: "Sperre aufheben" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    const [url, init] = fm.mock.calls[1]!;
    expect(String(url)).toBe(`/api/bff/documents/${DOC}/hold`);
    expect(init?.method).toBe("DELETE");
    expect(JSON.parse(String(init?.body))).toEqual({ reason: "Verfahren beendet" });
  });
});
