import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DefectTicketsButton } from "@/components/handover/DefectTicketsButton";
import { FastTableImportSwitch } from "@/components/ai/FastTableImportSwitch";
import { DataQualityActions } from "@/components/settings/DataQualityActions";
import { LexofficeRuns } from "@/components/settings/LexofficeRuns";
import { jsonResponse, renderIntl } from "@/test/intl";

import { ProspectViewings } from "./ProspectViewings";

const PID = "01920000-0000-7000-8000-0000000000p1";

describe("AF20 Oberflächen", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lädt Besichtigungen je Interessent", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse([{ id: "v1", scheduled_at: "2026-10-05T09:00:00Z", status: "proposed", location: "Hof", note: null }]),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<ProspectViewings prospectId={PID} />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Besichtigungen anzeigen" }));
    });
    expect(await screen.findByText("Hof")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/letting/prospects/${PID}/viewings`);
  });

  it("legt Mängel als Tickets an", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ created: [{}, {}], skipped: 0 }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<DefectTicketsButton protocolId={PID} defectCount={2} />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: /Mängel als Tickets anlegen/ }));
    });
    expect(await screen.findByText("2 Tickets angelegt.")).toBeInTheDocument();
  });

  it("zeigt Lexware Läufe", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse([{ id: "r1", kind: "import_receipts", status: "done", counts: { items: 3 }, errors: [], created_at: "2026-10-01T10:00:00Z", finished_at: null }])),
    );
    renderIntl(<LexofficeRuns canImport />);
    expect(await screen.findByText("import_receipts")).toBeInTheDocument();
  });

  it("schaltet den schnellen Tabellenimport", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse({ enabled: false })).mockResolvedValueOnce(jsonResponse({ enabled: true }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<FastTableImportSwitch />);
    const box = await screen.findByRole("checkbox");
    await act(async () => {
      await userEvent.click(box);
    });
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({ method: "PUT" });
  });

  it("startet die Datenqualitätsprüfung und meldet ungültiges JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ findings: [{ rule: "ES-01", field: null, severity: "warning", message: "Name fehlt" }] }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<DataQualityActions canRecompute={false} />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Prüfung starten" }));
    });
    expect(await screen.findByText(/Name fehlt/)).toBeInTheDocument();
  });
});

describe("AG14 Oberflächen", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("Lexware Export: Auswahl, Vorschau, Export", async () => {
    const { LexofficeExport } = await import("@/components/settings/LexofficeExport");
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return Promise.resolve(jsonResponse({ run_id: "r1", items: [{ entity_id: "c1", ok: true }] }));
      return Promise.resolve(jsonResponse({ items: [{ id: "c1", display_name: "Erika Muster" }] }));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<LexofficeExport canExport />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Liste laden" }));
    });
    await act(async () => {
      await userEvent.click(await screen.findByRole("checkbox"));
    });
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Vorschau" }));
    });
    expect(screen.getByTestId("lexoffice-export-preview")).toBeInTheDocument();
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: /Export starten/ }));
    });
    expect(await screen.findByTestId("lexoffice-export-result")).toBeInTheDocument();
    const post = fetchMock.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "POST");
    expect(post?.[0]).toBe("/api/bff/integrations/lexoffice/export/contacts");
  });

  it("U-Protokoll Dateien: Zuordnung zeigt Ergebnis", async () => {
    const { UprotokollFiles } = await import("@/components/handover/UprotokollFiles");
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ matched: [{ filename: "a.jpg", document_id: "d1" }], unmatched_in_zip: ["b.jpg"], staged_without_file: [] }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<UprotokollFiles canMatch />);
    await act(async () => {
      await userEvent.type(screen.getByLabelText("Lauf ID"), "run-1");
      await userEvent.upload(screen.getByLabelText("ZIP Datei"), new File(["x"], "f.zip"));
    });
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Zuordnen" }));
    });
    expect(await screen.findByText("a.jpg")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toContain("/api/bff/handover/imports/uprotokoll/files?import_run_id=run-1");
  });

  it("OpenImmo Import: Auswahllisten statt ID Eingabe", async () => {
    const { OpenImmoImport } = await import("@/components/letting/OpenImmoImport");
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return Promise.resolve(jsonResponse({ run_id: "r", filename: "x.xml", row_count: 1, rows: [{ row_id: "w1", title: "Wohnung", ort: null, strasse: null, status: "new", is_duplicate: false, structure_errors: [] }] }));
      if (url.includes("/units")) return Promise.resolve(jsonResponse([{ id: "u1", number: "WE 1", label: null }]));
      return Promise.resolve(jsonResponse({ items: [{ id: "p1", number: "100", name: "Hof" }] }));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<OpenImmoImport canApply />);
    await act(async () => {
      await userEvent.upload(document.querySelector("input[type=file]") as HTMLInputElement, new File(["<x/>"], "x.xml"));
    });
    await act(async () => {
      await userEvent.selectOptions(await screen.findByLabelText("Objekt"), "p1");
    });
    await act(async () => {
      await userEvent.selectOptions(await screen.findByLabelText("Einheit"), "u1");
    });
    expect(screen.getByRole("button", { name: "Übernehmen" })).toBeEnabled();
  });
});
