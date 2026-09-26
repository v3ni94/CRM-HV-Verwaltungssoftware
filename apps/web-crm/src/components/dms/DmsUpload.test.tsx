import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DmsUpload } from "./DmsUpload";

const PROPERTY = "01920000-0000-7000-8000-000000000523";
const UNIT = "01920000-0000-7000-8000-000000000007";
const DOC = "01920000-0000-7000-8000-00000000d0c1";

describe("DmsUpload", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uploads with the unit link and reports the objektakte filing", async () => {
    const bodies: FormData[] = [];
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith("/api/bff/properties?")) return Promise.resolve(jsonResponse({ items: [{ id: PROPERTY, number: "523", name: "Musterstraße 49" }] }));
      if (url.endsWith(`/properties/${PROPERTY}/units`)) return Promise.resolve(jsonResponse([{ id: UNIT, number: "7", label: "WE 7" }]));
      if (url === "/api/bff/documents") {
        bodies.push(init?.body as FormData);
        return Promise.resolve(jsonResponse({ id: DOC }, 201));
      }
      if (url.endsWith(`/documents/${DOC}/filing`)) return Promise.resolve(jsonResponse({ routed: true, status: "pending" }));
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<DmsUpload />);
    await screen.findByRole("option", { name: "523 Musterstraße 49" });
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), PROPERTY);
    await screen.findByRole("option", { name: "WE 7" });
    await userEvent.selectOptions(screen.getByLabelText("Einheit"), UNIT);
    await userEvent.upload(screen.getByLabelText("Datei"), new File(["%PDF-1.4"], "rechnung.pdf", { type: "application/pdf" }));
    await userEvent.click(screen.getByRole("button", { name: "Hochladen" }));

    expect(await screen.findByTestId("dms-upload-done")).toHaveTextContent("Hochgeladen, die Ablage in Drive und Paperless läuft über die Objektübernahme.");
    expect(screen.getByRole("link", { name: "Dokument öffnen" })).toHaveAttribute("href", `/dokumente/${DOC}`);
    expect(JSON.parse(String(bodies[0]?.get("links")))).toEqual([{ entity_type: "unit", entity_id: UNIT, role: "original" }]);
    expect((bodies[0]?.get("file") as File).name).toBe("rechnung.pdf");
  });
});
