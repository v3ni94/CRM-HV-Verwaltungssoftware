import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { NewTicket } from "./NewTicket";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

describe("NewTicket", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("requires a title and description before submitting", async () => {
    const user = userEvent.setup();
    renderIntl(<NewTicket />);
    await user.click(screen.getByRole("button", { name: "Melden" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte einen Titel eingeben.");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("submits title and description and shows the confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: "t1" }, 201));
    renderIntl(<NewTicket />);
    await user.type(screen.getByLabelText("Titel"), "Wasserschaden");
    await user.type(screen.getByLabelText("Beschreibung"), "Rohrbruch im Bad");
    await user.click(screen.getByRole("button", { name: "Melden" }));
    await waitFor(() => expect(screen.getByText("Meldung wurde übermittelt.")).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(
      "/api/bff/portal/tickets",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ title: "Wasserschaden", description: "Rohrbruch im Bad" }),
      }),
    );
  });
});
