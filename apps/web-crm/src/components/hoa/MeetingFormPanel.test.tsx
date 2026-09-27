import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MeetingFormPanel, type MeetingFormData } from "./MeetingFormPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
const M = "0192abcd-0000-7000-8000-000000000031";

const base: MeetingFormData = {
  mode: "hybrid",
  status: "invited",
  invited_at: "2026-10-01",
  invitation_weeks: 3,
  latest_invitation_at: "2026-10-09",
  invitation_short_notice: false,
  invitation_short_notice_reason: null,
  short_notice_note: null,
  invitation_notice: "Die Versammlung findet als hybride Versammlung statt.",
  virtual_basis: null,
  virtual_basis_valid_until: null,
  has_dial_in: false,
};

describe("MeetingFormPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the latest invitation date in TT.MM.JJJJ, the notice and the attendance channels", () => {
    renderIntl(
      <MeetingFormPanel
        meetingId={M}
        data={{ ...base, invitation_short_notice: true, short_notice_note: "Vermerk zur Einladungsfrist: Grund X" }}
        attendance={[
          { contract_id: "c1", unit_number: "01", party_name: "Eig 1", channel: "online", proxy_name: null },
          { contract_id: "c2", unit_number: "02", party_name: "Eig 2", channel: "proxy", proxy_name: "Vertreter" },
        ]}
      />,
    );
    expect(screen.getByTestId("latest-invitation")).toHaveTextContent("09.10.2026");
    expect(screen.getByTestId("short-notice")).toHaveTextContent("Grund X");
    expect(screen.getByTestId("invitation-notice")).toHaveTextContent("hybride Versammlung");
    expect(screen.getByTestId("attendance-list")).toHaveTextContent("online");
    expect(screen.getByTestId("attendance-list")).toHaveTextContent("Vollmacht (Vertreter)");
  });

  it("saves dial-in data via PUT and hides the form for presence meetings", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ id: M }));
    renderIntl(<MeetingFormPanel meetingId={M} data={base} attendance={[]} />);
    await userEvent.type(screen.getByTestId("dial-in-url"), "https://meet.example.org/weg");
    await userEvent.type(screen.getByTestId("dial-in-access"), "PIN 1234");
    await userEvent.click(screen.getByRole("button", { name: "Einwahldaten speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(`/hoa/meetings/${M}/dial-in`);
    const body = JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body)) as Record<string, string>;
    expect(body.dial_in_access).toBe("PIN 1234");
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();

    renderIntl(<MeetingFormPanel meetingId={M} data={{ ...base, mode: "presence", invitation_notice: null }} attendance={[]} />);
    expect(screen.getAllByTestId("dial-in-url")).toHaveLength(1);
  });
});
