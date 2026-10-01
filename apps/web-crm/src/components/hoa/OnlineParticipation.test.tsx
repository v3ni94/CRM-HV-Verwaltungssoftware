import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OnlineParticipation, type OnlineOverview } from "./OnlineParticipation";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const MEETING = "0192abcd-0000-7000-8000-000000000601";
const data: OnlineOverview = {
  enabled: true,
  note: "Hinweis AD06",
  has_conference_link: true,
  confirmations: [{ contract_id: "c1", confirmed_at: "2026-12-10T17:00:00Z" }],
  proxies: [
    { id: "p1", grantor_contract_id: "c3", proxy_kind: "owner", proxy_contract_id: "c1", valid_from: "2026-01-01", valid_to: "2027-12-31", document_id: "d1", revoked_at: null, active: true },
    { id: "p2", grantor_contract_id: "c2", proxy_kind: "manager", proxy_contract_id: null, valid_from: "2026-01-01", valid_to: null, document_id: "d2", revoked_at: "2026-12-01T09:00:00Z", active: false },
  ],
  speaker_requests: [{ id: "s1", contract_id: "c1", agenda_item_id: null, requested_at: "2026-12-10T17:05:00Z", note: "Frage", status: "open" }],
  items: [
    { id: "i1", position: 1, title: "Dachsanierung", voting_state: "not_opened", online_votes: 0 },
    { id: "i2", position: 2, title: "Hausordnung", voting_state: "open", online_votes: 2 },
  ],
};
const units = { c1: "01", c2: "02", c3: "03" };

describe("OnlineParticipation", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows confirmations, proxies and speaker requests with unit numbers (AD06)", () => {
    renderIntl(<OnlineParticipation meetingId={MEETING} data={data} units={units} />);
    expect(screen.getByText("Zusagen online (1)")).toBeInTheDocument();
    expect(screen.getAllByTestId("proxy")[0]).toHaveTextContent("Einheit 03 → Einheit 01 · 01.01.2026 bis 31.12.2027 · wirksam erfasst");
    expect(screen.getAllByTestId("proxy")[1]).toHaveTextContent("Einheit 02 → Verwaltung");
    expect(screen.getAllByTestId("proxy")[1]).toHaveTextContent("widerrufen am");
    expect(screen.getByTestId("speaker-request")).toHaveTextContent("Einheit 01 · Frage");
    expect(screen.getByText("2 Online-Stimmen")).toBeInTheDocument();
  });

  it("opens and closes the voting per item and handles a request to speak", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    renderIntl(<OnlineParticipation meetingId={MEETING} data={data} units={units} />);
    await user.click(screen.getByRole("button", { name: "Abstimmung öffnen" }));
    await user.click(screen.getByRole("button", { name: "Abstimmung schließen" }));
    await user.click(screen.getByRole("button", { name: "Erledigt" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual([
      `/api/bff/hoa/meetings/${MEETING}/agenda/i1/voting/open`,
      `/api/bff/hoa/meetings/${MEETING}/agenda/i2/voting/close`,
      `/api/bff/hoa/meetings/${MEETING}/speaker-requests/s1`,
    ]);
    expect(refresh).toHaveBeenCalled();
  });

  it("hides the voting buttons while the tenant switch is off", () => {
    renderIntl(<OnlineParticipation meetingId={MEETING} data={{ ...data, enabled: false }} units={units} />);
    expect(screen.getByText(/Schalter Online-Versammlung/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Abstimmung öffnen" })).not.toBeInTheDocument();
  });
});
