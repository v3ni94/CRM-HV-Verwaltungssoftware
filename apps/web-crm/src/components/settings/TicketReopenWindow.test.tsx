import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketReopenWindow } from "./TicketReopenWindow";

describe("TicketReopenWindow", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves the window in days and rejects values outside 0 to 3650", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/api/bff/tenant/settings") && init?.method === "PATCH") {
        return jsonResponse({ ticket_reopen_window_days: JSON.parse(String(init.body)).ticket_reopen_window_days });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<TicketReopenWindow initial={30} canUpdate />);
    const user = userEvent.setup();
    const input = screen.getByTestId("ticket-reopen-window-days");
    expect(input).toHaveValue(30);
    expect(screen.getByText(/entsteht ein Folgeticket/)).toBeInTheDocument();

    await user.clear(input);
    await user.type(input, "4000");
    await user.click(screen.getByRole("button", { name: "Frist speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("zwischen 0 und 3650");
    expect(fetchMock).not.toHaveBeenCalled();

    await user.clear(input);
    await user.type(input, "14");
    await user.click(screen.getByRole("button", { name: "Frist speichern" }));
    await waitFor(() => expect(screen.getByText("Gespeichert.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/tenant/settings",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ ticket_reopen_window_days: 14 }) }),
    );
  });

  it("is read only without the update permission", () => {
    renderIntl(<TicketReopenWindow initial={30} canUpdate={false} />);
    expect(screen.getByTestId("ticket-reopen-window-days")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Frist speichern" })).toBeDisabled();
    expect(screen.getByText("Die Änderung erfordert das Recht Mandanteneinstellungen ändern.")).toBeInTheDocument();
  });
});
