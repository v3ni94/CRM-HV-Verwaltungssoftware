import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { SlaBadge } from "./SlaBadge";

const TICKET = "0192abcd-0000-7000-8000-000000000081";
const CLOCK_ID = "0192abcd-0000-7000-8000-000000000082";
const inMinutes = (m: number) => new Date(Date.now() + m * 60_000).toISOString();

const clock = (over: Record<string, unknown> = {}) => ({
  id: CLOCK_ID,
  ticket_id: TICKET,
  rule_id: null,
  started_at: "2026-10-01T08:00:00Z",
  due_response_at: inMinutes(30),
  due_resolution_at: inMinutes(600),
  first_response_at: null,
  resolved_at: null,
  state: "running",
  color: "green",
  ...over,
});

describe("SlaBadge", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing when the ticket has no SLA clock", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Nicht gefunden", status: 404 }, 404));
    const { container } = renderIntl(<SlaBadge ticketId={TICKET} canManage />);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]![0])).toBe(`/api/bff/sla/tickets/${TICKET}/sla`);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the response target until a first response exists", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(clock()));
    renderIntl(<SlaBadge ticketId={TICKET} canManage={false} />);
    expect(await screen.findByText("im Rahmen")).toBeInTheDocument();
    expect(screen.getByText("läuft")).toBeInTheDocument();
    expect(screen.getByText(/Reaktion in \d+ Min\. fällig/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows an overdue resolution target after the first response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(clock({ first_response_at: "2026-10-01T08:10:00Z", due_resolution_at: inMinutes(-90), color: "red" })),
    );
    renderIntl(<SlaBadge ticketId={TICKET} canManage />);
    expect(await screen.findByText("verletzt")).toBeInTheDocument();
    expect(screen.getByText(/Lösung seit \d+ Min\. überfällig/)).toBeInTheDocument();
  });

  it("hides the target and the pause button for finished and breached clocks", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(clock({ state: "done", resolved_at: "2026-10-01T09:00:00Z" })));
    renderIntl(<SlaBadge ticketId={TICKET} canManage />);
    expect(await screen.findByText(/Gelöst am/)).toBeInTheDocument();
    expect(screen.queryByText(/fällig|überfällig/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("pauses a running clock and then offers to resume it", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(clock()))
      .mockResolvedValueOnce(jsonResponse(clock({ state: "paused" })));
    renderIntl(<SlaBadge ticketId={TICKET} canManage />);
    await userEvent.click(await screen.findByRole("button", { name: "Pausieren" }));
    expect(await screen.findByRole("button", { name: "Fortsetzen" })).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(`/api/bff/sla/clocks/${CLOCK_ID}/pause`);
    expect(init.method).toBe("POST");
  });

  it("keeps the clock and shows the error when pausing fails", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(clock()))
      .mockResolvedValueOnce(jsonResponse({ title: "Keine Berechtigung", status: 403 }, 403));
    renderIntl(<SlaBadge ticketId={TICKET} canManage />);
    await userEvent.click(await screen.findByRole("button", { name: "Pausieren" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("läuft")).toBeInTheDocument();
  });
});
