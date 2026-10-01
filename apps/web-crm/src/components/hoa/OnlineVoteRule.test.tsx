import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OnlineMeetingSwitch } from "./OnlineMeetingSwitch";
import { OnlineParticipation, type OnlineOverview } from "./OnlineParticipation";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const MEETING = "0192abcd-0000-7000-8000-000000000701";
const base: OnlineOverview = {
  enabled: true,
  note: "Hinweis AD06",
  has_conference_link: true,
  confirmations: [],
  proxies: [],
  speaker_requests: [],
  items: [{ id: "i1", position: 1, title: "Dachsanierung", voting_state: "open", online_votes: 2, open_conflicts: 1 }],
  proxy_conflict_mode: "flag",
  conflict_note: "Vollmacht gegen eigene Stimme: Regel des Betreibers, keine Rechtsauskunft.",
  vote_conflicts: [
    { id: "k1", agenda_item_id: "i1", contract_id: "c3", first_source: "proxy", first_choice: "yes", second_source: "own", second_choice: "no", mode: "flag", status: "open", resolution: null, decision_note: null },
    { id: "k2", agenda_item_id: "i1", contract_id: "c2", first_source: "own", first_choice: "yes", second_source: "proxy", second_choice: "no", mode: "flag", status: "resolved", resolution: "keep_first", decision_note: "Vollmacht lag vor" },
  ],
  admissibility: {
    applicable: true,
    complete: false,
    note: "Das System prüft die rechtliche Zulässigkeit nicht.",
    checks: [
      { key: "online_switch", state: "ok", state_label: "erfasst", label: "Schalter Online-Versammlung im Portal", detail: "eingeschaltet" },
      { key: "hybrid_basis", state: "open", state_label: "zu prüfen", label: "Hybride Form", detail: "Offen (AD06-01)." },
      { key: "conference_link", state: "missing", state_label: "nicht erfasst", label: "Konferenzlink", detail: "Nicht hinterlegt." },
    ],
  },
};
const units = { c1: "01", c2: "02", c3: "03" };

describe("AE31 Regel Vollmacht gegen eigene Stimme", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends the rule with the switch, default flag", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    renderIntl(<OnlineMeetingSwitch enabled={false} mode="flag" />);
    expect((screen.getByTestId("rule-flag") as HTMLInputElement).checked).toBe(true);
    expect(screen.getAllByRole("radio")).toHaveLength(4);
    await user.click(screen.getByTestId("rule-proxy_priority"));
    await user.click(screen.getByTestId("online-enabled"));
    await user.click(screen.getByRole("button", { name: "Schalter speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, { body: string; method: string }];
    expect(url).toBe("/api/bff/hoa/online-meeting-settings");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ enabled: true, proxy_conflict_mode: "proxy_priority" });
  });

  it("shows no rule choice and sends only the switch for an older API", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    renderIntl(<OnlineMeetingSwitch enabled={false} />);
    expect(screen.queryByTestId("proxy-conflict-rule")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Schalter speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse((fetchMock.mock.calls[0] as [string, { body: string }])[1].body)).toEqual({ enabled: false });
  });

  it("lists the checklist of recorded facts without a legal statement", () => {
    renderIntl(<OnlineParticipation meetingId={MEETING} data={base} units={units} />);
    const checks = screen.getAllByTestId("admissibility-check");
    expect(checks).toHaveLength(3);
    expect(checks[1]).toHaveTextContent("zu prüfen");
    expect(checks[1]).toHaveTextContent("Hybride Form");
    expect(checks[2]).toHaveTextContent("nicht erfasst");
    expect(screen.getByTestId("admissibility")).toHaveTextContent("Das System prüft die rechtliche Zulässigkeit nicht.");
    expect(screen.getByText(/Es gibt offene Prüfpunkte/)).toBeInTheDocument();
    expect(screen.getByTestId("proxy-conflict-mode")).toHaveTextContent("Konflikt als Prüfhinweis markieren");
    expect(screen.getByText("Offene Stimmkonflikte: 1")).toBeInTheDocument();
  });

  it("decides an open conflict and shows the decision of a resolved one", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    renderIntl(<OnlineParticipation meetingId={MEETING} data={base} units={units} />);
    const rows = screen.getAllByTestId("vote-conflict");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Einheit 03");
    expect(rows[0]).toHaveTextContent("zuerst Bevollmächtigter: Ja · danach Eigentümer: Nein");
    expect(rows[1]).toHaveTextContent("erste Stimme bestätigt");
    expect(rows[1]).toHaveTextContent("Vollmacht lag vor");
    await user.type(screen.getByTestId("conflict-note"), "Vollmacht geprüft");
    await user.click(screen.getByRole("button", { name: "Zweite Stimme zählen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, { body: string }];
    expect(url).toBe(`/api/bff/hoa/meetings/${MEETING}/vote-conflicts/k1/resolve`);
    expect(JSON.parse(init.body)).toEqual({ decision: "apply_second", note: "Vollmacht geprüft" });
    expect(refresh).toHaveBeenCalled();
  });
});
