import { screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AuditLogPanel, flattenChanges, type AuditRow } from "./AuditLogPanel";

const row: AuditRow = {
  id: "0192abcd-0000-7000-8000-000000000001",
  event_id: "0192abcd-0000-7000-8000-000000000002",
  entity_type: "contact",
  entity_id: "0192abcd-0000-7000-8000-000000000003",
  changes: { first_name: { old: "Anna", new: "Anna Maria" }, tags: { old: [], new: ["Beirat"] } },
  actor_user_id: "0192abcd-0000-7000-8000-000000000004",
  occurred_at: "2026-09-26T10:00:00+00:00",
};

describe("AuditLogPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("flattens changes into one row per field", () => {
    expect(flattenChanges(row.changes)).toEqual([
      { field: "first_name", oldValue: "Anna", newValue: "Anna Maria" },
      { field: "tags", oldValue: "[]", newValue: '["Beirat"]' },
    ]);
    expect(flattenChanges({ status: "active" })).toEqual([{ field: "status", oldValue: "", newValue: "active" }]);
  });

  it("loads the log with type and id filter and offers the CSV export", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse([row]));
    renderIntl(<AuditLogPanel entityType="contact" entityId={row.entity_id!} />);
    await waitFor(() => expect(screen.getByText("first_name")).toBeInTheDocument());
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/api/bff/tenant/audit-log?entity_type=contact&entity_id=${row.entity_id}&page=1&page_size=20`,
    );
    expect(screen.getByText("Anna Maria")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "CSV exportieren" })).toHaveAttribute(
      "href",
      `/api/bff/tenant/audit-log/export?entity_type=contact&entity_id=${row.entity_id}`,
    );
  });

  it("shows the empty state and a hint without permission", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse([]));
    renderIntl(<AuditLogPanel entityType="ticket" entityId="t1" />);
    await waitFor(() => expect(screen.getByText(/Noch keine Änderungen/)).toBeInTheDocument());
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ code: "forbidden" }, 403));
    renderIntl(<AuditLogPanel entityType="ticket" entityId="t2" />);
    await waitFor(() => expect(screen.getByText(/Berechtigung/)).toBeInTheDocument());
  });
});
