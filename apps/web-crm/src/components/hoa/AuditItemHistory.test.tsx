import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AuditItemHistory } from "./AuditItemHistory";

const ITEM = "0192abcd-0000-7000-8000-000000000401";

describe("AuditItemHistory", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the history on demand and shows old and new value per change", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse([
        { item_version: 2, changes: { note: { old: null, new: "Beleg fehlt" } }, occurred_at: "2026-09-26T10:00:00Z" },
        { item_version: 3, changes: { note: { old: "Beleg fehlt", new: "Beleg nachgereicht" }, status: { old: "open", new: "checked" } }, occurred_at: "2026-09-27T10:00:00Z" },
      ]),
    );
    renderIntl(<AuditItemHistory itemId={ITEM} />);
    await userEvent.click(screen.getByRole("button", { name: "Verlauf anzeigen" }));
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/hoa/audit-items/${ITEM}/history`);
    const list = await screen.findByTestId(`history-${ITEM}`);
    expect(list).toHaveTextContent("note: leer → Beleg fehlt");
    expect(list).toHaveTextContent("note: Beleg fehlt → Beleg nachgereicht");
    expect(list).toHaveTextContent("status: open → checked");
    await userEvent.click(screen.getByRole("button", { name: "Verlauf ausblenden" }));
    expect(screen.queryByTestId(`history-${ITEM}`)).not.toBeInTheDocument();
  });

  it("shows a note for an unchanged position", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]));
    renderIntl(<AuditItemHistory itemId={ITEM} />);
    await userEvent.click(screen.getByRole("button", { name: "Verlauf anzeigen" }));
    expect(await screen.findByText("Keine Änderungen seit Anlage.")).toBeInTheDocument();
  });
});
