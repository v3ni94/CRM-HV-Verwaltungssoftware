import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PropertyNotices, type PropertyNotice } from "./PropertyNotices";

const PROPERTY = "01920000-0000-7000-8000-0000000000aa";

function notice(overrides: Partial<PropertyNotice> = {}): PropertyNotice {
  return {
    id: "01920000-0000-7000-8000-000000000001",
    property_id: PROPERTY,
    title: "Treppenhausreinigung",
    body: "Ab Oktober freitags.",
    valid_from: "2026-09-20",
    valid_to: null,
    category: null,
    type: "neutral",
    audiences: ["tenant", "owner"],
    document_ids: [],
    read_count: 1,
    recipient_count: 3,
    ended_at: null,
    is_current: true,
    created_at: "2026-09-20T08:00:00Z",
    ...overrides,
  };
}

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PropertyNotices", () => {
  it("lists notices with validity, audience and status", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse([
        notice(),
        notice({ id: "01920000-0000-7000-8000-000000000002", title: "Beendet", ended_at: "2026-09-21T08:00:00Z", is_current: false, audiences: ["owner"] }),
      ]),
    );
    renderIntl(<PropertyNotices propertyId={PROPERTY} />);
    expect(await screen.findByText("Treppenhausreinigung")).toBeInTheDocument();
    expect(screen.getByText(/Gültig 20\.09\.2026 bis auf Weiteres · Mieter, Eigentümer · neutral · gelesen 1 von 3/)).toBeInTheDocument();
    expect(screen.getByText("sichtbar")).toBeInTheDocument();
    expect(screen.getByText("beendet")).toBeInTheDocument();
    // An ended notice has no actions.
    expect(screen.getAllByRole("button", { name: "Beenden" })).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledWith(`/api/bff/properties/${PROPERTY}/notices`, expect.anything());
  });

  it("validates the form and posts a new notice", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return Promise.resolve(jsonResponse(notice({ title: "Neu" }), 201));
      return Promise.resolve(jsonResponse([]));
    });
    renderIntl(<PropertyNotices propertyId={PROPERTY} />);
    expect(await screen.findByText("Keine Aushänge vorhanden.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Aushang anlegen" }));
    await user.click(screen.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte einen Titel eingeben.");
    await user.type(screen.getByLabelText("Titel"), "Neu");
    await user.type(screen.getByLabelText("Text"), "Text des Aushangs");
    await user.click(screen.getByLabelText("Eigentümer"));
    await user.click(screen.getByLabelText("Dienstleister"));
    await user.selectOptions(screen.getByLabelText("Hinweisstufe"), "warning");
    await user.click(screen.getByRole("button", { name: "Anlegen" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        `/api/bff/properties/${PROPERTY}/notices`,
        expect.objectContaining({ method: "POST", body: expect.stringContaining('"audiences":["tenant","provider"]') }),
      ),
    );
    const body = JSON.parse(String(fetchMock.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "POST")?.[1].body)) as Record<string, unknown>;
    expect(body).toMatchObject({ title: "Neu", body: "Text des Aushangs", audiences: ["tenant", "provider"], type: "warning", category: null, document_ids: [], valid_to: null });
  });

  it("ends a notice after confirmation", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("confirm", vi.fn(() => true));
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return Promise.resolve(jsonResponse(notice({ ended_at: "2026-09-26T08:00:00Z", is_current: false })));
      return Promise.resolve(jsonResponse([notice()]));
    });
    renderIntl(<PropertyNotices propertyId={PROPERTY} />);
    await user.click(await screen.findByRole("button", { name: "Beenden" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/bff/notices/01920000-0000-7000-8000-000000000001/end", expect.objectContaining({ method: "POST" })),
    );
  });
});

describe("PropertyNotices feedback (review 26.09.2026)", () => {
  it("asks before ending a notice and confirms the end", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "POST" ? jsonResponse(notice({ ended_at: "2026-09-26T08:00:00Z", is_current: false })) : jsonResponse([notice()])),
    );
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderIntl(<PropertyNotices propertyId={PROPERTY} />);
    await userEvent.click(await screen.findByRole("button", { name: "Beenden" }));
    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining("Treppenhausreinigung"));
    expect(fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === "POST")).toHaveLength(0);
    confirmSpy.mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "Beenden" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Aushang beendet."));
    confirmSpy.mockRestore();
  });
});

describe("PropertyNotices 6.2 fields", () => {
  it("shows level, several attachments and the read quota", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse([notice({ type: "danger", audiences: ["provider"], document_ids: ["a", "b"], read_count: 0, recipient_count: 2 })]),
    );
    renderIntl(<PropertyNotices propertyId={PROPERTY} />);
    expect(await screen.findByText(/Dienstleister · Gefahr · 2 Anlagen · gelesen 0 von 2/)).toBeInTheDocument();
  });

  it("refuses an empty audience and a malformed document id", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse([])));
    renderIntl(<PropertyNotices propertyId={PROPERTY} />);
    await user.click(await screen.findByRole("button", { name: "Aushang anlegen" }));
    await user.type(screen.getByLabelText("Titel"), "T");
    await user.type(screen.getByLabelText("Text"), "B");
    await user.click(screen.getByLabelText("Mieter"));
    await user.click(screen.getByLabelText("Eigentümer"));
    await user.click(screen.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte mindestens eine Zielgruppe wählen.");
    await user.click(screen.getByLabelText("Mieter"));
    await user.type(screen.getByLabelText("Dokument-IDs (optional)"), "kaputt");
    await user.click(screen.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Eine Dokument-ID ist ungültig.");
  });
});
