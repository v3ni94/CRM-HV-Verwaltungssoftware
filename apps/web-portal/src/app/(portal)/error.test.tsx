import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import PortalError from "./error";

describe("PortalError", () => {
  it("shows a German notice with retry and a way back, without technical details", async () => {
    const user = userEvent.setup();
    const reset = vi.fn();
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    renderIntl(<PortalError error={new Error("HTTP 500")} reset={reset} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Die Seite konnte nicht geladen werden.");
    expect(screen.queryByText(/HTTP 500/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zur Übersicht" })).toHaveAttribute("href", "/start");
    await user.click(screen.getByRole("button", { name: "Erneut versuchen" }));
    expect(reset).toHaveBeenCalledTimes(1);
  });
});
