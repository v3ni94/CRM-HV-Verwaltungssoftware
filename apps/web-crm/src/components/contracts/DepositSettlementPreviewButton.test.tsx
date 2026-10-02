import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DepositSettlementPreviewButton } from "./DepositSettlementPreviewButton";

const C = "0192abcd-0000-7000-8000-000000000018";
const S = "0192abcd-0000-7000-8000-000000000019";

describe("DepositSettlementPreviewButton (GAG-29)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("opens the PDF preview from the BFF path", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({ ok: true, status: 200, blob: async () => new Blob(["%PDF"]) } as unknown as Response);
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    renderIntl(<DepositSettlementPreviewButton contractId={C} settlementId={S} />);
    await userEvent.click(screen.getByRole("button", { name: "PDF-Vorschau" }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/contracts/${C}/deposit-settlements/${S}/document-preview`);
    vi.advanceTimersByTime(60_000);
    expect(revoke).toHaveBeenCalledWith("blob:x");
    vi.useRealTimers();
  });

  it("shows the problem when the preview is refused", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ title: "Nicht gefunden", status: 404, detail: "Nicht gefunden." }, 404));
    renderIntl(<DepositSettlementPreviewButton contractId={C} settlementId={S} />);
    await userEvent.click(screen.getByRole("button", { name: "PDF-Vorschau" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
