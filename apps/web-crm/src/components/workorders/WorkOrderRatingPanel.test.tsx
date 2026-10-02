import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { WorkOrderRatingPanel } from "./WorkOrderRatingPanel";

const base = { mode: "off", can_rate: true, staff_rated: false, ratings: [] };

describe("WorkOrderRatingPanel", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("hides ratings while the switch is off but allows rating", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(base));
    renderIntl(<WorkOrderRatingPanel orderId="o1" canEdit />);
    expect(await screen.findByText(/Anzeige von Bewertungen ist ausgeschaltet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bewertung speichern" })).toBeInTheDocument();
  });

  it("saves the rating and reloads", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(base))
      .mockResolvedValueOnce(jsonResponse({ id: "r" }, 201))
      .mockResolvedValueOnce(
        jsonResponse({
          ...base,
          mode: "staff",
          staff_rated: true,
          ratings: [{ id: "r", party: "staff", stars: 3, comment: null }],
        }),
      );
    renderIntl(<WorkOrderRatingPanel orderId="o1" canEdit />);
    await user.selectOptions(await screen.findByLabelText("Sterne"), "3");
    await user.click(screen.getByRole("button", { name: "Bewertung speichern" }));
    await waitFor(() => expect(screen.getByText("Verwaltung:")).toBeInTheDocument());
    expect(screen.getByText(/3 von 5 Sternen/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bewertung speichern" })).not.toBeInTheDocument();
  });

  it("offers no form without edit permission or before completion", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ ...base, can_rate: false }));
    renderIntl(<WorkOrderRatingPanel orderId="o1" canEdit={false} />);
    expect(await screen.findByText(/erst nach Abschluss/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bewertung speichern" })).not.toBeInTheDocument();
  });
});
