import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { UprotokollImport } from "./UprotokollImport";

describe("UprotokollImport (GAI-615)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("needs a file for the preview and a preview before the takeover", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ rows: 3, applied: false }));
    renderIntl(<UprotokollImport />);
    expect(screen.getByRole("button", { name: "Vorschau" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Übernehmen" })).toBeDisabled();
    await userEvent.upload(screen.getByLabelText("Exportdatei"), new File(["x"], "u.csv", { type: "text/csv" }));
    expect(screen.getByRole("button", { name: "Übernehmen" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Vorschau" }));
    expect(await screen.findByTestId("uprotokoll-result")).toHaveTextContent('"rows": 3');
    expect(String(fetchMock.mock.calls[0]![0])).toContain("mode=preview");
    expect(screen.getByRole("button", { name: "Übernehmen" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Übernehmen" }));
    await screen.findByTestId("uprotokoll-result");
    expect(String(fetchMock.mock.calls[1]![0])).toContain("mode=apply");
  });

  it("shows an error and keeps the takeover locked", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Ungültig", status: 422 }, 422));
    renderIntl(<UprotokollImport />);
    await userEvent.upload(screen.getByLabelText("Exportdatei"), new File(["x"], "u.csv"));
    await userEvent.click(screen.getByRole("button", { name: "Vorschau" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Übernehmen" })).toBeDisabled();
  });
});
