import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ExportKinds } from "./ExportKinds";
import { MigrationExtras } from "./MigrationExtras";
import { MigrationHistory } from "./MigrationHistory";

const property = { property_id: "p1", property_number: "100", property_name: "Musterstraße", ledgers: [{ id: "l1", name: "WEG" }] };
const columns = { columns: { date: "Datum" }, customised: false, fields: [{ name: "date", label: "Buchungsdatum", required: true }] };
const draft = { id: "a1", status: "draft", review_scope: "Salden", responsible_persons: [{ name: "A", role: "GF" }], non_migratable_data: "", fallback_plan: "x", archive_concept: "y", created_at: "2026-10-01T08:00:00Z" };

describe("GAG-14 migration masks", () => {
  afterEach(() => vi.restoreAllMocks());

  it("edits a draft acceptance with PUT and hides edit for signed records", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/status")) return jsonResponse([property]);
      if (url.endsWith("/journal-columns")) return jsonResponse(columns);
      if (url.endsWith("/acceptance/a1")) return jsonResponse({ ...draft, review_scope: "Salden und Kautionen" });
      return jsonResponse([draft, { ...draft, id: "a2", status: "signed" }]);
    });
    renderIntl(<MigrationExtras canUpdate canApprove />);
    await screen.findByText(/Buchungsdatum/);
    await userEvent.selectOptions(within(screen.getByRole("region", { name: "Migrationsabnahme je Objekt" })).getByLabelText("Objekt"), "p1");
    expect(await screen.findAllByTestId("acceptance")).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Bearbeiten" })).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Bearbeiten" }));
    const scope = screen.getByLabelText("Prüfumfang");
    await userEvent.clear(scope);
    await userEvent.type(scope, "Salden und Kautionen");
    await userEvent.click(screen.getByRole("button", { name: "Änderungen speichern" }));
    const put = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/acceptance/a1"));
    expect(put?.[1]?.method).toBe("PUT");
    expect(JSON.parse(String(put?.[1]?.body))).toMatchObject({ review_scope: "Salden und Kautionen", responsible_persons: [{ name: "A", role: "GF" }] });
  });

  it("lists export kinds with required columns", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse([{ kind: "journal", label: "Journal", columns: ["Datum", "Betrag"], required: ["Datum"], reconciled: true }]),
    );
    renderIntl(<ExportKinds />);
    expect(await screen.findByText("Journal")).toBeInTheDocument();
    expect(screen.getByTestId("export-kinds")).toHaveTextContent("Datum *, Betrag");
  });

  it("loads the open item totals per kind", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ ledger_id: "L1", kinds: { deposit: { count: 2, original: "300.00", paid: "100.00", open: "200.00" } } }),
    );
    renderIntl(<MigrationHistory ledgers={[{ id: "L1", name: "WEG" }]} canTickets={false} />);
    await userEvent.selectOptions(screen.getByLabelText("Buchungskreis"), "L1");
    await userEvent.click(screen.getByRole("button", { name: "Summen je Art" }));
    const table = await screen.findByTestId("history-summary");
    expect(table).toHaveTextContent("Kaution");
    expect(table).toHaveTextContent("200,00");
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/open-items/summary?ledger_id=L1");
  });
});
