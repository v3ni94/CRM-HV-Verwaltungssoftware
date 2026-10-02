import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MigrationExtras } from "./MigrationExtras";

const property = { property_id: "p1", property_number: "100", property_name: "Musterstraße", ledgers: [{ id: "l1", name: "WEG" }] };
const columns = { columns: { date: "Datum" }, customised: false, fields: [{ name: "date", label: "Buchungsdatum", required: true }] };
const acceptance = { id: "a1", status: "draft", review_scope: "Salden", responsible_persons: [{ name: "A", role: "GF" }], non_migratable_data: "", fallback_plan: "x", archive_concept: "y", created_at: "2026-10-01T08:00:00Z" };

describe("MigrationExtras", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows acceptance records of a property and signs a draft", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.endsWith("/status")) return Promise.resolve(jsonResponse([property]));
      if (url.endsWith("/journal-columns")) return Promise.resolve(jsonResponse(columns));
      if (url.endsWith("/sign")) return Promise.resolve(jsonResponse({ ...acceptance, status: "signed" }));
      void init;
      return Promise.resolve(jsonResponse([acceptance]));
    });
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<MigrationExtras canUpdate canApprove />);
    await screen.findByText(/Buchungsdatum/);
    await userEvent.selectOptions(screen.getByLabelText("Objekt"), "p1");
    expect(await screen.findByTestId("acceptance")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Unterzeichnen" }));
    expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith("/acceptance/a1/sign"))).toBe(true);
  });
});
