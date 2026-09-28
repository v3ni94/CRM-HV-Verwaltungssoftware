import { screen } from "@testing-library/react";

import type { Proposal } from "@/lib/ai";
import { renderIntl } from "@/test/intl";

import { ChatActionProposal } from "./ChatActionProposal";

const proposal = {
  id: "01920000-0000-7000-8000-00000000b002",
  task_run_id: "01920000-0000-7000-8000-00000000a002",
  entity_type: "chat_action",
  context_id: null,
  decision: "pending",
  decided_by: null,
  decided_at: null,
  import_run_id: null,
  proposed: {
    kind: "contact_change",
    contact_id: "01920000-0000-7000-8000-00000000c0de",
    contact_label: "Kowalski, Jan",
    changes: [{ field: "street", old: "Alte Straße", new: "Musterweg" }],
    reason: "Nutzer nennt die neue Anschrift",
  },
} as unknown as Proposal;

describe("ChatActionProposal", () => {
  it("shows the model's reason with the change so the confirming user sees why", () => {
    renderIntl(<ChatActionProposal proposal={proposal} />);
    expect(screen.getByText("Vorschlag: Kontaktdaten ändern")).toBeInTheDocument();
    expect(screen.getByText("Kontakt: Kowalski, Jan")).toBeInTheDocument();
    expect(screen.getByText("Begründung der KI: Nutzer nennt die neue Anschrift")).toBeInTheDocument();
    expect(screen.getByText("Straße: Musterweg")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bestätigen und übernehmen" })).toBeInTheDocument();
  });
});
