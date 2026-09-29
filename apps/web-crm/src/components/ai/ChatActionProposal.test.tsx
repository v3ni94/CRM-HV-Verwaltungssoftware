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

describe("ChatActionProposal calendar and deadline entries", () => {
  const entry = {
    ...proposal,
    id: "01920000-0000-7000-8000-00000000b003",
    proposed: {
      kind: "calendar_create",
      title: "Übergabe Musterweg 1",
      date: "2026-10-05",
      time: "10:00",
      appointment_kind: "uebergabe",
      participants: [{ contact_id: "01920000-0000-7000-8000-00000000c0de", label: "Kowalski, Jan" }],
      property_label: "893 Lindenhof",
      reminders: [],
      reason: "Nutzer bittet um den Termin",
    },
  } as unknown as Proposal;

  it("shows date, time, participants and that nobody is invited", () => {
    renderIntl(<ChatActionProposal proposal={entry} />);
    expect(screen.getByText("Vorschlag: Termin im CRM-Kalender")).toBeInTheDocument();
    expect(screen.getByText("Titel: Übergabe Musterweg 1")).toBeInTheDocument();
    expect(screen.getByText("Datum: 05.10.2026")).toBeInTheDocument();
    expect(screen.getByText("Uhrzeit: 10:00")).toBeInTheDocument();
    expect(screen.getByText("Beteiligte (werden nicht eingeladen): Kowalski, Jan")).toBeInTheDocument();
    expect(screen.getByText("Objekt: 893 Lindenhof")).toBeInTheDocument();
    expect(screen.getByText(/keine Einladungen versendet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bestätigen und übernehmen" })).toBeInTheDocument();
  });

  it("shows a deadline entry as all day with its reminders", () => {
    const deadline = { ...entry, proposed: { kind: "deadline_create", title: "Frist Widerspruch", date: "2026-11-02", time: null, reminders: ["1d", "7d"] } } as unknown as Proposal;
    renderIntl(<ChatActionProposal proposal={deadline} />);
    expect(screen.getByText("Vorschlag: Fristeintrag mit Erinnerung")).toBeInTheDocument();
    expect(screen.getByText("Datum: 02.11.2026")).toBeInTheDocument();
    expect(screen.getByText("ganztägig")).toBeInTheDocument();
    expect(screen.getByText("Erinnerungen: 1d, 7d")).toBeInTheDocument();
  });
});
