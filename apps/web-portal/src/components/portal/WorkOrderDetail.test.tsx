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
  appointment_proposals: [],
  photos: [],
};

describe("WorkOrderDetail", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    refresh.mockReset();
  });

  it("declines the order after the inline confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ ...order, status: "rejected" }));
    renderIntl(<WorkOrderDetail order={order} />);
    await user.click(screen.getByRole("button", { name: "Auftrag ablehnen" }));
    // First click only opens the confirmation, nothing is sent yet.
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByText("Auftrag wirklich ablehnen?")).toBeInTheDocument();
    const confirm = screen.getByRole("button", { name: "Ablehnen bestätigen" });
    expect(confirm).toHaveFocus();
    await user.click(confirm);
    await waitFor(() => expect(screen.getByText("Auftrag wurde abgelehnt.")).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(
      "/api/bff/portal/work-orders/o1/decline",
      expect.objectContaining({ method: "POST" }),
    );
    expect(refresh).toHaveBeenCalled();
  });

  it("does not call the API when the inline confirmation is cancelled", async () => {
    const user = userEvent.setup();
    renderIntl(<WorkOrderDetail order={order} />);
    await user.click(screen.getByRole("button", { name: "Auftrag ablehnen" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByText("Auftrag wirklich ablehnen?")).not.toBeInTheDocument();
    // Focus returns to the decline button.
    expect(screen.getByRole("button", { name: "Auftrag ablehnen" })).toHaveFocus();
  });

  it("shows a sending status while the request is running", async () => {
    const user = userEvent.setup();
    let resolve: (value: Response) => void = () => {};
    vi.mocked(fetch).mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    renderIntl(<WorkOrderDetail order={order} />);
    await user.click(screen.getByRole("button", { name: "Auftrag ablehnen" }));
    await user.click(screen.getByRole("button", { name: "Ablehnen bestätigen" }));
    expect(await screen.findByText("Wird gesendet")).toHaveAttribute("role", "status");
    resolve(jsonResponse({ ...order, status: "rejected" }));
    await waitFor(() => expect(screen.queryByText("Wird gesendet")).not.toBeInTheDocument());
  });

  it("sends up to three appointment proposals once the order is approved (A58)", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse([{ id: "p1" }], 201));
    renderIntl(<WorkOrderDetail order={{ ...order, status: "approved" }} />);
    await user.click(screen.getByRole("button", { name: "Terminvorschläge senden" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte mindestens einen Termin angeben.");
    expect(fetch).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText("Vorschlag 1"), "2026-10-05T09:00");
    await user.type(screen.getByLabelText("Vorschlag 3 (optional)"), "2026-10-06T14:00");
    await user.type(screen.getByLabelText("Hinweis (optional)"), "bitte Zugang");
    await user.click(screen.getByRole("button", { name: "Terminvorschläge senden" }));
    await waitFor(() =>
      expect(screen.getByText("Die Terminvorschläge wurden an den Bewohner gesendet.")).toBeInTheDocument(),
    );
    const first = vi.mocked(fetch).mock.calls[0];
    expect(String(first?.[0])).toBe("/api/bff/portal/work-orders/o1/appointment-proposals");
    const body = JSON.parse(String(first?.[1]?.body));
    expect(body.proposals).toHaveLength(2);
    expect(body.proposals[0].note).toBe("bitte Zugang");
    expect(new Date(body.proposals[0].starts_at).toISOString()).toBe(new Date("2026-10-05T09:00").toISOString());
  });

  it("hides the proposal form before approval and lists sent proposals with status", () => {
    renderIntl(
      <WorkOrderDetail
        order={{
          ...order,
          status: "scheduled",
          scheduled_at: "2026-10-06T12:00:00Z",
          appointment_proposals: [
            { id: "p1", work_order_id: "o1", starts_at: "2026-10-05T07:00:00Z", note: null, status: "declined", decided_at: null },
            { id: "p2", work_order_id: "o1", starts_at: "2026-10-06T12:00:00Z", note: null, status: "accepted", decided_at: null },
          ],
        }}
      />,
    );
    expect(screen.getByText("Nicht gewählt")).toBeInTheDocument();
    expect(screen.getByText("Bestätigt")).toBeInTheDocument();
    expect(screen.getByText("Termin: 06.10.2026, 14:00")).toBeInTheDocument();
  });

  it("hides the proposal form while the order is not approved", () => {
    renderIntl(<WorkOrderDetail order={order} />);
    expect(screen.queryByRole("button", { name: "Terminvorschläge senden" })).not.toBeInTheDocument();
  });

  it("uploads execution photos and links them via document_ids", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ id: "d1" }, 201))
      .mockResolvedValueOnce(jsonResponse({ ...order, status: "done" }));
    renderIntl(<WorkOrderDetail order={{ ...order, status: "scheduled" }} />);
    await user.type(screen.getByLabelText("Ausführungsbericht"), "Ziegel ersetzt");
    await user.upload(
      screen.getByLabelText("Fotos der Ausführung (optional, JPEG oder PNG)"),
      new File(["a"], "fertig.jpg", { type: "image/jpeg" }),
    );
    await user.click(screen.getByRole("button", { name: "Ausführung dokumentieren" }));
    await waitFor(() => expect(screen.getByText("Die Ausführung wurde dokumentiert.")).toBeInTheDocument());
    const calls = vi.mocked(fetch).mock.calls.map(([url, init]) => [String(url), init ?? {}] as const);
    expect(calls[0]?.[0]).toBe("/api/bff/portal/uploads");
    expect(calls[1]?.[0]).toBe("/api/bff/portal/work-orders/o1/complete");
    expect(JSON.parse(String(calls[1]?.[1].body))).toEqual({ report: "Ziegel ersetzt", document_ids: ["d1"] });
  });

  it("offers quote and decline while requested, but no report or invoice yet", () => {
    renderIntl(<WorkOrderDetail order={order} />);
    expect(screen.getByRole("button", { name: "Angebot abgeben" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Auftrag ablehnen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Termin festlegen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ausführung dokumentieren" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rechnung einreichen" })).not.toBeInTheDocument();
  });

  it("offers appointment and report once approved, but no quote resubmission", () => {
    renderIntl(<WorkOrderDetail order={{ ...order, status: "approved" }} />);
    expect(screen.queryByRole("button", { name: "Angebot abgeben" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Auftrag ablehnen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Termin festlegen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ausführung dokumentieren" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rechnung einreichen" })).not.toBeInTheDocument();
  });

  it("offers only the invoice once the work is done", () => {
    renderIntl(<WorkOrderDetail order={{ ...order, status: "done" }} />);
    expect(screen.getByRole("button", { name: "Rechnung einreichen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Angebot abgeben" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Auftrag ablehnen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Termin festlegen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ausführung dokumentieren" })).not.toBeInTheDocument();
  });

  it("offers no actions on a closed order", () => {
    for (const status of ["rejected", "cancelled", "accepted", "invoiced"]) {
      const { unmount } = renderIntl(<WorkOrderDetail order={{ ...order, status }} />);
      expect(screen.queryByRole("button", { name: "Auftrag ablehnen" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Angebot abgeben" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Termin festlegen" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Ausführung dokumentieren" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Rechnung einreichen" })).not.toBeInTheDocument();
      unmount();
    }
  });

  it("shows all actions for an unknown status (defensive default)", () => {
    renderIntl(<WorkOrderDetail order={{ ...order, status: "unbekannt" }} />);
    expect(screen.getByRole("button", { name: "Auftrag ablehnen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Angebot abgeben" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Termin festlegen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ausführung dokumentieren" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rechnung einreichen" })).toBeInTheDocument();
  });
});
