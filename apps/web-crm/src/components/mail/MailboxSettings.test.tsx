import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MailboxSettings, type Mailbox } from "./MailboxSettings";

const oauth = { client_id: "cid", configured: true, source: "tenant" as const, redirect_uri: "https://api/cb" };

const box: Mailbox = {
  id: "m1",
  address: "info@example.com",
  kind: "gmail",
  enabled: true,
  has_secret: true,
  is_default: true,
  calendar_enabled: false,
  calendar_id: "primary",
  user_ids: [],
  last_synced_at: null,
  last_error: null,
  push_watch_expires_at: "2026-10-03T10:00:00Z",
  last_push_at: "2026-09-26T09:30:00Z",
  backfill_status: "idle",
  backfill_total: null,
  backfill_done: 0,
  backfill_started_at: null,
  backfill_finished_at: null,
};

describe("MailboxSettings", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the push status read only and starts the full inbox fetch", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/bff/mail/mailboxes/m1/backfill") && init?.method === "POST") {
        return jsonResponse({ ...box, backfill_status: "queued" }, 202);
      }
      if (url.endsWith("/api/bff/mail/mailboxes")) {
        return jsonResponse([{ ...box, backfill_status: "running", backfill_done: 40, backfill_total: 120 }], 200);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(<MailboxSettings oauth={oauth} mailboxes={[box]} members={[]} />);

    expect(screen.getByTestId("push-status").textContent).toContain("Push aktiv bis");
    expect(screen.getByTestId("push-status").textContent).toContain("letzter Push");
    expect(screen.queryByTestId("backfill-status")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Posteingang vollständig abrufen" }));
    await waitFor(() => expect(screen.getByTestId("backfill-status").textContent).toContain("Vollabruf wartet"));
    expect(screen.getByRole("button", { name: "Posteingang vollständig abrufen" })).toBeDisabled();
    expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/mailboxes/m1/backfill") && init?.method === "POST")).toBe(true);
  });

  it("shows an inactive push and a finished backfill", () => {
    renderIntl(
      <MailboxSettings
        oauth={oauth}
        mailboxes={[{ ...box, push_watch_expires_at: null, last_push_at: null, backfill_status: "done", backfill_done: 120, backfill_total: 120, backfill_finished_at: "2026-09-26T10:00:00Z" }]}
        members={[]}
      />,
    );
    expect(screen.getByTestId("push-status").textContent).toContain("Push nicht aktiv");
    expect(screen.getByTestId("backfill-status").textContent).toContain("Vollabruf abgeschlossen");
    expect(screen.getByTestId("backfill-status").textContent).toContain("120 Nachrichten");
  });
});
