import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DocumentBulkLink } from "./DocumentBulkLink";

describe("DocumentBulkLink (GAI-417)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("posts the ids and shows the partial result", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ total: 2, succeeded: 1, failed: 1, items: [{ id: "01920000-0000-7000-8000-0000000a1701", ok: true }, { id: "01920000-0000-7000-8000-0000000a1702", ok: false, detail: "Nicht gefunden" }] }),
    );
    renderIntl(<DocumentBulkLink canEdit />);
    await userEvent.type(screen.getByLabelText("Dokument-IDs (eine je Zeile)"), "01920000-0000-7000-8000-0000000a1701\n01920000-0000-7000-8000-0000000a1702");
    await userEvent.type(screen.getByLabelText("Objekt-ID"), "01920000-0000-7000-8000-0000000a1703");
    await userEvent.click(screen.getByRole("button", { name: "Verknüpfen" }));
    expect(await screen.findByTestId("bulk-link-result")).toHaveTextContent("1 von 2 verknüpft, 1 fehlgeschlagen.");
    expect(screen.getByTestId("bulk-link-result")).toHaveTextContent("Nicht gefunden");
    expect(JSON.parse(String(f.mock.calls[0]![1]?.body))).toEqual({ ids: ["01920000-0000-7000-8000-0000000a1701", "01920000-0000-7000-8000-0000000a1702"], entity_type: "property", entity_id: "01920000-0000-7000-8000-0000000a1703" });
  });

  it("rejects invalid ids without a request and hides without the right", async () => {
    const f = vi.spyOn(globalThis, "fetch");
    const { unmount } = renderIntl(<DocumentBulkLink canEdit />);
    await userEvent.type(screen.getByLabelText("Dokument-IDs (eine je Zeile)"), "abc");
    await userEvent.click(screen.getByRole("button", { name: "Verknüpfen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("gültige Dokument-ID");
    expect(f).not.toHaveBeenCalled();
    unmount();
    const { container } = renderIntl(<DocumentBulkLink canEdit={false} />);
    expect(container).toBeEmptyDOMElement();
  });
});
