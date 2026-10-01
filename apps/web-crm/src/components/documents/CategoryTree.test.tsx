import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { buildTree, CategoryTree, type TreeCategory } from "./CategoryTree";

const cat = (id: string, name: string, parent_id: string | null, sort_order = 0): TreeCategory => ({
  id,
  code: id,
  name,
  parent_id,
  paperless_document_type: null,
  paperless_tag: null,
  drive_folder: null,
  sort_order,
});

describe("CategoryTree", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("builds the tree by parent, sorted, and keeps orphans and cycles visible", () => {
    const tree = buildTree([cat("b", "B", null, 2), cat("a", "A", null, 1), cat("a1", "A1", "a"), cat("o", "O", "missing")]);
    expect(tree.map((n) => n.id)).toEqual(["o", "a", "b"]);
    expect(tree[1]?.children.map((n) => [n.id, n.depth])).toEqual([["a1", 1]]);
    const cycle = buildTree([cat("x", "X", "y"), cat("y", "Y", "x")]);
    expect(cycle).toEqual([]);
  });

  it("saves the Paperless tag of a category", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async () => jsonResponse({ ...cat("a", "Rechnung", null), paperless_tag: "Beleg" }));
    renderIntl(<CategoryTree categories={[cat("a", "Rechnung", null)]} />);
    await user.click(screen.getByRole("button", { name: "Zuordnung bearbeiten" }));
    await user.type(screen.getByLabelText("Paperless-Tag"), "Beleg");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByText("Zuordnung gespeichert.")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/bff/document-categories/a");
    expect(JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body))).toEqual({
      paperless_document_type: null,
      paperless_tag: "Beleg",
      drive_folder: null,
    });
    expect(screen.getByText("Dokumenttyp -, Tag Beleg, Ordner -")).toBeInTheDocument();
  });
});
