import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InvoiceSecondApproval } from "./InvoiceSecondApproval";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

const REQUIRED = { enabled: true, limit_amount: "5000.00", second_approval_required: true, second_approval_valid: false, second_approved_by: null };

describe("InvoiceSecondApproval (GAI-615)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("renders nothing when no second approval is needed", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ ...REQUIRED, enabled: false, second_approval_required: false }));
    const { container } = renderIntl(<InvoiceSecondApproval invoiceId="i1" canApprove />);
    await vi.waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("names the limit and hides the action without the right", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(REQUIRED));
    renderIntl(<InvoiceSecondApproval invoiceId="i1" canApprove={false} />);
    expect(await screen.findByText(/5\.000,00 EUR/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Zweite Freigabe erteilen" })).not.toBeInTheDocument();
  });

  it("asks for confirmation, posts once and refreshes", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(REQUIRED))
      .mockResolvedValueOnce(jsonResponse({ ...REQUIRED, second_approval_valid: true }));
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderIntl(<InvoiceSecondApproval invoiceId="i1" canApprove />);
    const button = await screen.findByRole("button", { name: "Zweite Freigabe erteilen" });
    await userEvent.click(button);
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await userEvent.click(button);
    expect(await screen.findByText("Zweite Freigabe erteilt.")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1]![0]).toBe("/api/bff/accounting/tax/invoices/i1/second-approval");
    expect((fetchMock.mock.calls[1]![1] as RequestInit).method).toBe("POST");
    expect(refresh).toHaveBeenCalled();
  });

  it("shows the refusal of the four eyes check", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(REQUIRED)).mockResolvedValueOnce(jsonResponse({ title: "Gleiche Person", status: 403 }, 403));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<InvoiceSecondApproval invoiceId="i1" canApprove />);
    await userEvent.click(await screen.findByRole("button", { name: "Zweite Freigabe erteilen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
