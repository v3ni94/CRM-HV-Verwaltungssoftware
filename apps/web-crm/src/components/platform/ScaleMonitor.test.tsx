import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { changedSettings, formatBytes, formatCount, formatMs, formatPercent, ScaleMonitor, type ScaleSettings, type ScaleView } from "./ScaleMonitor";

const settings: ScaleSettings = {
  rows_threshold: 20000000,
  size_gb_threshold: 50,
  p95_ms_threshold: 300,
  p95_deep_ms_threshold: 1000,
  p95_weeks: 3,
  restore_seconds_threshold: 14400,
  tenants_review_threshold: 20,
  alarm_enabled: true,
  version: 1,
};

const view = (overrides: Partial<ScaleView> = {}): ScaleView => ({
  settings,
  tables: [
    { table: "journal_entry", rows: 100000, bytes: 91 * 1024 ** 2, exact: true, rows_percent: 0.5, size_percent: 0.2 },
    { table: "journal_line", rows: 21000000, bytes: 2 * 1024 ** 3, exact: false, rows_percent: 105, size_percent: 4 },
    { table: "bank_transaction", rows: 0, bytes: 0, exact: true, rows_percent: 0, size_percent: 0 },
  ],
  latency: [
    { key: "journal_list", samples: 120, p95_ms: 412.4, threshold_ms: 300 },
    { key: "journal_list_deep", samples: 3, p95_ms: null, threshold_ms: 1000 },
    { key: "bank_list", samples: 50, p95_ms: 88, threshold_ms: 300 },
    { key: "bank_list_deep", samples: 0, p95_ms: null, threshold_ms: 1000 },
  ],
  min_samples: 20,
  restore: { seconds: null, threshold_seconds: 14400 },
  tenants: { productive: 3, demo: 1, review_threshold: 20 },
  triggers: [],
  history: [],
  ...overrides,
});

describe("format helpers (AE36)", () => {
  it("formats counts, sizes, milliseconds and shares for display", () => {
    expect(formatCount(20000000)).toBe("20.000.000");
    expect(formatBytes(2 * 1024 ** 3)).toBe("2 GB");
    expect(formatBytes(1.5 * 1024 ** 3)).toBe("1,5 GB");
    expect(formatBytes(91 * 1024 ** 2)).toBe("91 MB");
    expect(formatBytes(0)).toBe("0 MB");
    expect(formatMs(412.4)).toBe("412 ms");
    expect(formatMs(null)).toBe("-");
    expect(formatPercent(105)).toBe("105,0 %");
    expect(formatPercent(0.5)).toBe("0,5 %");
  });

  it("sends only the changed settings as numbers", () => {
    const form = {
      rows_threshold: "20000000",
      size_gb_threshold: "40",
      p95_ms_threshold: "300",
      p95_deep_ms_threshold: "1000",
      p95_weeks: "3",
      restore_seconds_threshold: "14400",
      tenants_review_threshold: "20",
      alarm_enabled: false,
    };
    expect(changedSettings(form, settings)).toEqual({ size_gb_threshold: 40, alarm_enabled: false });
    expect(changedSettings({ ...form, size_gb_threshold: "50", alarm_enabled: true }, settings)).toEqual({});
    expect(changedSettings({ ...form, p95_weeks: "abc" }, settings)).toEqual({ size_gb_threshold: 40, alarm_enabled: false });
  });
});

describe("ScaleMonitor", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows tables, P95 with the sample basis and the tenant count without demo tenants", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(view()));
    renderIntl(<ScaleMonitor />);
    expect(await screen.findByText("journal_line")).toBeInTheDocument();
    expect(screen.getByText("21.000.000")).toBeInTheDocument();
    expect(screen.getByText("Schätzung der Datenbank")).toBeInTheDocument();
    expect(screen.getByText("412 ms")).toBeInTheDocument();
    expect(screen.getAllByText("zu wenige Aufrufe")).toHaveLength(2);
    expect(screen.getByText(/Produktive Mandanten: 3 \(Demo-Mandanten: 1, nicht mitgezählt\)/)).toBeInTheDocument();
    expect(screen.getByText(/Kein Auslöser erreicht/)).toBeInTheDocument();
    expect(screen.getByText(/Letzter Wiederherstellungstest: kein erfolgreicher Test vorhanden/)).toBeInTheDocument();
  });

  it("lists the triggers reached with their kind", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse(
        view({
          triggers: [
            { key: "rows:journal_line", kind: "partition_review", title: "journal_line: 20.000.000 Zeilen erreicht", detail: "Planung beginnen.", value: 21000000, threshold: 20000000 },
            { key: "tenants:productive", kind: "measure_again", title: "20 produktive Mandanten", detail: "Messung wiederholen.", value: 20, threshold: 20 },
          ],
        }),
      ),
    );
    renderIntl(<ScaleMonitor />);
    expect(await screen.findByText("journal_line: 20.000.000 Zeilen erreicht")).toBeInTheDocument();
    expect(screen.getByText("Partitionierung planen")).toBeInTheDocument();
    expect(screen.getByText("Messung wiederholen")).toBeInTheDocument();
    expect(screen.queryByText(/Kein Auslöser erreicht/)).not.toBeInTheDocument();
  });

  it("saves only changed thresholds with PATCH and reloads", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(view()));
    renderIntl(<ScaleMonitor />);
    const input = await screen.findByLabelText("Größe je Tabelle in GB (mit Indizes)");
    await userEvent.clear(input);
    await userEvent.type(input, "40");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
      expect(patch).toBeDefined();
      expect(String(patch?.[0])).toContain("/api/bff/platform/ops/scale/settings");
      expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ size_gb_threshold: 40 });
    });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("does not call the API when nothing changed", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(view()));
    renderIntl(<ScaleMonitor />);
    await screen.findByText("journal_line");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Keine Änderung.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
  });

  it("stores a measurement now and reports the new triggers", async () => {
    fetchMock.mockImplementation(async (input, init) =>
      String(input).endsWith("/snapshot") && init?.method === "POST"
        ? jsonResponse({ iso_week: "2026-W40", triggers: [], new_triggers: ["tenants:productive"], notified: 1 })
        : jsonResponse(view()),
    );
    renderIntl(<ScaleMonitor />);
    await userEvent.click(await screen.findByRole("button", { name: "Messung jetzt speichern" }));
    expect(await screen.findByText("Messung 2026-W40 gespeichert, neue Auslöser: 1.")).toBeInTheDocument();
  });

  it("shows the weekly history", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse(
        view({
          history: [
            {
              iso_week: "2026-W40",
              source: "job",
              tables: { journal_line: { rows: 72, bytes: 1 }, bank_transaction: { rows: 200, bytes: 1 } },
              latency: { journal_list: { p95_ms: 120 }, bank_list: { p95_ms: null } },
              triggers: [],
            },
          ],
        }),
      ),
    );
    renderIntl(<ScaleMonitor />);
    const row = (await screen.findByText("2026-W40")).closest("tr") as HTMLElement;
    expect(within(row).getByText("72")).toBeInTheDocument();
    expect(within(row).getByText("200")).toBeInTheDocument();
    expect(within(row).getByText("120 ms")).toBeInTheDocument();
  });
});
