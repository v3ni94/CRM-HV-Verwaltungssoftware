import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { WorkOrderDetail } from "./WorkOrderDetail";
import type { WorkOrder } from "./types";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh }),
}));

const order: WorkOrder = {
  id: "o1",
  description: "Heizung reparieren",
  status: "requested",
  quote_amount: null,
  scheduled_at: null,
};

describe("WorkOrderDetail", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.spyOn(window, "confirm").mockReturnValue(true);
    refresh.mockReset();
  });

  it("declines the order after confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ ...order, status: "rejected" }));
    renderIntl(<WorkOrderDetail order={order} />);
    await user.click(screen.getByRole("button", { name: "Auftrag ablehnen" }));
    await waitFor(() => expect(screen.getByText("Auftrag wurde abgelehnt.")).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(
      "/api/bff/portal/work-orders/o1/decline",
      expect.objectContaining({ method: "POST" }),
    );
    expect(refresh).toHaveBeenCalled();
  });

  it("does not call the API when the confirmation is cancelled", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = userEvent.setup();
    renderIntl(<WorkOrderDetail order={order} />);
    await user.click(screen.getByRole("button", { name: "Auftrag ablehnen" }));
    expect(fetch).not.toHaveBeenCalled();
  });
});
