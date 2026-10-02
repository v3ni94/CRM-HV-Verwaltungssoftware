import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankSyncLog } from "./BankSyncLog";

const RUNS = [
  {
    id: "r1",
    source: "ebics:C53",
    status: "failed",
    counts: {},
    errors: ["MHVP-BANK-0050: EBICS-Übertragung nicht verfügbar"],
    property_bank_account_id: null,
    document_id: null,
    connection_id: null,
    created_at: "2026-10-02T04:40:00Z",
  },
  {
    id: "r2",
    source: "file_import",
    status: "done",
    counts: { new: 3, duplicates: 1, possible_duplicates: 1, auto_posted: 2, proposals: 1 },
    errors: [],
    property_bank_account_id: "a1",
    document_id: "d1",
    connection_id: null,
    created_at: "2026-10-01T08:00:00Z",
  },
];

describe("BankSyncLog", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists runs with counters and errors", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(RUNS));
    renderIntl(<BankSyncLog />);
    const table = await screen.findByTestId("bank-sync-log");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/banking/runs?limit=20");
    expect(table).toHaveTextContent("MHVP-BANK-0050");
    expect(table).toHaveTextContent("ebics:C53");
    expect(table).toHaveTextContent("02.10.2026");
    const cells = screen.getAllByRole("row")[2]?.querySelectorAll("td");
    expect(cells?.[3]).toHaveTextContent("3");
    expect(cells?.[4]).toHaveTextContent("2");
    expect(cells?.[5]).toHaveTextContent("2");
  });

  it("shows the empty state", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    renderIntl(<BankSyncLog />);
    expect(await screen.findByText("Noch keine Läufe.")).toBeInTheDocument();
  });
});
