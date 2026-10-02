import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MaintenanceAdmin } from "./MaintenanceAdmin";

const win = (phase: string) => ({
  id: "w1",
  starts_at: "2026-11-01T20:00:00Z",
  ends_at: "2026-11-01T22:00:00Z",
  text_de: "Wartung der Datenbank",
  text_en: "DB maintenance",
  notice_hours: null,
  cancelled_at: null,
  phase,
});

describe("MaintenanceAdmin (GAH-407)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the empty state", async () => {
    fetchMock.mockImplementation(async () => jsonResponse([]));
    renderIntl(<MaintenanceAdmin />);
    expect(await screen.findByText("Keine Wartungsfenster erfasst.")).toBeInTheDocument();
  });

  it("shows the load error", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ code: "X", title: "Nur für Plattformadministratoren", status: 403 }, 403));
    renderIntl(<MaintenanceAdmin />);
    expect(await screen.findByText("Nur für Plattformadministratoren")).toBeInTheDocument();
  });

  it("offers cancel only for open phases and patches the window", async () => {
    fetchMock.mockImplementation(async (input, init) =>
      jsonResponse(init?.method === "PATCH" ? {} : [win("announced"), { ...win("ended"), id: "w2" }]),
    );
    renderIntl(<MaintenanceAdmin />);
    expect(await screen.findByText("Angekündigt")).toBeInTheDocument();
    const cancel = screen.getAllByRole("button", { name: "Absagen" });
    expect(cancel).toHaveLength(1);
    await userEvent.click(cancel[0]!);
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => c[1]?.method === "PATCH")).toBe(true));
    const patch = fetchMock.mock.calls.find((c) => c[1]?.method === "PATCH");
    expect(String(patch?.[0])).toBe("/api/bff/platform/maintenance-windows/w1");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ cancel: true });
  });

  it("announces a window with ISO timestamps", async () => {
    fetchMock.mockImplementation(async (input, init) => jsonResponse(init?.method === "POST" ? {} : []));
    renderIntl(<MaintenanceAdmin />);
    await screen.findByText("Keine Wartungsfenster erfasst.");
    await userEvent.type(screen.getByLabelText("Beginn"), "2026-11-01T20:00");
    await userEvent.type(screen.getByLabelText("Ende"), "2026-11-01T22:00");
    await userEvent.type(screen.getByLabelText("Text Deutsch"), "Wartung");
    await userEvent.type(screen.getByLabelText("Text Englisch"), "Maintenance");
    await userEvent.click(screen.getByRole("button", { name: "Ankündigen" }));
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => c[1]?.method === "POST")).toBe(true));
    const post = fetchMock.mock.calls.find((c) => c[1]?.method === "POST");
    const body = JSON.parse(String(post?.[1]?.body));
    expect(body.text_de).toBe("Wartung");
    expect(body.notice_hours).toBeNull();
    expect(body.starts_at).toMatch(/^2026-11-01T\d{2}:00:00\.000Z$/);
  });
});
