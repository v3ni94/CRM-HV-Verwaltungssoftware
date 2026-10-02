import { act, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LedgerLockForm } from "./LedgerLockForm";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

function fill(container: HTMLElement, value: string) {
  const input = container.querySelector('input[type="date"]') as HTMLInputElement;
  fireEvent.change(input, { target: { value } });
}

describe("LedgerLockForm", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("keeps the submit button disabled without a date", () => {
    renderIntl(<LedgerLockForm ledgerId="l1" lockedUntil={null} />);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("locks after confirmation via POST /accounting/ledgers/{id}/lock", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ locked_until: "2026-06-30", drafts_in_locked_period: 2, unclarified_bank_movements: 1 }));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderIntl(<LedgerLockForm ledgerId="l1" lockedUntil="2026-03-31" />);
    fill(container, "2026-06-30");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/accounting/ledgers/l1/lock");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ until: "2026-06-30" });
    expect(await screen.findByRole("status")).toBeInTheDocument();
    expect(refresh).toHaveBeenCalled();
  });

  it("does not post when the confirmation is declined", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { container } = renderIntl(<LedgerLockForm ledgerId="l1" lockedUntil={null} />);
    fill(container, "2026-06-30");
    await userEvent.click(screen.getByRole("button"));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the error for a forbidden lock (403)", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    const { container } = renderIntl(<LedgerLockForm ledgerId="l1" lockedUntil={null} />);
    fill(container, "2026-06-30");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });
});
