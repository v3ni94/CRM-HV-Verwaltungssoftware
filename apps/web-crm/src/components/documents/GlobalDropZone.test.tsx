import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { fileDropped, GlobalDropZone } from "./GlobalDropZone";

describe("GlobalDropZone", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("sends a ZIP to the bulk import and other files to the upload with object and category", async () => {
    fetchMock.mockImplementation(async (input) =>
      String(input).includes("zip-import")
        ? jsonResponse({ import_run_id: "r1", created: ["a", "b"], skipped: [{ name: "x.exe", reason: "nicht zulässig" }] }, 201)
        : jsonResponse({ id: "d1" }, 201),
    );
    const zip = new File(["PK"], "belege.zip", { type: "application/zip" });
    const pdf = new File(["%PDF"], "rechnung.pdf", { type: "application/pdf" });
    const outcome = await fileDropped([zip, pdf], "p1", "c1");
    expect(outcome).toEqual({ filed: 3, skipped: [{ name: "x.exe", reason: "nicht zulässig" }], failed: [] });
    const [first, second] = fetchMock.mock.calls;
    expect(String(first?.[0])).toBe("/api/bff/documents/zip-import");
    expect(String(second?.[0])).toBe("/api/bff/documents");
    const body = (second?.[1] as RequestInit).body as FormData;
    expect(body.get("category_id")).toBe("c1");
    expect(JSON.parse(String(body.get("links")))).toEqual([{ entity_type: "property", entity_id: "p1" }]);
  });

  it("opens the dialog for picked files and reports what was filed", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("properties")) return jsonResponse({ items: [{ id: "p1", number: "101", name: "Rhein" }] });
      if (url.includes("document-categories")) return jsonResponse([{ id: "c1", code: "invoice", name: "Rechnung" }]);
      return jsonResponse({ id: "d1" }, 201);
    });
    renderIntl(<GlobalDropZone />);
    await user.upload(screen.getByTestId("global-drop-input"), new File(["x"], "notiz.txt", { type: "text/plain" }));
    const dialog = await screen.findByRole("dialog", { name: "Dokumente ablegen" });
    await screen.findByRole("option", { name: "101 Rhein" });
    await user.selectOptions(screen.getByLabelText("Objekt"), "p1");
    await user.click(within(dialog).getByRole("button", { name: "Ablegen" }));
    await waitFor(() => expect(screen.getByText("1 Dokument automatisch abgelegt")).toBeInTheDocument());
  }, 20000);
});
