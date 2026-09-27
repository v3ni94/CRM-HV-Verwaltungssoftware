import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DatevCheckPanel, type CheckOut, type DatevExportRun } from "./DatevCheckPanel";

const run: DatevExportRun = {
  id: "01920000-0000-7000-8000-00000000e001",
  ledger_id: "01920000-0000-7000-8000-00000000a001",
  period_from: "2026-01-01",
  period_to: "2026-12-31",
  rows: 5,
  sha256: "abc",
  note: null,
  created_at: "2026-09-27T10:00:00Z",
  checked_at: null,
  check_status: null,
  has_content: true,
};

const checked: CheckOut = {
  export_id: run.id,
  checked_at: "2026-09-27T10:05:00Z",
  report: {
    status: "fehlerhaft",
    errors: 1,
    warnings: 1,
    infos: 0,
    booking_rows: 5,
    header_fields: 21,
    columns: [],
    rules: [{ id: "DC-01", title: "Kopfzeile EXTF", source: "belegt", reference: "x", checked: true }],
    findings: [
      { rule: "DC-14", title: "Konto", source: "belegt", severity: "error", line: 3, field: "Gegenkonto (ohne BU-Schlüssel)", value: "", message: "Gegenkonto ist leer." },
      { rule: "DC-05", title: "Felder", source: "zu_pruefen", severity: "warning", line: 1, field: null, value: null, message: "Kopfzeile hat 21 Felder." },
    ],
    disclaimer: "Formale Selbstprüfung.",
  },
  text: "Prüfbericht",
};

describe("DatevCheckPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("checks an export and renders the findings with rule, source and line", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith(`/exports/${run.id}/check`) && init?.method === "POST") return jsonResponse(checked);
      if (url.endsWith("/datev/exports")) return jsonResponse([{ ...run, check_status: "fehlerhaft", checked_at: checked.checked_at }]);
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<DatevCheckPanel initial={[run]} canCheck />);
    expect(screen.getByText("nicht geprüft")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Testdatei herunterladen" })).toHaveAttribute("href", "/api/bff/accounting/datev/sample-batch");

    await userEvent.setup().click(screen.getByRole("button", { name: "Prüfen" }));
    await waitFor(() => expect(screen.getByTestId("datev-check-report")).toBeInTheDocument());
    expect(screen.getByText("Prüfbericht: fehlerhaft")).toBeInTheDocument();
    expect(screen.getByText("5 Buchungszeilen, 1 Fehler, 1 Hinweise")).toBeInTheDocument();
    expect(screen.getByText("Gegenkonto ist leer.")).toBeInTheDocument();
    expect(screen.getByText("zu prüfen")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(`/api/bff/accounting/datev/exports/${run.id}/check`, expect.objectContaining({ method: "POST" }));
    await waitFor(() => expect(screen.getAllByText("fehlerhaft").length).toBeGreaterThan(0));
  });

  it("hides the check button without the export permission", () => {
    renderIntl(<DatevCheckPanel initial={[run]} canCheck={false} />);
    expect(screen.queryByRole("button", { name: "Prüfen" })).not.toBeInTheDocument();
    expect(screen.getByText("Die Prüfung erfordert das Recht Buchhaltung exportieren.")).toBeInTheDocument();
  });
});
