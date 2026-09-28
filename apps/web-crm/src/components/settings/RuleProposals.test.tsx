import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { RuleProposals, RuleProposalsBadge, type RuleProposal } from "./RuleProposals";

const ID = "01900000-0000-7000-8000-000000000001";
const ID2 = "01900000-0000-7000-8000-000000000002";

function proposal(over: Partial<RuleProposal> = {}): RuleProposal {
  return {
    id: ID,
    entity_type: "message",
    field: "property",
    scope: "address",
    sender_key: "hans@hauswart.example",
    value: "01900000-0000-7000-8000-00000000000a",
    value_label: "871 Lernhaus",
    status: "proposed",
    evidence_count: 5,
    threshold: 5,
    evidence: {
      decision_ids: ["a", "b", "c", "d", "e"],
      addresses: ["hans@hauswart.example"],
      first_at: "2026-09-20T08:00:00Z",
      last_at: "2026-09-27T08:00:00Z",
    },
    rule_id: null,
    ...over,
  };
}

describe("RuleProposals", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists a proposal with its evidence and accepts it", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith(`/rule-proposals/${ID}/accept`) && init?.method === "POST")
        return jsonResponse(proposal({ status: "accepted", rule_id: ID2 }));
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<RuleProposals initial={[proposal()]} canManage />);
    expect(screen.getByText("Mail: Objekt 871 Lernhaus")).toBeInTheDocument();
    expect(screen.getByText("Absender hans@hauswart.example")).toBeInTheDocument();
    expect(
      screen.getByText(
        "5 gleiche manuelle Entscheidungen ohne Widerspruch (Schwelle 5), vom 20.09.2026 bis 27.09.2026",
      ),
    ).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Annehmen und Regel aktivieren" }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Regel angelegt und aktiv."));
    expect(screen.getByRole("link", { name: "Zur Automatisierung" })).toHaveAttribute(
      "href",
      "/einstellungen/automatisierung",
    );
    expect(screen.queryByTestId("rule-proposal")).not.toBeInTheDocument();
    expect(screen.getByText("Derzeit gibt es keine offenen Regelvorschläge.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/bff/automation/rule-proposals/${ID}/accept`,
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("rejects with a reason and shows a conflict as an alert", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith(`/rule-proposals/${ID}/reject`) && init?.method === "POST")
        return jsonResponse(proposal({ status: "rejected" }));
      if (url.endsWith(`/rule-proposals/${ID2}/accept`))
        return jsonResponse(
          { title: "Regelvorschlag nicht mehr belegt", detail: "Grundlage geändert.", status: 409, code: "MHVP-AUTO-0002" },
          409,
        );
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    const domain = proposal({
      id: ID2,
      entity_type: "ticket",
      field: "topic",
      scope: "domain",
      sender_key: "lernfirma.example",
      value: "vertrag",
      value_label: "Vertrag",
      evidence: { decision_ids: ["a"], addresses: ["anna@lernfirma.example", "bernd@lernfirma.example"] },
    });
    renderIntl(<RuleProposals initial={[proposal(), domain]} canManage />);
    const user = userEvent.setup();
    expect(screen.getByText("Ticket: Thema Vertrag")).toBeInTheDocument();
    expect(screen.getByText("Absenderdomain lernfirma.example")).toBeInTheDocument();
    expect(
      screen.getByText("Absenderadressen: anna@lernfirma.example, bernd@lernfirma.example"),
    ).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Annehmen und Regel aktivieren" })[1]!);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getAllByTestId("rule-proposal")).toHaveLength(2);

    await user.click(screen.getAllByRole("button", { name: "Ablehnen" })[0]!);
    await user.type(screen.getByLabelText("Grund der Ablehnung (optional)"), "wechselt oft");
    await user.click(screen.getByRole("button", { name: "Ablehnung bestätigen" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Vorschlag abgelehnt."));
    expect(screen.getAllByTestId("rule-proposal")).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/bff/automation/rule-proposals/${ID}/reject`,
      expect.objectContaining({ method: "POST", body: JSON.stringify({ reason: "wechselt oft" }) }),
    );
  });

  it("validates and saves the threshold, read only without the right", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/api/bff/tenant/settings") && init?.method === "PATCH")
        return jsonResponse({ rule_proposal_threshold: 7 });
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    const { unmount } = renderIntl(<RuleProposals initial={[]} canManage initialThreshold={5} />);
    const user = userEvent.setup();
    const input = screen.getByTestId("rule-proposal-threshold");
    expect(input).toHaveValue(5);
    await user.clear(input);
    await user.type(input, "1");
    await user.click(screen.getByRole("button", { name: "Schwelle speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("zwischen 2 und 50");
    expect(fetchMock).not.toHaveBeenCalled();
    await user.clear(input);
    await user.type(input, "7");
    await user.click(screen.getByRole("button", { name: "Schwelle speichern" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Schwelle gespeichert."));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/tenant/settings",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ rule_proposal_threshold: 7 }) }),
    );
    unmount();

    renderIntl(<RuleProposals initial={[proposal()]} canManage={false} />);
    expect(screen.queryByRole("button", { name: "Annehmen und Regel aktivieren" })).not.toBeInTheDocument();
    expect(screen.getByText(/erfordern das Recht Mandanteneinstellungen ändern/)).toBeInTheDocument();
  });

  it("shows the hint badge only with open proposals", () => {
    const { unmount } = renderIntl(<RuleProposalsBadge count={0} />);
    expect(screen.queryByTestId("rule-proposals-badge")).not.toBeInTheDocument();
    unmount();
    renderIntl(<RuleProposalsBadge count={3} />);
    const badge = screen.getByTestId("rule-proposals-badge");
    expect(badge).toHaveAttribute("href", "/einstellungen/regelvorschlaege");
    expect(badge).toHaveTextContent("Regelvorschläge 3");
    expect(badge).toHaveAttribute("title", "3 offene Regelvorschläge");
  });
});
