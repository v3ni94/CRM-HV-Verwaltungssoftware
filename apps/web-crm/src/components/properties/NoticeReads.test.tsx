import { fireEvent, screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { NoticeReads } from "./NoticeReads";

const ID = "11111111-1111-7111-8111-111111111111";

describe("NoticeReads (GAL-307)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the read status on demand and shows the no-proof note", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ recipient_count: 4, read_count: 1, reads: [{ account_id: "a1", contact_id: "99999999-9999-7999-8999-999999999999", read_at: "2026-10-01T10:00:00Z" }], note: "x" }),
    );
    renderIntl(<NoticeReads noticeId={ID} />);
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Lesestatus anzeigen" }));
    expect(await screen.findByText("1 von 4 Portalkonten haben den Aushang bestätigt.")).toBeInTheDocument();
    expect(screen.getByText(/Keine Zustellung und kein rechtlich bewerteter Zugang/)).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0]![0])).toBe(`/api/bff/notices/${ID}/reads`);
  });

  it("shows the error of the API", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "Nicht gefunden" }, 404));
    renderIntl(<NoticeReads noticeId={ID} />);
    fireEvent.click(screen.getByRole("button", { name: "Lesestatus anzeigen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
