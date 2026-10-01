import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalFormElementTypes } from "./PortalFormElementTypes";

const SOURCE = "abgeleitet aus den Portalfunktionen (Abschnitt 14), Abgleich mit der Typenliste des Altportals offen (AA14-01)";
const ROWS = [
  { type: "address", kind: "input", value_format: "Anschrift", rule: "2 bis 5 Zeilen", needs_options: false, required_allowed: true, source_status: SOURCE },
  { type: "divider", kind: "display", value_format: "Trennlinie", rule: "kein Wert", needs_options: false, required_allowed: false, source_status: SOURCE },
];

describe("PortalFormElementTypes", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads nothing before it is opened, then lists types, rules and the source status", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(ROWS));
    const user = userEvent.setup();
    renderIntl(<PortalFormElementTypes />);
    expect(fetchMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Elementtypen und Prüfregeln anzeigen" }));
    expect(fetchMock.mock.calls.at(0)?.[0]).toBe("/api/bff/portal-admin/forms/element-types");
    const box = await screen.findByTestId("portal-form-types");
    expect(box).toHaveTextContent("2 Elementtypen");
    expect(box).toHaveTextContent("Anschrift");
    expect(box).toHaveTextContent("2 bis 5 Zeilen");
    expect(box).toHaveTextContent("Abgleich mit der Typenliste des Altportals offen (AA14-01)");
    await user.click(screen.getByRole("button", { name: "Elementtypen und Prüfregeln ausblenden" }));
    expect(screen.queryByTestId("portal-form-types")).toBeNull();
    // opened again: no second request
    await user.click(screen.getByRole("button", { name: "Elementtypen und Prüfregeln anzeigen" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows the error when the list cannot be loaded", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Verboten", status: 403, detail: "Keine Berechtigung." }, 403));
    const user = userEvent.setup();
    renderIntl(<PortalFormElementTypes />);
    await user.click(screen.getByRole("button", { name: "Elementtypen und Prüfregeln anzeigen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Keine Berechtigung.");
  });
});
