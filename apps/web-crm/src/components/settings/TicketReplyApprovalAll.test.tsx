import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketReplyApprovalAll } from "./TicketReplyApprovalAll";

describe("TicketReplyApprovalAll", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the brake off by default with the note and patches the tenant setting", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/bff/tenant/settings") && init?.method === "PATCH") {
        return jsonResponse({ ticket_reply_approval_all: JSON.parse(String(init.body)).ticket_reply_approval_all });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(<TicketReplyApprovalAll initial={false} canUpdate />);
    expect(screen.getByTestId("ticket-reply-approval-all-status")).toHaveTextContent("aus");
    expect(screen.getByText(/Jede Änderung wird protokolliert/)).toBeInTheDocument();
    expect(screen.getByText(/Kennzeichen je Mitglied/)).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("checkbox"));

    await waitFor(() => expect(screen.getByTestId("ticket-reply-approval-all-status")).toHaveTextContent("an"));
    expect(screen.getByText("Gespeichert.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/tenant/settings",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ ticket_reply_approval_all: true }) }),
    );
  });

  it("is read only without the update permission", () => {
    renderIntl(<TicketReplyApprovalAll initial={false} canUpdate={false} />);
    expect(screen.getByRole("checkbox")).toBeDisabled();
    expect(screen.getByText("Die Änderung erfordert das Recht Mandanteneinstellungen ändern.")).toBeInTheDocument();
  });

  it("shows the error when the change is refused", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ title: "Verboten", status: 403, detail: "Keine Berechtigung." }, 403),
    );
    renderIntl(<TicketReplyApprovalAll initial={false} canUpdate />);
    await userEvent.setup().click(screen.getByRole("checkbox"));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByTestId("ticket-reply-approval-all-status")).toHaveTextContent("aus");
  });
});
