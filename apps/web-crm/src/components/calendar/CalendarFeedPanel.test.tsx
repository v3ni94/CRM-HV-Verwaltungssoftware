import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CalendarFeedPanel } from "./CalendarFeedPanel";

describe("CalendarFeedPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the address once after creating and asks before revoking", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "POST") {
        return jsonResponse({ token: "t.x", path: "/api/v1/workspace/calendar-feed/t.x.ics" }, 201);
      }
      return new Response(null, { status: 204 });
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderIntl(<CalendarFeedPanel initialActive={false} />);
    expect(screen.getByText("Kein Abo eingerichtet.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Abo-Adresse erzeugen" }));
    const input = await screen.findByLabelText("Abo-Adresse");
    expect(input).toHaveValue(`${window.location.origin}/api/v1/workspace/calendar-feed/t.x.ics`);
    await userEvent.click(screen.getByRole("button", { name: "Abo widerrufen" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Abo widerrufen" }));
    await waitFor(() => expect(screen.getByText("Kein Abo eingerichtet.")).toBeInTheDocument());
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(screen.queryByLabelText("Abo-Adresse")).toBeNull();
  });

  it("links the ICS download through the BFF (GAG-34)", () => {
    renderIntl(<CalendarFeedPanel initialActive />);
    const link = screen.getByRole("link", { name: "ICS-Datei herunterladen" });
    expect(link).toHaveAttribute("href", "/api/bff/workspace/calendar.ics");
    expect(link).toHaveAttribute("download", "kalender.ics");
  });
});
