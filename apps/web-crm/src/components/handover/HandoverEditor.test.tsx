import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HandoverEditor, parseDecimal } from "./HandoverEditor";
import type { Full } from "./types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const ID = "0192abcd-0000-7000-8000-000000000060";

function protocol(overrides: Partial<Full> = {}): Full {
  return {
    id: ID,
    number: "UP-20260925-001",
    version: 1,
    parent_id: null,
    change_reason: null,
    kind: "rental",
    status: "in_progress",
    current_step: "rooms",
    property_id: null,
    unit_id: null,
    street: "Musterweg",
    house_number: "12",
    postal_code: "40789",
    city: "Monheim am Rhein",
    object_label: null,
    building: null,
    floor: null,
    unit_number: "03",
    unit_label: null,
    unit_position: null,
    handover_date: "2026-09-25",
    handover_start: null,
    handover_end: null,
    hide_time_information: false,
    handover_location: null,
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
    completed_at: null,
    archived_at: null,
    pdf_document_id: null,
    locked: false,
    finalized: false,
    address: "Musterweg 12, 40789 Monheim am Rhein",
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
    versions: [
      {
        id: ID,
        version: 1,
        status: "in_progress",
        completed_at: null,
        change_reason: null,
      },
    ],
    ...overrides,
  };
}

describe("HandoverEditor", () => {
  afterEach(() => vi.restoreAllMocks());

  it("adds a room through the section form and reloads the protocol", async () => {
    const calls: { url: string; method: string; body: string | null }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({
        url,
        method,
        body: typeof init?.body === "string" ? init.body : null,
      });
      if (method === "POST" && url.endsWith("/rooms")) {
        return jsonResponse(
          {
            id: "0192abcd-0000-7000-8000-000000000061",
            name: "Küche",
            condition: "ok",
          },
          201,
        );
      }
      if (method === "GET") {
        return jsonResponse(
          protocol({
            rooms: [
              {
                id: "0192abcd-0000-7000-8000-000000000061",
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
    renderIntl(<HandoverEditor initial={protocol()} />);
    expect(screen.getByText("Keine Einträge.")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Raum hinzufügen"));
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Küche");
    await userEvent.selectOptions(screen.getByLabelText("Zustand"), "ok");
    await userEvent.click(screen.getByText("Speichern"));
    await waitFor(() => expect(screen.getByText("Küche")).toBeInTheDocument());
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe(`/api/bff/handover/protocols/${ID}/rooms`);
    expect(JSON.parse(post?.body ?? "{}")).toMatchObject({
      name: "Küche",
      condition: "ok",
    });
  });

  it("shows the hints before completing and offers the forced completion", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({}, 200),
    );
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderIntl(
      <HandoverEditor initial={protocol({ current_step: "summary" })} />,
    );
    await userEvent.click(
      screen.getByText("Protokoll verbindlich abschließen"),
    );
    expect(screen.getByTestId("hints")).toHaveTextContent(
      "Es wurden keine Räume erfasst.",
    );
    expect(
      screen.getByText("Trotz Hinweisen verbindlich abschließen"),
    ).toBeInTheDocument();
    expect(window.confirm).not.toHaveBeenCalled();
  });

  it("hides every write action once the protocol is locked", () => {
    renderIntl(
      <HandoverEditor
        initial={protocol({
          status: "completed",
          locked: true,
          finalized: true,
          completed_at: "2026-09-25T10:00:00Z",
          current_step: "summary",
        })}
      />,
    );
    expect(screen.getByText(/schreibgeschützt/)).toBeInTheDocument();
    expect(
      screen.queryByText("Protokoll verbindlich abschließen"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Neue Version anlegen")).toBeInTheDocument();
    expect(screen.getByText("Zustellung vorbereiten")).toBeInTheDocument();
  });
});

describe("parseDecimal", () => {
  it("accepts German input and the API format without changing the value", () => {
    expect(parseDecimal("1.500,50")).toBe("1500.50");
    expect(parseDecimal("1500,5")).toBe("1500.5");
    expect(parseDecimal("1500.00")).toBe("1500.00");
    expect(parseDecimal("12345.678")).toBe("12345.678");
    expect(parseDecimal("1.234.567")).toBe("1234567");
  });
});

describe("HandoverEditor deposit round trip", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves an unchanged deposit amount with the same value", async () => {
    const bodies: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (init?.method === "PATCH" && typeof init.body === "string")
        bodies.push(init.body);
      return jsonResponse(protocol({ deposit_amount: "1500.00" }));
    });
    renderIntl(
      <HandoverEditor
        initial={protocol({
          current_step: "deposit",
          deposit_amount: "1500.00",
        })}
      />,
    );
    expect(screen.getByLabelText("Kautionsbetrag (EUR)")).toHaveValue(
      "1500,00",
    );
    await userEvent.click(screen.getByText("Speichern"));
    await waitFor(() => expect(bodies.length).toBeGreaterThan(0));
    expect(JSON.parse(bodies[0]!)).toMatchObject({ deposit_amount: "1500.00" });
  });
});
