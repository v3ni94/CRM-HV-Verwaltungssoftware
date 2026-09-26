import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AppointmentProposals } from "./AppointmentProposals";
import type { AppointmentProposal } from "./types";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh }),
}));

const first: AppointmentProposal = {
  id: "p1",
  work_order_id: "o1",
  starts_at: "2026-10-05T07:00:00Z",
  note: null,
  status: "proposed",
  decided_at: null,
};
const second: AppointmentProposal = { ...first, id: "p2", starts_at: "2026-10-06T12:00:00Z", note: "nachmittags" };
const proposals: AppointmentProposal[] = [first, second];

describe("AppointmentProposals", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    refresh.mockReset();
  });

  it("renders nothing without proposals", () => {
    const { container } = renderIntl(<AppointmentProposals proposals={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows open proposals in Berlin time and confirms the chosen one (A58)", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ order: { status: "scheduled" }, proposal: { id: "p2" } }));
    renderIntl(<AppointmentProposals proposals={proposals} />);
    expect(screen.getByText("05.10.2026, 09:00")).toBeInTheDocument();
    expect(screen.getByText("06.10.2026, 14:00")).toBeInTheDocument();
    expect(screen.getByText("(nachmittags)")).toBeInTheDocument();
    const buttons = screen.getAllByRole("button", { name: "Diesen Termin bestätigen" });
    await user.click(buttons[1] as HTMLElement);
    await waitFor(() => expect(screen.getByText("Der Termin wurde bestätigt.")).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(
      "/api/bff/portal/work-orders/o1/appointment-proposals/p2/accept",
      expect.objectContaining({ method: "POST" }),
    );
    expect(refresh).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Diesen Termin bestätigen" })).not.toBeInTheDocument();
  });

  it("shows the confirmed appointment and the API error", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ title: "Konflikt", detail: "Nicht mehr offen." }, 409));
    renderIntl(
      <AppointmentProposals proposals={[{ ...first, status: "accepted", decided_at: "2026-10-01T10:00:00Z" }, second]} />,
    );
    expect(screen.getByText("Bestätigter Termin:")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Diesen Termin bestätigen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nicht mehr offen.");
    expect(refresh).not.toHaveBeenCalled();
  });
});
