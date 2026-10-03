import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AllocationDetermination, REASON_DETERMINED } from "./AllocationDetermination";

const cands = {
  candidates: [
    { open_item_id: "i1", remaining: "100.00", reasons: [REASON_DETERMINED], allocation_reason: REASON_DETERMINED },
    { open_item_id: "i2", remaining: "100.00", reasons: [], allocation_reason: "Regel ohne Bestimmung" },
  ],
};

describe("AllocationDetermination", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the determined item without conflict when it is selected", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(cands));
    const onChange = vi.fn();
    renderIntl(<AllocationDetermination txId="t1" selectedItemIds={["i1"]} onChange={onChange} />);
    expect(await screen.findByText(REASON_DETERMINED)).toBeInTheDocument();
    expect(screen.queryByTestId("determination-conflict")).toBeNull();
    expect(onChange).toHaveBeenLastCalledWith({ conflict: false, reason: "" });
  });

  it("requires a reason when another item than the determined one is chosen", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(cands));
    const onChange = vi.fn();
    renderIntl(<AllocationDetermination txId="t1" selectedItemIds={["i2"]} onChange={onChange} />);
    expect(await screen.findByTestId("determination-conflict")).toBeInTheDocument();
    expect(onChange).toHaveBeenLastCalledWith({ conflict: true, reason: "" });
    await userEvent.type(screen.getByLabelText(/Begründung der Abweichung/), "Zahler hat telefonisch anders bestimmt");
    expect(onChange).toHaveBeenLastCalledWith({ conflict: true, reason: "Zahler hat telefonisch anders bestimmt" });
  });

  it("states that no determination was found and tolerates a failed load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ candidates: [] }));
    const { unmount } = renderIntl(<AllocationDetermination txId="t1" selectedItemIds={[]} onChange={vi.fn()} />);
    expect(await screen.findByText(/keine Tilgungsbestimmung erkannt/)).toBeInTheDocument();
    unmount();
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ title: "x", status: 500 }, 500));
    renderIntl(<AllocationDetermination txId="t2" selectedItemIds={[]} onChange={vi.fn()} />);
    expect(await screen.findByText(/konnte nicht geladen werden/)).toBeInTheDocument();
  });
});
