import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { IntlTestProvider, jsonResponse } from "@/test/intl";

import { DocumentBulkBar } from "./DocumentBulkBar";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

describe("DocumentBulkBar", () => {
  const posts: Record<string, unknown>[] = [];
  beforeEach(() => {
    posts.length = 0;
    refresh.mockClear();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "POST") {
        posts.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return jsonResponse({ changed: 2 });
      }
      if (url.includes("document-categories")) return jsonResponse([{ id: "c1", name: "Rechnung" }]);
      return jsonResponse({ items: [{ id: "p1", number: "101", name: "Testhaus" }] });
    });
  });
  afterEach(() => vi.restoreAllMocks());

  function setup() {
    return render(
      <IntlTestProvider>
        <div id="documents-bulk">
          <input type="checkbox" name="bulk-id" value="d1" defaultChecked />
          <input type="checkbox" name="bulk-id" value="d1" defaultChecked />
          <input type="checkbox" name="bulk-id" value="d2" />
          <DocumentBulkBar formId="documents-bulk" />
        </div>
      </IntlTestProvider>,
    );
  }

  it("sets the category of the checked documents once per id", async () => {
    setup();
    await screen.findByRole("option", { name: "Rechnung" });
    await userEvent.selectOptions(screen.getByLabelText("Kategorie"), "c1");
    await userEvent.click(screen.getByRole("button", { name: "Kategorie setzen" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toEqual({ ids: ["d1"], action: "documents.set_category", category_id: "c1" });
    expect(await screen.findByText("2 geändert.")).toBeInTheDocument();
    expect(refresh).toHaveBeenCalled();
  });

  it("links the property and reports when nothing is checked", async () => {
    setup();
    await screen.findByRole("option", { name: "101 Testhaus" });
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), "p1");
    await userEvent.click(screen.getByRole("button", { name: "Mit Objekt verknüpfen" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toEqual({ ids: ["d1"], action: "documents.link_property", property_id: "p1" });
  });

  it("does not post without a selection", async () => {
    render(
      <IntlTestProvider>
        <div id="documents-bulk">
          <input type="checkbox" name="bulk-id" value="d2" />
          <DocumentBulkBar formId="documents-bulk" />
        </div>
      </IntlTestProvider>,
    );
    await screen.findByRole("option", { name: "Rechnung" });
    await userEvent.selectOptions(screen.getByLabelText("Kategorie"), "c1");
    await userEvent.click(screen.getByRole("button", { name: "Kategorie setzen" }));
    expect(await screen.findByText("Keine Zeilen markiert.")).toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });
});
