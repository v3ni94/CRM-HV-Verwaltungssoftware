import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OnlineMeetingPanel } from "./OnlineMeetingPanel";
import type { PortalMeetingDetail } from "./types";

const MID = "00000000-0000-7000-8000-000000000001";
const U1 = "00000000-0000-7000-8000-0000000000a1";
const U3 = "00000000-0000-7000-8000-0000000000a3";

function detail(over: Partial<PortalMeetingDetail> = {}): PortalMeetingDetail {
  return {
    id: MID,
    mode: "hybrid",
    status: "invited",
    online_enabled: true,
    online_note: "Hinweis AD06",
    conference_url: "https://meet.example.org/ad06",
    conference_access: "PIN 0606",
    own_contract_ids: [U1],
    confirmed_contract_ids: [U1],
    represented_contract_ids: [U3],
    units: [
      { contract_id: U1, unit_number: "01", own: true },
      { contract_id: U3, unit_number: "03", own: false },
    ],
    items: [
      { id: "i1", position: 1, title: "Dachsanierung", proposal: null, voting_state: "open", voted_contract_ids: [U3], result: null },
      { id: "i2", position: 2, title: "Hausordnung", proposal: null, voting_state: "announced", voted_contract_ids: [], result: { status: "positive", votes: { yes: "2", no: "1", abstain: "0" } } },
    ],
    speaker_requests: [],
    ...over,
  };
}

describe("OnlineMeetingPanel", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn()));

  it("shows the disabled note when the tenant switch is off (AD06)", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockImplementation(() => Promise.resolve(jsonResponse(detail({ online_enabled: false }))));
    renderIntl(<OnlineMeetingPanel meetingId={MID} />);
    await user.click(screen.getByRole("button", { name: "Online-Teilnahme anzeigen" }));
    expect(await screen.findByText(/nicht freigeschaltet/)).toBeInTheDocument();
    expect(screen.queryByText("Videokonferenz öffnen")).not.toBeInTheDocument();
  });

  it("votes only on open items for units not yet voted, results only when announced", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockImplementation(() => Promise.resolve(jsonResponse(detail())));
    renderIntl(<OnlineMeetingPanel meetingId={MID} />);
    await user.click(screen.getByRole("button", { name: "Online-Teilnahme anzeigen" }));
    expect(await screen.findByRole("link", { name: "Videokonferenz öffnen" })).toHaveAttribute("href", "https://meet.example.org/ad06");
    expect(screen.getByText("Einheit 03: abgestimmt")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Ja" })).toHaveLength(1);
    expect(screen.getByText("Ergebnis: Ja 2, Nein 1, Enthaltung 0")).toBeInTheDocument();
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ id: "v1", channel: "online" }, 201)).mockImplementation(() => Promise.resolve(jsonResponse(detail())));
    await user.click(screen.getByRole("button", { name: "Nein" }));
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([url, init]) => url === `/api/bff/portal/meetings/${MID}/agenda/i1/votes` && (init as RequestInit).body === JSON.stringify({ contract_id: U1, choice: "no" }))).toBe(true),
    );
  });

  it("confirms the participation before voting", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockImplementation(() => Promise.resolve(jsonResponse(detail({ confirmed_contract_ids: [] }))));
    renderIntl(<OnlineMeetingPanel meetingId={MID} />);
    await user.click(screen.getByRole("button", { name: "Online-Teilnahme anzeigen" }));
    expect(await screen.findByRole("button", { name: "Online-Teilnahme zusagen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ja" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Wortmeldung abgeben" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Online-Teilnahme zusagen" }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => url === `/api/bff/portal/meetings/${MID}/participation`)).toBe(true));
  });
});

describe("OnlineMeetingPanel vote conflict (AE31)", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn()));

  it("tells the owner when the vote is stored for review and not counted", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockImplementation(() => Promise.resolve(jsonResponse(detail())));
    renderIntl(<OnlineMeetingPanel meetingId={MID} />);
    await user.click(screen.getByRole("button", { name: "Online-Teilnahme anzeigen" }));
    await screen.findByRole("link", { name: "Videokonferenz öffnen" });
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ id: "v1", channel: "online", counted: false, conflict: true }, 201))
      .mockImplementation(() => Promise.resolve(jsonResponse(detail())));
    await user.click(screen.getByRole("button", { name: "Nein" }));
    expect(await screen.findByText(/wird aber nicht gezählt/)).toBeInTheDocument();
  });
});
