import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ReserveOpeningChanges, type OpeningChange } from "./ReserveOpeningChanges";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const rows: OpeningChange[] = [
  { id: "oc1", status: "pending", reason: "Korrektur", changes: { opening_balance: { old: "100.00", new: "120.00" } }, requested_at: "2026-09-30T10:00:00Z" },
  { id: "oc2", status: "applied", reason: null, changes: {}, requested_at: "2026-09-29T10:00:00Z" },
];

describe("ReserveOpeningChanges", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    refresh.mockClear();
  });

  it("offers decisions only for pending changes and posts the approval", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<ReserveOpeningChanges name="Rücklage A" rows={rows} />);
    expect(screen.getAllByRole("button")).toHaveLength(2);
    await act(async () => {
      await userEvent.click(screen.getAllByRole("button")[0]!);
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/hoa/reserve-opening-changes/oc1/approve");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(refresh).toHaveBeenCalled();
  });

  it("shows the error and does not refresh on 403 (second person required)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<ReserveOpeningChanges name="Rücklage A" rows={rows} />);
    await act(async () => {
      await userEvent.click(screen.getAllByRole("button")[1]!);
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });
});
