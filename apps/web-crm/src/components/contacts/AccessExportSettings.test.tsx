import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AccessExportSettings } from "./AccessExportSettings";

describe("AccessExportSettings (AE33, AC07-01)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps the conservative default and saves a wider scope", async () => {
    const wide = { third_party_scope: "names", include_internal_notes: true };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(wide));
    renderIntl(<AccessExportSettings initial={{ third_party_scope: "none", include_internal_notes: false }} canEdit={true} />);
    expect(screen.getByLabelText("Angaben zu anderen Personen")).toHaveValue("none");
    const notes = screen.getByLabelText(/Interne Vermerke/);
    expect(notes).not.toBeChecked();
    // GAI-506: further sources off by default.
    expect(screen.getByLabelText(/Vorgänge \(Tickets\)/)).not.toBeChecked();
    await userEvent.selectOptions(screen.getByLabelText("Angaben zu anderen Personen"), "names");
    await userEvent.click(notes);
    await userEvent.click(screen.getByLabelText(/Vorgänge \(Tickets\)/));
    await userEvent.click(screen.getByLabelText(/Portalkonto mit Anmeldeereignissen/));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/bff/contact-access-export-settings");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({
      ...wide,
      include_tickets: true,
      include_communication: false,
      include_documents: false,
      include_portal_account: true,
      include_payments: false,
      include_contracts: false,
    });
    expect(await screen.findByText("Einstellung gespeichert.")).toBeInTheDocument();
  });

  it("shows the server problem", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Keine Berechtigung", status: 403 }, 403));
    renderIntl(<AccessExportSettings initial={{ third_party_scope: "none", include_internal_notes: false }} canEdit={true} />);
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
