import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { HandoverSummary } from "./HandoverSummary";
import type { Full } from "./types";

vi.mock("next/navigation", () => ({
  usePathname: () => "/makler/uebergabe/1",
  useSearchParams: () => new URLSearchParams(),
}));

const ID = "0192abcd-0000-7000-8000-000000000060";

export function fixture(overrides: Partial<Full> = {}): Full {
  return {
    id: ID,
    number: "UP-20260925-001",
    version: 2,
    parent_id: null,
    change_reason: "Nachtrag",
    kind: "rental",
    status: "completed",
    current_step: "summary",
    property_id: null,
    unit_id: null,
    street: "Musterweg",
    house_number: "12",
    postal_code: "40789",
    city: "Monheim am Rhein",
    object_label: null,
    building: null,
    floor: "2",
    unit_number: "03",
    unit_label: "links",
    unit_position: null,
    handover_date: "2026-09-25",
    handover_start: "10:00:00",
    handover_end: null,
    hide_time_information: false,
    handover_location: "Vor Ort",
    ticket_number: null,
    reference_number: null,
    management_number: null,
    rental_contract_number: null,
    internal_contact: null,
    internal_note: null,
    general_note: null,
    deposit_amount: null,
    deposit_account_holder: null,
    deposit_iban: null,
    deposit_bic: null,
    deposit_bank_name: null,
    deposit_note: null,
    deposit_iban_verified: false,
    deposit_separate_statement: false,
    completed_at: "2026-09-25T10:30:00Z",
    archived_at: null,
    pdf_document_id: "0192abcd-0000-7000-8000-000000000099",
    locked: true,
    finalized: true,
    address: "Musterweg 12, 40789 Monheim am Rhein",
    participants: [
      { id: "p1", role: "moving_out", role_label: "Ausziehender Mieter", first_name: "Anna", last_name: "Alt", phone: "0211 123 456", email: "anna@example.org" },
      { id: "p2", role: "moving_in", role_label: "Einziehender Mieter", company: "Neu GmbH", phone: null, email: null },
    ],
    meters: [{ id: "m1", meter_type: "electricity", number: "E-1", value: "12345.600", unit: "kWh", read_on: "2026-09-25" }],
    rooms: [
      { id: "r1", name: "Küche", condition: "defective" },
      { id: "r2", name: "Bad", condition: "ok" },
    ],
    defects: [
      { id: "d1", room_id: "r1", title: "Kratzer", priority: "low", defect_status: "new" },
      { id: "d2", room_id: "r2", title: "Fuge", priority: "high", defect_status: "pre_existing" },
      { id: "d3", room_id: null, title: "Haustür klemmt", priority: "medium", defect_status: "unclear" },
    ],
    keys: [{ id: "k1", key_type: "Haustürschlüssel", quantity: 2, status: "handed_over" }],
    items: [],
    notes: [
      { id: "n1", category: "hint", text: "Nur intern", is_internal: true },
      { id: "n2", category: "agreement", text: "Rückzahlung Kaution bis 31.10.", is_internal: false, due_date: "2026-10-31" },
    ],
    signatures: [
      { id: "s1", participant_id: "p1", signer_name: "Anna Alt", signer_role: "moving_out", sha256: "x", signed_at: "2026-09-25T10:15:00Z", signed_location: "Monheim", document_id: "0192abcd-0000-7000-8000-000000000077" },
    ],
    documents: [
      { id: "0192abcd-0000-7000-8000-000000000001", title: "Kratzer", filename: "k.jpg", mime_type: "image/jpeg", size: 10, kind: "photo", section: "defect", item_id: "d1", created_at: "2026-09-25T10:00:00Z", thumbnail_url: `/api/v1/handover/protocols/${ID}/documents/0192abcd-0000-7000-8000-000000000001/thumbnail` },
      { id: "0192abcd-0000-7000-8000-000000000002", title: "Anlage", filename: "anlage.pdf", mime_type: "application/pdf", size: 10, kind: "attachment", section: null, item_id: null, created_at: "2026-09-25T10:00:00Z", thumbnail_url: null },
    ],
    hints: [],
    hint_codes: [],
    content_locked: false,
    changes: [],
    versions: [],
    ...overrides,
  };
}

describe("HandoverSummary", () => {
  it("renders the stored data with German formats, contact links, grouped defects and the PDF link in the same tab", () => {
    const { container } = renderIntl(<HandoverSummary p={fixture()} mode="locked" />);
    expect(screen.getByText("25.09.2026")).toBeInTheDocument();
    expect(screen.getByText("12.345,6 kWh")).toBeInTheDocument();
    expect(screen.getByText("0211 123 456").closest("a")).toHaveAttribute("href", "tel:0211123456");
    expect(screen.getByText("anna@example.org").closest("a")).toHaveAttribute("href", "mailto:anna@example.org");
    const rooms = screen.getAllByTestId("summary-room");
    expect(rooms).toHaveLength(2);
    expect(within(rooms[0]!).getByText("Kratzer")).toBeInTheDocument();
    expect(within(rooms[1]!).getByText("Fuge")).toBeInTheDocument();
    expect(within(screen.getByTestId("summary-unassigned")).getByText("Haustür klemmt")).toBeInTheDocument();
    expect(screen.getByText("Intern")).toBeInTheDocument();
    const signature = container.querySelector('img[src*="000000000077"]');
    expect(signature?.className).toContain("bg-paper");
    expect(screen.getByText(/unterschrieben am 25\.09\.2026/)).toBeInTheDocument();
    const pdf = screen.getByTestId("summary-pdf");
    expect(pdf).toHaveAttribute("href", `/api/handover-files/handover/protocols/${ID}/pdf`);
    expect(pdf).not.toHaveAttribute("target");
    expect(screen.getByText("anlage.pdf").closest("a")).toHaveAttribute("download", "anlage.pdf");
    expect(container.textContent).not.toMatch(/\b(zugestellt|rechtsgültig|gelesen)\b/i);
    expect(container.querySelectorAll("input, textarea")).toHaveLength(0);
    expect(screen.queryByText("Bearbeiten")).not.toBeInTheDocument();
  });

  it("offers edit buttons and hint links only in overview mode", async () => {
    const onGoTo = vi.fn();
    renderIntl(<HandoverSummary p={fixture({ hints: ["Es wurden keine Schlüssel erfasst."], hint_codes: ["no_keys"], keys: [] })} mode="overview" onGoTo={onGoTo} />);
    await userEvent.click(screen.getByTestId("summary-edit-rooms"));
    expect(onGoTo).toHaveBeenCalledWith("rooms");
    const hints = screen.getByTestId("hints");
    await userEvent.click(within(hints).getByText("Bearbeiten"));
    expect(onGoTo).toHaveBeenCalledWith("keys");
  });

  it("shows the change history and marks an invalidated signature", () => {
    renderIntl(
      <HandoverSummary
        p={fixture({
          changes: [{ id: "c1", reason: "Zählernummer falsch", changed_at: "2026-09-25T11:00:00Z", changed_by: "u1", changed_by_name: "Timo Müller", signatures_invalidated: 1 }],
          signatures: [{ id: "s1", participant_id: "p1", signer_name: "Anna Alt", signer_role: "moving_out", sha256: "x", signed_at: "2026-09-25T10:15:00Z", signed_location: null, document_id: "0192abcd-0000-7000-8000-000000000077", invalidated_at: "2026-09-25T11:00:00Z", invalidated_change_id: "c1" }],
        })}
        mode="locked"
      />,
    );
    expect(screen.getByTestId("summary-changes")).toHaveTextContent("Timo Müller: Zählernummer falsch");
    expect(screen.getByText(/gilt nicht mehr/)).toBeInTheDocument();
  });
});
