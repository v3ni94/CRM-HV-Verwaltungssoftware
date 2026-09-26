import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";
import type { DmsDocumentPage } from "@/lib/objektakte-dms";

import { DmsDocuments } from "./DmsDocuments";

const PAGE: DmsDocumentPage = {
  count: 2,
  page: 1,
  page_size: 50,
  results: [
    {
      id: 9001,
      title: "Teilungserklärung",
      doc_type: "Teilungserklärung",
      category: "02_Stammakte",
      subfolder: null,
      status: "filed",
      drive_file_id: "drive-9001",
      drive_url: "https://drive.google.com/file/d/drive-9001/view",
      sha256: "a".repeat(64),
      filed_at: "2026-09-24T08:00:00Z",
      mime_type: "application/pdf",
      size_bytes: 1234,
      crm_document_id: "0192abcd-0000-7000-8000-000000000001",
    },
    {
      id: 9002,
      title: "Energieausweis",
      doc_type: null,
      category: "02_Stammakte",
      subfolder: "Energie",
      status: "filed",
      drive_file_id: null,
      drive_url: null,
      sha256: "b".repeat(64),
      filed_at: null,
      mime_type: null,
      size_bytes: null,
      crm_document_id: null,
    },
  ],
};

describe("DmsDocuments", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the documents with the Drive jump and the CRM link", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(PAGE));
    renderIntl(<DmsDocuments number="291" />);
    const table = await screen.findByTestId("dms-documents");
    expect(table).toHaveTextContent("Teilungserklärung");
    expect(table).toHaveTextContent("24.09.2026");
    expect(table).toHaveTextContent("02_Stammakte / Energie");
    expect(screen.getByText("In Drive öffnen")).toHaveAttribute("href", "https://drive.google.com/file/d/drive-9001/view");
    expect(screen.getByText("CRM-Dokument")).toHaveAttribute("href", "/dokumente/0192abcd-0000-7000-8000-000000000001");
    expect(screen.getByText("Nicht verknüpft")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/integrations/objektakte/objects/291/documents?page=1&page_size=50",
      expect.anything(),
    );
  });

  it("links the documents and reports the counts", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "POST")
        return jsonResponse({ object_number: "291", property_id: null, total: 3, created: 1, linked: 1, updated: 0, unchanged: 0, invalid: 1 });
      return jsonResponse(PAGE);
    });
    renderIntl(<DmsDocuments number="291" />);
    await screen.findByTestId("dms-documents");
    await userEvent.click(screen.getByTestId("dms-link"));
    await waitFor(() => expect(screen.getByTestId("dms-link-result")).toBeInTheDocument());
    expect(screen.getByTestId("dms-link-result")).toHaveTextContent("1 neu angelegt, 1 vorhandenen Dokumenten zugeordnet");
    const post = fetchMock.mock.calls.find((c) => c[1]?.method === "POST");
    expect(post?.[0]).toBe("/api/bff/integrations/objektakte/objects/291/documents/link");
  });

  it("shows the problem message when objektakte is unavailable", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ title: "objektakte nicht erreichbar", detail: "objektakte meldet HTTP 500.", status: 502 }, 502),
    );
    renderIntl(<DmsDocuments number="291" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("objektakte meldet HTTP 500.");
  });
});
