import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DocumentList } from "./DocumentList";
import type { PortalDocument } from "./types";

const documents: PortalDocument[] = [
  { id: "01920000-0000-7000-8000-00000000000a", title: "Hausordnung", filename: "hausordnung.pdf", created_at: "2026-01-10T10:00:00Z" },
  { id: "01920000-0000-7000-8000-00000000000b", title: "Wirtschaftsplan 2026", filename: "wplan-2026.pdf", created_at: "2026-02-01T10:00:00Z" },
];

beforeEach(() => vi.stubGlobal("fetch", vi.fn()));

describe("DocumentList", () => {
  it("shows the empty notice without documents", () => {
    renderIntl(<DocumentList documents={[]} />);
    expect(screen.getByText("Keine freigegebenen Dokumente.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Suche")).not.toBeInTheDocument();
  });

  it("filters by title or filename and shows the no-results notice", async () => {
    const user = userEvent.setup();
    renderIntl(<DocumentList documents={documents} />);
    expect(screen.getByText("Hausordnung")).toBeInTheDocument();
    const search = screen.getByLabelText("Suche");
    await user.type(search, "wplan");
    expect(screen.queryByText("Hausordnung")).not.toBeInTheDocument();
    expect(screen.getByText("Wirtschaftsplan 2026")).toBeInTheDocument();
    await user.clear(search);
    await user.type(search, "gibt es nicht");
    expect(screen.getByText("Keine Treffer für die aktuelle Auswahl.")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("loads the metadata via the BFF on the first opening only (read receipt 'opened')", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockImplementation(async () =>
      jsonResponse({
        id: documents[0]!.id,
        title: "Hausordnung",
        filename: "hausordnung.pdf",
        created_at: "2026-01-10T10:00:00Z",
        category: "Hausverwaltung",
      }),
    );
    renderIntl(<DocumentList documents={documents} />);
    const toggles = screen.getAllByRole("button", { name: "Details anzeigen" });
    expect(toggles).toHaveLength(2);
    expect(toggles[0]).toHaveAttribute("aria-expanded", "false");
    await user.click(toggles[0] as HTMLElement);
    await waitFor(() => expect(screen.getByText("Hausverwaltung")).toBeInTheDocument());
    expect(screen.getByText("Kategorie")).toBeInTheDocument();
    expect(screen.getByText("10.01.2026")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith(
      `/api/bff/portal/documents/${documents[0]!.id}`,
      expect.objectContaining({ cache: "no-store" }),
    );
    // Closing and reopening keeps the loaded metadata without a second call.
    await user.click(screen.getByRole("button", { name: "Details ausblenden" }));
    await user.click(screen.getAllByRole("button", { name: "Details anzeigen" })[0] as HTMLElement);
    expect(await screen.findByText("Hausverwaltung")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("shows the API error in the detail area", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockImplementation(async () => jsonResponse({ title: "Fehler", detail: "Nicht verfügbar." }, 502));
    renderIntl(<DocumentList documents={documents} />);
    await user.click(screen.getAllByRole("button", { name: "Details anzeigen" })[0] as HTMLElement);
    expect(await screen.findByRole("alert")).toHaveTextContent("Nicht verfügbar.");
  });
});
