import { screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LocalModelStatus } from "./LocalModelStatus";
import { RequiredDocuments } from "./RequiredDocuments";

describe("RequiredDocuments", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists required documents with category names", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse([{ id: "r1", management_type: "hoa", document_category_id: "c1", mandatory: true }])));
    renderIntl(<RequiredDocuments categories={[{ id: "c1", code: "01", name: "Teilungserklärung" }]} canManage canDelete />);
    expect(await screen.findByText("Teilungserklärung")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Entfernen" })).toBeInTheDocument();
  });

  it("shows the local model status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse({ enabled: false, version: null, artifact: null })));
    renderIntl(<LocalModelStatus canPropose />);
    expect(await screen.findByText("Ausgeschaltet")).toBeInTheDocument();
  });
});
