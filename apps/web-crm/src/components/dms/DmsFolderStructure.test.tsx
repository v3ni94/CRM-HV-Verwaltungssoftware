import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DmsFolderStructure } from "./DmsFolderStructure";

function folders(withStandard: boolean) {
  return [
    { folder: "01_Legitimationsunterlagen", description: "Ausweiskopien, Vollmachten", per_unit_and_person: false, categories: [{ id: "c1", code: "identification", name: "Legitimationsunterlage" }], subfolders: [], subfolders_source: null },
    { folder: "02_Stammakte", description: "Teilungserklärung", per_unit_and_person: false, categories: [{ id: "c2", code: "contract", name: "Vertrag" }, { id: "c3", code: "minutes", name: "Protokoll" }], subfolders: [], subfolders_source: null },
    { folder: "03_Buchhaltung", description: "Rechnungen", per_unit_and_person: false, categories: [], subfolders: [], subfolders_source: null },
    {
      folder: "04_Mieterakte",
      description: "Je Einheit und Mieter",
      per_unit_and_person: true,
      categories: withStandard ? [{ id: "c4", code: "tenant_file", name: "Mieterakte" }] : [],
      subfolders: withStandard ? [{ name: "Verträge", document_types: ["Mietvertrag", "Nachtrag"] }] : [],
      subfolders_source: withStandard ? "objektakte" : null,
    },
    { folder: "05_Eigentümerakte", description: "Je Einheit und Eigentümer", per_unit_and_person: true, categories: withStandard ? [{ id: "c5", code: "owner_file", name: "Eigentümerakte" }] : [], subfolders: [], subfolders_source: null },
    { folder: "06_Sonstiges", description: "Unklar", per_unit_and_person: false, categories: [{ id: "c6", code: "other", name: "Sonstiges" }], subfolders: [], subfolders_source: null },
  ];
}

describe("DmsFolderStructure", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the six folders with categories and imported subfolders", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(folders(true)))),
    );
    renderIntl(<DmsFolderStructure />);
    await userEvent.click(screen.getByRole("button", { name: "Struktur anzeigen" }));
    expect(await screen.findByText("04_Mieterakte")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(7);
    expect(screen.getByText("Vertrag, Protokoll")).toBeInTheDocument();
    expect(screen.getByText("Verträge")).toBeInTheDocument();
    expect(screen.getByText("(Mietvertrag, Nachtrag)")).toBeInTheDocument();
    expect(screen.getByText("Bezeichnungen noch nicht aus der Objektübernahme übernommen, zu verifizieren")).toBeInTheDocument();
    expect(screen.queryByText("Standardkategorien ergänzen")).not.toBeInTheDocument();
  });

  it("offers to add the missing standard categories to an administrator", async () => {
    let ensured = false;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/bff/document-categories/ensure-defaults" && init?.method === "POST") {
        ensured = true;
        return Promise.resolve(jsonResponse([]));
      }
      if (url === "/api/bff/document-folders") return Promise.resolve(jsonResponse(folders(ensured)));
      return Promise.resolve(jsonResponse({}, 404));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<DmsFolderStructure canEnsureDefaults />);
    await userEvent.click(screen.getByRole("button", { name: "Struktur anzeigen" }));
    expect(await screen.findByText("Die Standardkategorien Mieterakte (04) und Eigentümerakte (05) fehlen bei diesem Mandanten.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Standardkategorien ergänzen" }));
    expect(await screen.findByText("Fehlende Standardkategorien wurden ergänzt.")).toBeInTheDocument();
    expect(await screen.findByText("Mieterakte")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Standardkategorien ergänzen" })).not.toBeInTheDocument();
  });
});
