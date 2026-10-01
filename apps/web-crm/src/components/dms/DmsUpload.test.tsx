import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DmsUpload } from "./DmsUpload";

const PROPERTY = "01920000-0000-7000-8000-000000000523";
const UNIT = "01920000-0000-7000-8000-000000000007";
const DOC = "01920000-0000-7000-8000-00000000d0c1";
const CATEGORY = "01920000-0000-7000-8000-00000000ca04";
const CONTRACT = "01920000-0000-7000-8000-00000000c001";
const CONTACT = "01920000-0000-7000-8000-00000000c0e1";

function fetchFor(bodies: FormData[]) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.startsWith("/api/bff/properties?")) return Promise.resolve(jsonResponse({ items: [{ id: PROPERTY, number: "523", name: "Musterstraße 49" }] }));
    if (url === "/api/bff/document-categories")
      return Promise.resolve(
        jsonResponse([
          { id: "c-inv", code: "invoice", name: "Rechnung", drive_folder: "03_Buchhaltung" },
          { id: CATEGORY, code: "tenant_file", name: "Mieterakte", drive_folder: "04_Mieterakte" },
        ]),
      );
    if (url.endsWith(`/properties/${PROPERTY}/units`)) return Promise.resolve(jsonResponse([{ id: UNIT, number: "7", label: "WE 7" }]));
    if (url.startsWith(`/api/bff/contracts?unit_id=${UNIT}`))
      return Promise.resolve(jsonResponse([{ id: CONTRACT, number: "MV-0007", party_name: "Mustermann, Erika", start_date: "2025-01-01", end_date: null }]));
    if (url.startsWith("/api/bff/contracts?property_id=")) return Promise.resolve(jsonResponse([]));
    if (url.startsWith("/api/bff/contacts?q=")) return Promise.resolve(jsonResponse({ items: [{ id: CONTACT, display_name: "Mustermann, Erika" }] }));
    if (url === "/api/bff/documents") {
      bodies.push(init?.body as FormData);
      return Promise.resolve(jsonResponse({ id: DOC }, 201));
    }
    if (url.endsWith(`/documents/${DOC}/filing`)) return Promise.resolve(jsonResponse({ routed: true, status: "pending" }));
    return Promise.resolve(jsonResponse({}, 404));
  });
}

describe("DmsUpload", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uploads with the unit link and reports the objektakte filing", async () => {
    const bodies: FormData[] = [];
    vi.stubGlobal("fetch", fetchFor(bodies));

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
    expect(bodies[0]?.get("category_id")).toBeNull();
    expect((bodies[0]?.get("file") as File).name).toBe("rechnung.pdf");
  });

  it("sends category, contract and contact with the upload (Package F)", async () => {
    const bodies: FormData[] = [];
    vi.stubGlobal("fetch", fetchFor(bodies));

    renderIntl(<DmsUpload />);
    await screen.findByRole("option", { name: "523 Musterstraße 49" });
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), PROPERTY);
    await screen.findByRole("option", { name: "WE 7" });
    await userEvent.selectOptions(screen.getByLabelText("Einheit"), UNIT);
    await screen.findByRole("option", { name: "Mieterakte (04_Mieterakte)" });
    await userEvent.selectOptions(screen.getByLabelText("Kategorie"), CATEGORY);
    await screen.findByRole("option", { name: "MV-0007, Mustermann, Erika, 01.01.2025" });
    await userEvent.selectOptions(screen.getByLabelText("Vertrag"), CONTRACT);
    await userEvent.type(screen.getByLabelText("Kontakt"), "Mustermann");
    await userEvent.click(screen.getByRole("button", { name: "Kontakt suchen" }));
    await userEvent.click(await screen.findByRole("button", { name: "Mustermann, Erika" }));
    await userEvent.upload(screen.getByLabelText("Datei"), new File(["%PDF-1.4"], "mietvertrag.pdf", { type: "application/pdf" }));
    await userEvent.type(screen.getByLabelText("Titel (optional)"), "WE 7, Mietvertrag, Mustermann, 01.01.2025");
    await userEvent.click(screen.getByRole("button", { name: "Hochladen" }));

    await screen.findByTestId("dms-upload-done");
    expect(bodies[0]?.get("category_id")).toBe(CATEGORY);
    expect(bodies[0]?.get("title")).toBe("WE 7, Mietvertrag, Mustermann, 01.01.2025");
    expect(JSON.parse(String(bodies[0]?.get("links")))).toEqual([
      { entity_type: "unit", entity_id: UNIT, role: "original" },
      { entity_type: "contract", entity_id: CONTRACT, role: "original" },
      { entity_type: "contact", entity_id: CONTACT, role: "original" },
    ]);
  });

  it("offers a file chooser with images, HEIC and PDF and a camera input with capture (M31)", async () => {
    const bodies: FormData[] = [];
    vi.stubGlobal("fetch", fetchFor(bodies));
    renderIntl(<DmsUpload />);
    const file = screen.getByLabelText("Datei");
    expect(file).toHaveAttribute("accept", "image/jpeg,image/png,image/heic,image/heif,application/pdf");
    expect(file).not.toHaveAttribute("capture");
    const camera = screen.getByLabelText("Kamera");
    expect(camera).toHaveAttribute("accept", "image/*");
    expect(camera).toHaveAttribute("capture", "environment");
    await screen.findByRole("option", { name: "523 Musterstraße 49" });
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), PROPERTY);
    await userEvent.upload(camera, new File(["jpg"], "foto.jpg", { type: "image/jpeg" }));
    await userEvent.click(screen.getByRole("button", { name: "Hochladen" }));
    await screen.findByTestId("dms-upload-done");
    expect((bodies[0]?.get("file") as File).name).toBe("foto.jpg");
  });

  it("uploads directly with a signed URL when the tenant switch is on and falls back on failure", async () => {
    const calls: string[] = [];
    const base = fetchFor([]);
    const direct = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url === "/api/bff/document-direct-upload") return Promise.resolve(jsonResponse({ enabled: true }));
      if (url === "/api/bff/documents/uploads")
        return Promise.resolve(jsonResponse({ upload_id: "up1", url: "https://s3.example.org/tmp/up1", headers: { "Content-Type": "application/pdf" }, method: "PUT", expires_in: 300 }, 201));
      if (url === "https://s3.example.org/tmp/up1") return Promise.resolve(new Response(null, { status: 200 }));
      if (url === "/api/bff/documents/uploads/up1/complete") return Promise.resolve(jsonResponse({ id: DOC }, 201));
      return base(input, init);
    });
    vi.stubGlobal("fetch", direct);
    renderIntl(<DmsUpload />);
    await screen.findByRole("option", { name: "523 Musterstraße 49" });
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), PROPERTY);
    await userEvent.upload(screen.getByLabelText("Datei"), new File(["%PDF-1.4"], "rechnung.pdf", { type: "application/pdf" }));
    await userEvent.click(screen.getByRole("button", { name: "Hochladen" }));
    expect(await screen.findByTestId("dms-upload-done")).toBeInTheDocument();
    expect(calls).toContain("PUT https://s3.example.org/tmp/up1");
    expect(calls).not.toContain("POST /api/bff/documents");
  });

  it("falls back to the API upload when the signed PUT fails", async () => {
    const bodies: FormData[] = [];
    const base = fetchFor(bodies);
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/bff/document-direct-upload") return Promise.resolve(jsonResponse({ enabled: true }));
        if (url === "/api/bff/documents/uploads")
          return Promise.resolve(jsonResponse({ upload_id: "up1", url: "https://s3.example.org/tmp/up1", headers: {}, method: "PUT", expires_in: 300 }, 201));
        if (url === "https://s3.example.org/tmp/up1") return Promise.reject(new TypeError("CORS"));
        return base(input, init);
      }),
    );
    renderIntl(<DmsUpload />);
    await screen.findByRole("option", { name: "523 Musterstraße 49" });
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), PROPERTY);
    await userEvent.upload(screen.getByLabelText("Datei"), new File(["%PDF-1.4"], "rechnung.pdf", { type: "application/pdf" }));
    await userEvent.click(screen.getByRole("button", { name: "Hochladen" }));
    expect(await screen.findByTestId("dms-upload-done")).toBeInTheDocument();
    expect(bodies).toHaveLength(1);
  });
});
