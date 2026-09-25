import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HandoverFill, parseDecimal } from "./HandoverFill";
import type { Full } from "./types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const ID = "0192abcd-0000-7000-8000-000000000070";

function protocol(overrides: Partial<Full> = {}): Full {
  return {
    id: ID,
    number: "UP-20260925-003",
    version: 1,
    parent_id: null,
    change_reason: null,
    kind: "rental",
    status: "in_progress",
    current_step: "rooms",
    property_id: null,
    unit_id: null,
    street: "Portalweg",
    house_number: "1",
    postal_code: "40789",
    city: "Monheim am Rhein",
    object_label: null,
    building: null,
    floor: null,
    unit_number: null,
    unit_label: null,
    unit_position: null,
    handover_date: null,
    handover_start: null,
    handover_end: null,
    hide_time_information: false,
    handover_location: null,
    ticket_number: null,
    reference_number: null,
    rental_contract_number: null,
    general_note: null,
    deposit_amount: null,
    deposit_account_holder: null,
    deposit_iban: null,
    deposit_bic: null,
    deposit_bank_name: null,
    deposit_note: null,
    deposit_iban_verified: false,
    deposit_separate_statement: false,
    completed_at: null,
    archived_at: null,
    pdf_document_id: null,
    locked: false,
    finalized: false,
    address: "Portalweg 1, 40789 Monheim am Rhein",
    participants: [],
    meters: [],
    rooms: [],
    defects: [],
    keys: [],
    items: [],
    notes: [],
    signatures: [],
    documents: [],
    hints: ["Es wurden keine Räume erfasst."],
    access: { right: "edit", valid_to: null },
    ...overrides,
  };
}

describe("HandoverFill", () => {
  afterEach(() => vi.restoreAllMocks());

  it("adds a room through the portal BFF and reloads", async () => {
    const calls: { url: string; method: string; body: string | null }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? init.body : null });
      if (method === "POST" && url.endsWith("/rooms")) {
        return jsonResponse({ id: "0192abcd-0000-7000-8000-000000000071", name: "Küche" }, 201);
      }
      if (method === "GET") {
        return jsonResponse(
          protocol({
            rooms: [
              {
                id: "0192abcd-0000-7000-8000-000000000071",
                name: "Küche",
                room_type: null,
                condition: "ok",
                comment: null,
                sort_order: 0,
              },
            ],
            hints: [],
          }),
        );
      }
      return jsonResponse({}, 200);
    });
    renderIntl(<HandoverFill initial={protocol()} />);
    expect(screen.getByText("Keine Einträge.")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Raum hinzufügen"));
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Küche");
    await userEvent.click(screen.getByText("Speichern"));
    await waitFor(() => expect(screen.getByText("Küche")).toBeInTheDocument());
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe(`/api/bff/portal/handover/${ID}/rooms`);
    expect(JSON.parse(post?.body ?? "{}")).toMatchObject({ name: "Küche" });
  });

  it("offers no internal fields and no internal flag on remarks", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}, 200));
    renderIntl(<HandoverFill initial={protocol({ current_step: "notes" })} />);
    await userEvent.click(screen.getByText("Bemerkung hinzufügen"));
    expect(screen.queryByLabelText(/intern/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("Objekt"));
    expect(screen.queryByLabelText("Verwaltungsnummer")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Straße")).toHaveValue("Portalweg");
  });

  it("shows the hints before completing and offers the forced completion", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}, 200));
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderIntl(<HandoverFill initial={protocol({ current_step: "summary" })} />);
    await userEvent.click(screen.getByText("Protokoll verbindlich abschließen"));
    expect(screen.getByTestId("hints")).toHaveTextContent("Es wurden keine Räume erfasst.");
    expect(screen.getByText("Trotz Hinweisen verbindlich abschließen")).toBeInTheDocument();
    expect(window.confirm).not.toHaveBeenCalled();
  });

  it("is read only once the access is read or the protocol is locked", () => {
    renderIntl(
      <HandoverFill
        initial={protocol({
          status: "completed",
          locked: true,
          finalized: true,
          current_step: "summary",
          access: { right: "read", valid_to: "2026-10-09" },
        })}
      />,
    );
    expect(screen.getByText(/kann nicht mehr geändert werden/)).toBeInTheDocument();
    expect(screen.queryByText("Protokoll verbindlich abschließen")).not.toBeInTheDocument();
    expect(screen.getByText("Protokoll als PDF")).toHaveAttribute(
      "href",
      `/api/portal-files/portal/handover/${ID}/pdf`,
    );
    expect(screen.getByText(/abrufbar bis 09.10.2026/)).toBeInTheDocument();
  });
});

describe("parseDecimal", () => {
  it("accepts German input and the API format without changing the value", () => {
    expect(parseDecimal("1.500,50")).toBe("1500.50");
    expect(parseDecimal("1500.00")).toBe("1500.00");
  });
});
