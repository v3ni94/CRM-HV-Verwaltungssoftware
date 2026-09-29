import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LexofficeOutbox, type LexofficeOutboxRow } from "./LexofficeOutbox";

const row = (over: Partial<LexofficeOutboxRow>): LexofficeOutboxRow => ({
  id: "o-1",
  config_id: "cfg-1",
  kind: "contact_update",
  target_kind: "contact",
  target_id: "c-1",
  status: "pending",
  attempts: 1,
  next_attempt_at: "2026-09-29T10:00:00Z",
  last_status_code: null,
  last_error: null,
  sent_at: null,
  created_at: "2026-09-29T09:00:00Z",
  ...over,
});

describe("LexofficeOutbox", () => {
  afterEach(() => vi.restoreAllMocks());

  it("offers retry only on failed rows and reloads after it", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (init?.method === "POST") return jsonResponse(row({ id: "o-2", status: "pending", attempts: 0 }), 200);
      expect(String(input)).toContain("config_id=cfg-1");
      return jsonResponse({ items: [row({}), row({ id: "o-2", status: "failed", attempts: 7, last_error: "Status 406, person.lastName: validation_failure" })] }, 200);
    });
    renderIntl(<LexofficeOutbox configId="cfg-1" canManage />);
    await waitFor(() => expect(screen.getByText("Status 406, person.lastName: validation_failure")).toBeInTheDocument());
    expect(screen.getAllByRole("button", { name: "Erneut versuchen" })).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Erneut versuchen" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Eintrag erneut eingeplant."));
    expect(fetchMock.mock.calls.some(([u, i]) => String(u).endsWith("/outbox/o-2/retry") && i?.method === "POST")).toBe(true);
  });

  it("hides retry without the permission", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ items: [row({ status: "failed" })] }, 200));
    renderIntl(<LexofficeOutbox configId={null} canManage={false} />);
    await waitFor(() => expect(screen.getByText("Fehlgeschlagen")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Erneut versuchen" })).not.toBeInTheDocument();
  });
});
