import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { EventDetailDialog, type CalendarEventDetail } from "./EventDetailDialog";

vi.mock("next/navigation", () => ({ usePathname: () => "/kalender", useSearchParams: () => new URLSearchParams() }));

const m = messages.Workspace;
const BASE: CalendarEventDetail = {
  kind: "event",
  title: "Ortstermin",
  date: "2026-10-05",
  source: "default",
  google_event_id: "g1",
  calendar_event_id: null,
  invite_status: "draft",
  attendees: [{ email: "extern@example.org", name: "Frau Extern" }],
  is_stale: false,
};

describe("EventDetailDialog", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends the invitation only after the explicit confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}));
    const onSent = vi.fn();
    renderIntl(<EventDetailDialog item={BASE} onClose={vi.fn()} onSent={onSent} />);
    expect(screen.getByText("05.10.2026")).toBeInTheDocument();
    expect(screen.getByText(m.inviteNotSentYet)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: m.sendInvite }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: m.confirmInviteAction }));
    await waitFor(() => expect(onSent).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/bff/workspace/calendar/google/default/g1/invite");
    expect(JSON.parse(String(init?.body))).toEqual({ confirm: true });
  });

  it("cancel closes the confirmation without sending", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<EventDetailDialog item={BASE} onClose={vi.fn()} onSent={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: m.sendInvite }));
    await userEvent.click(screen.getByRole("button", { name: m.cancel }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("offers no invitation for internal events, sent invitations or without attendees, and shows the stale notice", () => {
    const { unmount } = renderIntl(<EventDetailDialog item={{ ...BASE, source: "internal" }} onClose={vi.fn()} onSent={vi.fn()} />);
    expect(screen.queryByRole("button", { name: m.sendInvite })).toBeNull();
    unmount();
    const second = renderIntl(<EventDetailDialog item={{ ...BASE, invite_status: "invited", is_stale: true }} onClose={vi.fn()} onSent={vi.fn()} />);
    expect(screen.queryByRole("button", { name: m.sendInvite })).toBeNull();
    expect(screen.getByText(m.inviteSent)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(m.staleNotice);
    second.unmount();
    renderIntl(<EventDetailDialog item={{ ...BASE, attendees: [] }} onClose={vi.fn()} onSent={vi.fn()} />);
    expect(screen.queryByRole("button", { name: m.sendInvite })).toBeNull();
  });

  it("shows the API error and keeps onSent unused when the invitation fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Fehler", status: 502, detail: "Google nicht erreichbar" }, 502));
    const onSent = vi.fn();
    renderIntl(<EventDetailDialog item={BASE} onClose={vi.fn()} onSent={onSent} />);
    await userEvent.click(screen.getByRole("button", { name: m.sendInvite }));
    await userEvent.click(screen.getByRole("button", { name: m.confirmInviteAction }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(onSent).not.toHaveBeenCalled();
  });
});
