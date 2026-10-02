import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { WorkOrderRating } from "./WorkOrderRating";

const open = { mode: "off", can_rate: true, own: null, provider_summary: null };

describe("WorkOrderRating", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("renders nothing when the order cannot be rated", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ ...open, can_rate: false }));
    const { container } = renderIntl(<WorkOrderRating orderId="o1" />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("submits the stars once and shows the own rating afterwards", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(open))
      .mockResolvedValueOnce(jsonResponse({ id: "r1", stars: 4 }, 201))
      .mockResolvedValueOnce(jsonResponse({ ...open, can_rate: false, own: { stars: 4 } }));
    renderIntl(<WorkOrderRating orderId="o1" />);
    await user.selectOptions(await screen.findByLabelText("Sterne"), "4");
    await user.click(screen.getByRole("button", { name: "Bewertung abgeben" }));
    await waitFor(() => expect(screen.getByText(/Ihre Bewertung: 4 von 5 Sternen/)).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(
      "/api/bff/portal/work-orders/o1/rating",
      expect.objectContaining({ method: "POST" }),
    );
    expect(screen.queryByRole("button", { name: "Bewertung abgeben" })).not.toBeInTheDocument();
  });

  it("shows the provider average only when delivered by the switch", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ ...open, mode: "all", provider_summary: { rated_count: 3, average: "4.3" } }),
    );
    renderIntl(<WorkOrderRating orderId="o1" />);
    expect(await screen.findByText(/Durchschnitt des Dienstleisters: 4.3 von 5 Sternen \(3 Bewertungen\)/)).toBeInTheDocument();
  });
});
