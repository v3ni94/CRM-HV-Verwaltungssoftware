import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DatevMappingsAdmin, type DatevMapping, type ImportResult, type Report } from "./DatevMappingsAdmin";

const LEDGER = "01920000-0000-7000-8000-00000000a001";
const ledgers = [{ id: LEDGER, name: "WEG Berichthaus" }];
const existing: DatevMapping = {
  id: "01920000-0000-7000-8000-00000000b001",
  ledger_id: null,
  account_code: "001200",
  datev_account: "1200",
  label: "Bank",
  active: true,
  valid_from: null,
};

describe("DatevMappingsAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists mappings and creates a new one", async () => {
    const created: DatevMapping = { ...existing, id: "01920000-0000-7000-8000-00000000b002", account_code: "009000", datev_account: "9000", label: null };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/api/bff/accounting/datev-mappings" && method === "POST") return jsonResponse(created, 201);
      if (url.startsWith("/api/bff/accounting/datev-mappings?include_inactive=true")) return jsonResponse([existing, created]);
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<DatevMappingsAdmin initial={[existing]} ledgers={ledgers} canManage />);
    expect(screen.getByText("Bank")).toBeInTheDocument();
    expect(screen.getAllByText("Alle Buchungskreise").length).toBeGreaterThan(0);

    const user = userEvent.setup();
    const form = screen.getByRole("button", { name: "Anlegen" }).closest("form")!;
    await user.type(within(form).getByLabelText("CRM-Konto"), "009000");
    await user.type(within(form).getByLabelText("DATEV-Konto"), "9000");
    await user.click(screen.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(screen.getByText("Zuordnung angelegt.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/accounting/datev-mappings",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ account_code: "009000", datev_account: "9000", label: null, ledger_id: null, valid_from: null }),
      }),
    );
    await waitFor(() => expect(screen.getByText("9000")).toBeInTheDocument());
  });

  it("previews a CSV import, blocks apply on errors and loads the report", async () => {
    const preview: ImportResult = {
      dry_run: true,
      ledger_id: null,
      rows: [
        { line_no: 2, account_code: "009000", datev_account: "9000", label: null, valid_from: null, action: "create", error: null, existing_datev_account: null },
        { line_no: 3, account_code: "001201", datev_account: "12x", label: null, valid_from: null, action: "error", error: "DATEV-Konto muss numerisch sein.", existing_datev_account: null },
      ],
      file_errors: [],
      counts: { create: 1, update: 0, unchanged: 0, error: 1 },
    };
    const report: Report = {
      ledger_id: LEDGER,
      period_from: "2026-01-01",
      period_to: "2026-12-31",
      unmapped_count: 1,
      used_unmapped_count: 1,
      accounts: [
        { account_id: "a1", account_code: "001200", account_name: "Bank", datev_account: "1200", lines_in_period: 2, first_booking_date: "2026-01-01", last_booking_date: "2026-03-15", unmapped: false, unmapped_lines: 0, reason: null },
        { account_id: "a2", account_code: "009000", account_name: "Saldenvortrag", datev_account: null, lines_in_period: 1, first_booking_date: "2026-01-01", last_booking_date: "2026-01-01", unmapped: true, unmapped_lines: 1, reason: "keine Zuordnung" },
      ],
    };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/api/bff/accounting/datev-mappings/import" && method === "POST") {
        expect(JSON.parse(String(init?.body))).toEqual({ content: "Konto;DATEV-Konto\n009000;9000\n001201;12x\n", ledger_id: null, dry_run: true });
        return jsonResponse(preview);
      }
      if (url.startsWith("/api/bff/accounting/datev-mappings/report?")) {
        expect(url).toContain(`ledger_id=${LEDGER}`);
        return jsonResponse(report);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<DatevMappingsAdmin initial={[existing]} ledgers={ledgers} canManage />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("CSV-Inhalt"), "Konto;DATEV-Konto\n009000;9000\n001201;12x\n");
    await user.click(screen.getByRole("button", { name: "Vorschau" }));
    await waitFor(() => expect(screen.getByText("Vorschau: 1 neu, 0 geändert, 0 unverändert, 1 fehlerhaft.")).toBeInTheDocument());
    expect(screen.getByText("DATEV-Konto muss numerisch sein.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Übernehmen" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Bericht laden" }));
    await waitFor(() =>
      expect(screen.getByText("1 Konten ohne Zuordnung, davon 1 mit Buchungen im Zeitraum.")).toBeInTheDocument(),
    );
    expect(screen.getByText("Saldenvortrag")).toBeInTheDocument();
    expect(screen.getByText("keine Zuordnung")).toBeInTheDocument();
    expect(screen.queryByText("zugeordnet")).not.toBeInTheDocument();
    await user.click(screen.getByLabelText("Nur nicht zugeordnete Konten anzeigen"));
    expect(screen.getByText("zugeordnet")).toBeInTheDocument();
  });

  it("hides maintenance without accounting:update", () => {
    renderIntl(<DatevMappingsAdmin initial={[existing]} ledgers={ledgers} canManage={false} />);
    expect(screen.getByText("Nur zur Ansicht. Die Pflege erfordert das Recht Buchhaltung ändern.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Anlegen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Vorschau" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bericht laden" })).toBeInTheDocument();
  });
});
