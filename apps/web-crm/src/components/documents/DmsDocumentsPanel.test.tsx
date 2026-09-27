import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DmsDocumentsPanel } from "./DmsDocumentsPanel";

const PROPERTY = "01920000-0000-7000-8000-000000000523";

const doc = (id: number, title: string, company: string | null) => ({
  id,
  title,
  created: "2026-09-01T08:00:00Z",
  added: null,
  correspondent: null,
  document_type: null,
  tags: [],
  page_count: 1,
  original_file_name: null,
  company,
  preview_url: `/api/v1/dms-documents/${String(id)}/file?kind=preview`,
  download_url: `/api/v1/dms-documents/${String(id)}/file?kind=download`,
});

function urlOf(call: unknown[]): string {
  return String(call[0]);
}

describe("DmsDocumentsPanel", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("filters by the configured company option and shows the company column", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/bff/dms-documents/companies")) {
        return Promise.resolve(
          jsonResponse([
            { option_id: "opt-a", label: "Gesellschaft A" },
            { option_id: "opt-b", label: "Gesellschaft B" },
          ]),
        );
      }
      const filtered = url.includes("company=opt-b");
      const data = filtered ? [doc(2, "Protokoll", "Gesellschaft B")] : [doc(1, "Rechnung", "Gesellschaft A"), doc(2, "Protokoll", "Gesellschaft B")];
      return Promise.resolve(jsonResponse({ data, meta: { page: 1, per_page: 20, total: data.length } }));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<DmsDocumentsPanel entity="property" id={PROPERTY} />);

    expect(await screen.findByText("Rechnung")).toBeInTheDocument();
    const select = await screen.findByLabelText("Gesellschaft");
    expect(screen.getByRole("columnheader", { name: "Gesellschaft" })).toBeInTheDocument();
    expect(screen.getByText("Gesellschaft A", { selector: "td" })).toBeInTheDocument();

    await userEvent.selectOptions(select, "opt-b");

    await waitFor(() => expect(screen.queryByText("Rechnung")).not.toBeInTheDocument());
    expect(screen.getByText("Protokoll")).toBeInTheDocument();
    const listCalls = fetchMock.mock.calls.map(urlOf).filter((u) => u.includes("/dms-documents?"));
    expect(listCalls.at(-1)).toBe(`/api/bff/properties/${PROPERTY}/dms-documents?page=1&page_size=20&company=opt-b`);
  });

  it("hides the filter without company options and maps 502 to not configured", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/companies")) return Promise.resolve(jsonResponse([]));
        return Promise.resolve(jsonResponse({ type: "about:blank", title: "Paperless ist nicht eingerichtet", status: 502, code: "MHVP-DOC-0005" }, 502));
      }),
    );

    renderIntl(<DmsDocumentsPanel entity="ticket" id={PROPERTY} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Paperless nicht eingerichtet");
    expect(screen.queryByLabelText("Gesellschaft")).not.toBeInTheDocument();
  });

  it("maps 503 to unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/companies")) return Promise.resolve(jsonResponse([]));
        return Promise.resolve(jsonResponse({ type: "about:blank", title: "Paperless nicht erreichbar", status: 503, code: "MHVP-DOC-0006" }, 503));
      }),
    );

    renderIntl(<DmsDocumentsPanel entity="property" id={PROPERTY} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Paperless nicht erreichbar");
  });
});
