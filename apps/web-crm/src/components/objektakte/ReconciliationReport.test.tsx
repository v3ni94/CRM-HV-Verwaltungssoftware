import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ReconciliationReport, type ReconciliationReport as Report } from "./ReconciliationReport";

const report: Report = {
  generated_at: "2026-09-27T10:15:00Z",
  ok: false,
  totals: {
    objects: 3,
    objektakte_documents: 5,
    crm_documents: 4,
    missing_in_crm: 2,
    missing_in_objektakte: 1,
    hash_mismatches: 1,
    placeholders: 1,
    objects_with_differences: 2,
  },
  objects: [
    {
      object_number: "077",
      objektakte_count: 1,
      crm_count: 1,
      missing_in_crm: [],
      missing_in_crm_total: 0,
      missing_in_objektakte: [],
      missing_in_objektakte_total: 0,
      hash_mismatches: [],
      hash_mismatch_total: 0,
      placeholders: 0,
      ok: true,
    },
    {
      object_number: "291",
      objektakte_count: 4,
      crm_count: 3,
      missing_in_crm: ["4", "6"],
      missing_in_crm_total: 2,
      missing_in_objektakte: [],
      missing_in_objektakte_total: 0,
      hash_mismatches: [{ source_id: "2", crm: "b".repeat(64), objektakte: "c".repeat(64) }],
      hash_mismatch_total: 1,
      placeholders: 1,
      ok: false,
    },
    {
      object_number: "ohne_objekt",
      objektakte_count: 0,
      crm_count: 1,
      missing_in_crm: [],
      missing_in_crm_total: 0,
      missing_in_objektakte: ["8"],
      missing_in_objektakte_total: 1,
      hash_mismatches: [],
      hash_mismatch_total: 0,
      placeholders: 0,
      ok: false,
    },
  ],
};

describe("ReconciliationReport", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads the report for one object and lists only objects with differences", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(report));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderIntl(<ReconciliationReport />);

    await user.type(screen.getByPlaceholderText("291"), "291");
    await user.click(screen.getByRole("button", { name: "Abgleich laden" }));

    await waitFor(() => expect(screen.getByTestId("reconciliation-summary")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/bff/objektakte/reconciliation?number=291");
    expect(screen.getByTestId("reconciliation-summary")).toHaveTextContent("2 von 3 Objekten mit Abweichungen");
    expect(screen.getByTestId("reconciliation-totals")).toHaveTextContent("Fehlt im CRM2");

    const table = screen.getByTestId("reconciliation-table");
    expect(table).toHaveTextContent("2: 4, 6");
    expect(table).toHaveTextContent("Ohne Objekt");
    expect(table).not.toHaveTextContent("077");

    await user.click(screen.getByLabelText("Nur Objekte mit Abweichungen"));
    expect(screen.getByTestId("reconciliation-table")).toHaveTextContent("077");
  });

  it("shows the upstream error when objektakte is not reachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(jsonResponse({ code: "MHVP-OAK-0002", title: "objektakte nicht erreichbar" }, 502)),
    );
    const user = userEvent.setup();
    renderIntl(<ReconciliationReport />);
    await user.click(screen.getByRole("button", { name: "Abgleich laden" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
