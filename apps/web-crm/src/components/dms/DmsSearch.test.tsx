import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DmsSearch } from "./DmsSearch";

const doc = (id: number, title: string) => ({
  id,
  title,
  created: "2026-09-01T08:00:00Z",
  added: null,
  correspondent: "Stadtwerke",
  document_type: "Rechnung",
  tags: ["Objekt 523"],
  page_count: 1,
  original_file_name: null,
  company: "Hausverwaltung Müller GmbH",
});

describe("DmsSearch", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("requires a criterion, searches by object number and text and links the proxy", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/bff/dms-documents/companies")) return Promise.resolve(jsonResponse([]));
      return Promise.resolve(jsonResponse({ data: [doc(7, "Wasserrechnung 2025")], meta: { page: 1, per_page: 25, total: 1 } }));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<DmsSearch />);
    await userEvent.click(screen.getByRole("button", { name: "Suchen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte Suchbegriff, Objekt oder Gesellschaft angeben.");

    await userEvent.type(screen.getByLabelText("Suchbegriff"), "Wasser");
    await userEvent.type(screen.getByLabelText("Objekt"), "5x23");
    await userEvent.click(screen.getByRole("button", { name: "Suchen" }));

    expect(await screen.findByText("Wasserrechnung 2025")).toBeInTheDocument();
    const search = fetchMock.mock.calls.map((c) => String(c[0])).find((u) => u.includes("/dms-documents?"));
    expect(search).toContain("q=Wasser");
    expect(search).toContain("object_number=523");
    expect(screen.getByRole("link", { name: "Vorschau" })).toHaveAttribute("href", "/api/bff/dms-documents/7/file?kind=preview");
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute("href", "/api/bff/dms-documents/7/file?kind=download");
    // Same tab preview and a download attribute instead of target=_blank (ADR 0017).
    expect(screen.getByRole("link", { name: "Vorschau" })).not.toHaveAttribute("target");
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute("download");
  });

  it("shows the configuration hint for 502", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) =>
        Promise.resolve(String(input).endsWith("/companies") ? jsonResponse([]) : jsonResponse({ code: "MHVP-DOC-0005" }, 502)),
      ),
    );
    renderIntl(<DmsSearch />);
    await userEvent.type(screen.getByLabelText("Suchbegriff"), "Protokoll");
    await userEvent.click(screen.getByRole("button", { name: "Suchen" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Paperless nicht eingerichtet"));
  });
});
