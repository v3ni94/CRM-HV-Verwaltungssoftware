import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { GMAIL_DONE_SYNC_DEFAULTS, GmailDoneSync } from "./GmailDoneSync";

describe("GmailDoneSync", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves the mode and guards with If-Match and keeps done locked without the spike", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/api/bff/tenant/settings") && init?.method === "PATCH") {
        return jsonResponse({ ...GMAIL_DONE_SYNC_DEFAULTS, ...JSON.parse(String(init.body)), version: 8 });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<GmailDoneSync initial={GMAIL_DONE_SYNC_DEFAULTS} version={7} canUpdate />);
    const user = userEvent.setup();
    expect(screen.getByText(/Maßgeblich ist das Sammelpostfach/)).toBeInTheDocument();
    expect(screen.getByTestId("gmail-mode-done")).toBeDisabled();
    expect(screen.getByTestId("gmail-mode-record_only")).toBeChecked();

    await user.click(screen.getByTestId("gmail-gmail_done_closes_ticket"));
    await user.clear(screen.getByTestId("gmail-settle-seconds"));
    await user.type(screen.getByTestId("gmail-settle-seconds"), "4000");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Beruhigungsfrist 0 bis 3600");
    expect(fetchMock).not.toHaveBeenCalled();

    await user.clear(screen.getByTestId("gmail-settle-seconds"));
    await user.type(screen.getByTestId("gmail-settle-seconds"), "120");
    await user.type(screen.getByTestId("gmail-keep-open-labels"), "Warten, Rückfrage");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByText("Gespeichert.")).toBeInTheDocument());
    const [, init] = fetchMock.mock.calls[0]!;
    expect(init).toEqual(
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          gmail_done_sync_mode: "record_only",
          gmail_done_closes_ticket: true,
          gmail_close_assigned_tickets: false,
          gmail_done_on_trash: true,
          gmail_reopen_on_unarchive: true,
          gmail_restore_inbox_on_reopen: false,
          gmail_settle_seconds: 120,
          gmail_reconcile_grace_seconds: 300,
          gmail_keep_open_labels: ["Warten", "Rückfrage"],
        }),
      }),
    );
    expect(new Headers((init as RequestInit).headers).get("if-match")).toBe('"7"');
  });

  it("allows mode done once the spike is confirmed and is read only without the permission", () => {
    renderIntl(
      <GmailDoneSync
        initial={{ ...GMAIL_DONE_SYNC_DEFAULTS, gmail_spike_confirmed_at: "2026-09-28T10:00:00Z" }}
        version={1}
        canUpdate={false}
      />,
    );
    expect(screen.getByTestId("gmail-mode-done")).toBeDisabled();
    expect(screen.getByTestId("gmail-mode-record_only")).toBeDisabled();
    expect(screen.queryByText(/erst nach bestätigtem Test/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Speichern" })).toBeDisabled();
    expect(screen.getByText("Die Änderung erfordert das Recht Mandanteneinstellungen ändern.")).toBeInTheDocument();
  });
});

describe("GmailDoneSync spike confirmation", () => {
  afterEach(() => vi.restoreAllMocks());

  it("confirms the test run with a note and unlocks the mode done", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/api/bff/tenant/settings/gmail-spike-confirm") && init?.method === "POST") {
        return jsonResponse({
          ...GMAIL_DONE_SYNC_DEFAULTS,
          gmail_spike_confirmed_at: "2026-09-29T06:40:00Z",
          version: 9,
        });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<GmailDoneSync initial={GMAIL_DONE_SYNC_DEFAULTS} version={7} canUpdate />);
    const user = userEvent.setup();
    expect(screen.getByTestId("gmail-spike-confirm-button")).toBeDisabled();
    await user.type(screen.getByTestId("gmail-spike-ref"), "29.09.2026 08:38 info@ archiviert");
    await user.click(screen.getByTestId("gmail-spike-confirm-button"));
    await waitFor(() => expect(screen.getByTestId("gmail-mode-done")).toBeEnabled());
    expect(screen.queryByTestId("gmail-spike-confirm")).not.toBeInTheDocument();
    const [, init] = fetchMock.mock.calls[0]!;
    expect(JSON.parse(String(init?.body))).toEqual({ protocol_ref: "29.09.2026 08:38 info@ archiviert" });
  });
});
