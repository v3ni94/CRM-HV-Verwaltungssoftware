import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { StatementOutputsPanel } from "./StatementOutputsPanel";

const BASE = "/api/bff/billing/owner-statements/0192abcd-0000-7000-8000-000000000041";
const DOC = "0192abcd-0000-7000-8000-000000000042";

describe("StatementOutputsPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists filed outputs, files new ones and shows the text marking", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
      .mockResolvedValueOnce(jsonResponse({ items: [{ part: "letter", document_id: DOC }] }, 201))
      .mockResolvedValueOnce(jsonResponse({ items: [{ document_id: DOC, origin: "owner_statement_letter", title: "Anschreiben Eigentümerabrechnung", created_at: "2026-10-01T08:00:00Z" }] }));
    renderIntl(<StatementOutputsPanel base={BASE} previews={[{ key: "ownerLetter", path: "preview/letter", method: "GET" }]} filePath="outputs" enabled />);
    expect(screen.getByText(/Text nicht freigegeben/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Noch keine Ausgaben abgelegt.")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Vorschau Anschreiben" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Als Dokument ablegen" }));
    await waitFor(() => expect(screen.getByRole("link", { name: "Anschreiben Eigentümerabrechnung" })).toHaveAttribute("href", `/dokumente/${DOC}`));
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(`${BASE}/outputs`);
    expect(init.method).toBe("POST");
  });

  it("renders nothing without a calculated snapshot", () => {
    const { container } = renderIntl(<StatementOutputsPanel base={BASE} previews={[]} filePath="outputs" enabled={false} />);
    expect(container).toBeEmptyDOMElement();
  });
});
