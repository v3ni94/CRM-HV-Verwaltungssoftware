import { screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { renderIntl } from "@/test/intl";

import { GeneratedDocumentsList, generatedDocumentsQuery } from "./GeneratedDocumentsList";

describe("GeneratedDocumentsList", () => {
  afterEach(() => vi.restoreAllMocks());

  it("builds the query without empty filters", () => {
    expect(generatedDocumentsQuery("", "", "")).toBe("limit=100");
    expect(generatedDocumentsQuery("t1", "2026-01-01", "2026-01-31")).toBe("template_id=t1&created_from=2026-01-01&created_to=2026-01-31&limit=100");
  });

  it("lists rows with a link to the document and filters by template", async () => {
    const row = {
      id: "g1", document_id: "d1", template_id: "t1", template_code: "mahnung", template_version: 2,
      context_type: "contract", recipient_contact_id: null, delivery_channel: "email", delivery_status: "sent",
      created_at: "2026-09-30T10:00:00Z",
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(JSON.stringify([row]), { status: 200, headers: { "content-type": "application/json" } }));
    renderIntl(<GeneratedDocumentsList templates={[{ id: "t1", code: "mahnung", name: "Mahnung", version: 2 }]} />);
    expect(await screen.findByText("mahnung (v2)")).toBeTruthy();
    expect(screen.getByRole("link").getAttribute("href")).toBe("/dokumente/d1");
    (screen.getByLabelText("Vorlage") as HTMLSelectElement).value = "t1";
    screen.getByLabelText("Vorlage").dispatchEvent(new Event("change", { bubbles: true }));
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("template_id=t1"))).toBe(true));
  });
});
