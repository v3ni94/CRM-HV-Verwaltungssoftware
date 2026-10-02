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
