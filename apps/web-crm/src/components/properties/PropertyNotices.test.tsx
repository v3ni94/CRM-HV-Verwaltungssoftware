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
    audience: "all",
    document_id: null,
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
        notice({ id: "01920000-0000-7000-8000-000000000002", title: "Beendet", ended_at: "2026-09-21T08:00:00Z", is_current: false, audience: "owner" }),
      ]),
    );
    renderIntl(<PropertyNotices propertyId={PROPERTY} />);
    expect(await screen.findByText("Treppenhausreinigung")).toBeInTheDocument();
    expect(screen.getByText(/Gültig 20\.09\.2026 bis auf Weiteres · Mieter und Eigentümer/)).toBeInTheDocument();
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
    await user.selectOptions(screen.getByLabelText("Zielgruppe"), "tenant");
    await user.click(screen.getByRole("button", { name: "Anlegen" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        `/api/bff/properties/${PROPERTY}/notices`,
        expect.objectContaining({ method: "POST", body: expect.stringContaining('"audience":"tenant"') }),
      ),
    );
    const body = JSON.parse(String(fetchMock.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "POST")?.[1].body)) as Record<string, unknown>;
    expect(body).toMatchObject({ title: "Neu", body: "Text des Aushangs", audience: "tenant", valid_to: null, document_id: null });
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
