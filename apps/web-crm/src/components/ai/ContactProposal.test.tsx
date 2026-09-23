import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Proposal } from "@/lib/ai";
import { jsonResponse, renderIntl } from "@/test/intl";

import { ContactProposal } from "./ContactProposal";

const ID = "01920000-0000-7000-8000-0000000000p1";
const EXISTING = "01920000-0000-7000-8000-0000000000c1";

const proposal: Proposal = {
  id: ID,
  task_run_id: "01920000-0000-7000-8000-0000000000r1",
  entity_type: "contacts",
  context_id: null,
  decision: "pending",
  decided_by: null,
  decided_at: null,
  import_run_id: null,
  proposed: {
    questions: ["Ist Zeile 4 ein Mieter oder ein Eigentümer?"],
    rows: [
      { index: 0, status: "new", contact: { first_name: "Anna", last_name: "Neu" }, role: "owner", unit_number: "1", co_members: [], confidence: 0.9, source_row: 2, duplicates: [], notes: [] },
      {
        index: 1,
        status: "existing",
        contact: { first_name: "Erika", last_name: "Mustermann" },
        role: "tenant",
        unit_number: null,
        co_members: [],
        confidence: 0.8,
        source_row: 3,
        duplicates: [{ contact_id: EXISTING, name: "Erika Mustermann", score: 0.95, reasons: ["gleiche E-Mail-Adresse"] }],
        notes: [],
      },
      { index: 2, status: "incomplete", contact: { last_name: "Ohneadresse" }, role: null, unit_number: null, co_members: [], confidence: 0.5, source_row: 4, duplicates: [], notes: ["Anschrift fehlt."] },
      { index: 3, status: "invalid", contact: null, role: null, unit_number: null, co_members: [], confidence: 0.2, source_row: 5, duplicates: [], notes: ["Kontakt nicht übernehmbar: Name fehlt"] },
    ],
  },
};

describe("ContactProposal", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows questions on top, a status per row, duplicate score and notes", () => {
    renderIntl(<ContactProposal proposal={proposal} />);
    expect(screen.getByText("Offene Rückfragen")).toBeInTheDocument();
    expect(screen.getByText("Ist Zeile 4 ein Mieter oder ein Eigentümer?")).toBeInTheDocument();
    expect(within(screen.getByTestId("contact-row-0")).getByText("neu")).toBeInTheDocument();
    const existing = screen.getByTestId("contact-row-1");
    expect(within(existing).getByText("vorhanden")).toBeInTheDocument();
    expect(within(existing).getByText(/Erika Mustermann \(95 %\)/)).toBeInTheDocument();
    expect(within(screen.getByTestId("contact-row-2")).getByText("Anschrift fehlt.")).toBeInTheDocument();
    expect(within(screen.getByTestId("contact-row-3")).getByText("ungültig")).toBeInTheDocument();
  });

  it("defaults actions by status and blocks invalid rows from being created", () => {
    renderIntl(<ContactProposal proposal={proposal} />);
    expect(screen.getByLabelText("Aktion für Anna Neu")).toHaveValue("create");
    expect(screen.getByLabelText("Aktion für Erika Mustermann")).toHaveValue("link");
    const invalid = screen.getByLabelText("Aktion für ohne Namen") as HTMLSelectElement;
    expect(invalid).toHaveValue("skip");
    expect(within(invalid).getByRole("option", { name: "anlegen" })).toBeDisabled();
    expect(within(screen.getByLabelText("Aktion für Anna Neu")).getByRole("option", { name: "mit vorhandenem verknüpfen" })).toBeDisabled();
  });

  it("sends the chosen actions and shows the import result with undo", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ id: "01920000-0000-7000-8000-0000000000i1", source: "ai:extract_contacts", status: "applied", summary: {}, created_at: "2026-09-23T08:00:00Z", undone_at: null, items: [] }, 201),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<ContactProposal proposal={proposal} />);
    await userEvent.selectOptions(screen.getByLabelText("Aktion für Ohneadresse"), "skip");
    await userEvent.click(screen.getByRole("button", { name: "Bestätigen und übernehmen" }));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe(`/api/bff/ai/proposals/${ID}/apply`);
    expect(JSON.parse(init.body as string)).toEqual({
      contacts: [
        { index: 0, action: "create" },
        { index: 1, action: "link", contact_id: EXISTING },
        { index: 2, action: "skip" },
        { index: 3, action: "skip" },
      ],
    });
    expect(await screen.findByText("Ergebnis des Imports")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rückgängig" })).toBeInTheDocument();
  });
});
