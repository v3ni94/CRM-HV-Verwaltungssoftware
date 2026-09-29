import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HandoverEditor, parseDecimal } from "./HandoverEditor";
import type { Full } from "./types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/makler/uebergabe/1",
  useSearchParams: () => new URLSearchParams(),
}));

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});

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
    hint_codes: ["no_rooms"],
    content_locked: false,
    changes: [],
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
            hint_codes: [],
          }),
        );
      }
      return jsonResponse({}, 200);
    });
    renderIntl(<HandoverEditor initial={protocol()} />);
    expect(screen.getByText("Keine Einträge.")).toBeInTheDocument();
    // Step chip: attention dot from the hint code, no counter yet.
    const roomsChip = screen.getByTestId("step-rooms");
    expect(roomsChip).toHaveAttribute("aria-current", "step");
    expect(roomsChip.className).toContain("min-h-11");
    expect(within(roomsChip).getByTestId("step-state")).toHaveAttribute("data-state", "attention");
    await userEvent.click(screen.getByText("Raum hinzufügen"));
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Küche");
    await userEvent.selectOptions(screen.getByLabelText("Zustand"), "ok");
    const save = screen.getByText("Speichern");
    expect(save.closest("div")?.className).toContain("sticky");
    await userEvent.click(save);
    await waitFor(() => expect(screen.getByText("Küche")).toBeInTheDocument());
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe(`/api/bff/handover/protocols/${ID}/rooms`);
    expect(JSON.parse(post?.body ?? "{}")).toMatchObject({
      name: "Küche",
      condition: "ok",
    });
    await waitFor(() => expect(within(screen.getByTestId("step-rooms")).getByTestId("step-state")).toHaveAttribute("data-state", "filled"));
    expect(screen.getByTestId("step-rooms")).toHaveTextContent("Räume1");
  });

  it("moves to the next step with the footer and remembers current_step", async () => {
    const calls: { url: string; method: string; body: string | null }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push({ url: String(input), method: init?.method ?? "GET", body: typeof init?.body === "string" ? init.body : null });
      return jsonResponse({}, 200);
    });
    renderIntl(<HandoverEditor initial={protocol({ current_step: "object" })} />);
    expect(screen.getByTestId("step-object")).toHaveAttribute("aria-current", "step");
    await userEvent.click(screen.getByText("Weiter"));
    expect(screen.getByTestId("step-participants")).toHaveAttribute("aria-current", "step");
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH" && c.body === JSON.stringify({ current_step: "participants" }))).toBe(true));
    await userEvent.click(screen.getByTestId("step-defects"));
    await waitFor(() => expect(calls.some((c) => c.body === JSON.stringify({ current_step: "defects" }))).toBe(true));
    expect(screen.getByText("Mangel hinzufügen")).toBeInTheDocument();
  });

  it("uses the keyboard hints per field", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(protocol({ current_step: "participants" }), 200));
    renderIntl(<HandoverEditor initial={protocol({ current_step: "participants" })} />);
    await userEvent.click(screen.getByText("Beteiligten hinzufügen"));
    expect(screen.getByLabelText("E-Mail")).toHaveAttribute("type", "email");
    expect(screen.getByLabelText("Telefon")).toHaveAttribute("type", "tel");
    expect(screen.getByLabelText("PLZ")).toHaveAttribute("inputmode", "numeric");
    expect(screen.getByLabelText("Vorname")).toHaveAttribute("enterkeyhint", "next");
    await userEvent.click(screen.getByText("Abbrechen"));
    await userEvent.click(screen.getByTestId("step-deposit"));
    expect(screen.getByLabelText("IBAN")).toHaveAttribute("autocapitalize", "characters");
    expect(screen.getByLabelText("Kautionsbetrag (EUR)")).toHaveAttribute("inputmode", "decimal");
  });

  it("keeps the value and offers Erneut senden after a failed save, and warns while offline", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "PATCH") throw new TypeError("network");
      return jsonResponse({}, 200);
    });
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    renderIntl(<HandoverEditor initial={protocol({ current_step: "object" })} />);
    expect(screen.getByTestId("offline-notice")).toHaveTextContent("Keine Verbindung");
    await userEvent.type(screen.getByLabelText("Ort der Übergabe"), "Vor Ort");
    await userEvent.click(screen.getByText("Speichern"));
    expect(await screen.findByText("Erneut senden")).toBeInTheDocument();
    expect(screen.getByLabelText("Ort der Übergabe")).toHaveValue("Vor Ort");
    expect(screen.getByRole("alert")).toBeInTheDocument();
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
  });

  it("asks before leaving a step with unsaved input", async () => {
    const calls: { method: string; body: string | null }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      calls.push({ method: init?.method ?? "GET", body: typeof init?.body === "string" ? init.body : null });
      return jsonResponse({}, 200);
    });
    renderIntl(<HandoverEditor initial={protocol({ current_step: "object" })} />);
    await userEvent.type(screen.getByLabelText("Ort der Übergabe"), "x");
    await userEvent.click(screen.getByTestId("step-keys"));
    expect(screen.getByText(/Es gibt ungespeicherte Eingaben/)).toBeInTheDocument();
    await userEvent.click(screen.getByText("Hier bleiben"));
    expect(screen.getByTestId("step-object")).toHaveAttribute("aria-current", "step");
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
    await userEvent.click(screen.getByTestId("step-keys"));
    await userEvent.click(screen.getByText("Verwerfen"));
    expect(screen.getByTestId("step-keys")).toHaveAttribute("aria-current", "step");
    await waitFor(() => expect(calls.some((c) => c.body === JSON.stringify({ current_step: "keys" }))).toBe(true));
  });

  it("uploads the photos of a new defect after the POST, marks a failed file and retries only that one", async () => {
    const calls: { url: string; method: string; body: BodyInit | null | undefined }[] = [];
    let uploads = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: init?.body });
      if (method === "POST" && url.endsWith("/defects")) return jsonResponse({ id: "0192abcd-0000-7000-8000-000000000070" }, 201);
      if (method === "POST" && url.endsWith("/documents")) {
        uploads += 1;
        return uploads === 2 ? jsonResponse({ title: "Fehler" }, 500) : jsonResponse({ id: `d${uploads}` }, 201);
      }
      return jsonResponse(protocol({ current_step: "defects" }), 200);
    });
    renderIntl(<HandoverEditor initial={protocol({ current_step: "defects" })} />);
    await userEvent.click(screen.getByText("Mangel hinzufügen"));
    await userEvent.type(screen.getByLabelText("Titel"), "Kratzer");
    await userEvent.upload(screen.getByTestId("photo-pick"), [new File(["a"], "a.jpg", { type: "image/jpeg" }), new File(["b"], "b.jpg", { type: "image/jpeg" })]);
    await userEvent.click(screen.getByText("Speichern"));
    await waitFor(() => expect(screen.getByTestId("upload-status")).toHaveTextContent("Fehlgeschlagen"));
    const order = calls.filter((c) => c.method === "POST").map((c) => c.url.split("/").pop());
    expect(order).toEqual(["defects", "documents", "documents"]);
    const first = calls.find((c) => c.method === "POST" && c.url.endsWith("/documents"))!.body as FormData;
    expect(first.get("section")).toBe("defects");
    expect(first.get("item_id")).toBe("0192abcd-0000-7000-8000-000000000070");
    expect(screen.getByTestId("upload-status")).toHaveTextContent("Fertig");
    expect(screen.getByText("Später")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Erneut versuchen"));
    await waitFor(() => expect(uploads).toBe(3));
    await waitFor(() => expect(screen.queryByTestId("upload-status")).not.toBeInTheDocument());
  });

  it("locks the content after a signature and reopens it through Änderung nach Unterschrift with a reason", async () => {
    const calls: { url: string; method: string; body: string | null }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, method: init?.method ?? "GET", body: typeof init?.body === "string" ? init.body : null });
      if (url.endsWith("/changes")) return jsonResponse(protocol({ current_step: "rooms", content_locked: false, status: "in_progress", changes: [{ id: "c1", reason: "Zählernummer falsch", changed_at: "2026-09-25T11:00:00Z", changed_by: "u", changed_by_name: "Timo", signatures_invalidated: 1 }] }), 201);
      return jsonResponse({}, 200);
    });
    renderIntl(<HandoverEditor initial={protocol({ current_step: "rooms", status: "signature_pending", content_locked: true, rooms: [{ id: "r1", name: "Küche" }] })} />);
    expect(screen.getByTestId("content-locked")).toHaveTextContent("Änderung nach Unterschrift");
    expect(screen.queryByText("Raum hinzufügen")).not.toBeInTheDocument();
    expect(screen.queryByText("Bearbeiten")).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("Änderung nach Unterschrift"));
    await userEvent.click(screen.getByTestId("change-confirm"));
    expect(screen.getByRole("alert")).toHaveTextContent("Änderungsgrund");
    expect(calls.some((c) => c.url.endsWith("/changes"))).toBe(false);
    await userEvent.type(screen.getByLabelText("Änderungsgrund"), "Zählernummer falsch");
    await userEvent.click(screen.getByTestId("change-confirm"));
    await waitFor(() => expect(screen.getByText("Raum hinzufügen")).toBeInTheDocument());
    const post = calls.find((c) => c.url.endsWith("/changes"));
    expect(JSON.parse(post?.body ?? "{}")).toEqual({ reason: "Zählernummer falsch" });
    expect(screen.queryByTestId("content-locked")).not.toBeInTheDocument();
  });

  it("shows the hints before completing and offers the forced completion through a ConfirmSheet", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push(`${init?.method ?? "GET"} ${String(input)}`);
      return jsonResponse({}, 200);
    });
    renderIntl(
      <HandoverEditor initial={protocol({ current_step: "summary" })} />,
    );
    await userEvent.click(
      screen.getByText("Protokoll verbindlich abschließen"),
    );
    expect(screen.getByTestId("hints")).toHaveTextContent(
      "Es wurden keine Räume erfasst.",
    );
    expect(screen.queryByTestId("confirm-sheet")).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("Trotz Hinweisen verbindlich abschließen"));
    expect(screen.getByTestId("confirm-sheet")).toHaveTextContent("Es liegen Hinweise vor.");
    await userEvent.click(screen.getByText("Abbrechen"));
    expect(calls.some((c) => c.includes("/complete"))).toBe(false);
  });

  it("hides every write action once the protocol is locked and renders the read view", () => {
    const { container } = renderIntl(
      <HandoverEditor
        initial={protocol({
          status: "completed",
          locked: true,
          finalized: true,
          completed_at: "2026-09-25T10:00:00Z",
          current_step: "rooms",
        })}
      />,
    );
    expect(screen.getByText(/schreibgeschützt/)).toBeInTheDocument();
    expect(screen.getByTestId("handover-summary")).toBeInTheDocument();
    expect(screen.getByTestId("step-summary")).toHaveAttribute("aria-current", "step");
    expect(
      screen.queryByText("Protokoll verbindlich abschließen"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Neue Version anlegen")).toBeInTheDocument();
    expect(screen.getByText("Zustellung vorbereiten")).toBeInTheDocument();
    expect(screen.getByTestId("summary-pdf")).not.toHaveAttribute("target");
    // Only the version reason field is an input; the content has none.
    expect(container.querySelectorAll("input:not(#reason), textarea")).toHaveLength(0);
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

describe("HandoverEditor portal access", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sets up the portal access of a participant with a contact and shows the token once", async () => {
    const calls: { url: string; method: string; body: string | null }[] = [];
    const participant = {
      id: "0192abcd-0000-7000-8000-000000000062",
      role: "moving_in",
      first_name: "Gerd",
      last_name: "Gehilfe",
      contact_id: "0192abcd-0000-7000-8000-000000000063",
      email: "gerd@example.org",
      portal_access: null,
      sort_order: 0,
    };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? init.body : null });
      if (method === "POST" && url.endsWith("/portal-access")) {
        return jsonResponse(
          {
            account_status: "invited",
            right: "edit",
            valid_to: null,
            active: true,
            account_id: "0192abcd-0000-7000-8000-000000000064",
            invitation_token: "abcd.secret-token",
            email: "gerd@example.org",
          },
          201,
        );
      }
      return jsonResponse(
        protocol({
          current_step: "participants",
          participants: [
            {
              ...participant,
              portal_access: { account_status: "invited", right: "edit", valid_to: null, active: true },
            },
          ],
        }),
      );
    });
    renderIntl(
      <HandoverEditor
        initial={protocol({ current_step: "participants", participants: [participant] })}
      />,
    );
    expect(screen.getByLabelText("E-Mail-Adresse für die Einladung")).toHaveValue("gerd@example.org");
    await userEvent.click(screen.getByText("Portalzugang einrichten"));
    await waitFor(() => expect(screen.getByTestId("invitation-token")).toHaveTextContent("abcd.secret-token"));
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe(`/api/bff/handover/protocols/${ID}/participants/${participant.id}/portal-access`);
    expect(JSON.parse(post?.body ?? "{}")).toEqual({ email: "gerd@example.org" });
    await waitFor(() =>
      expect(screen.getByText("Eingeladen, Passwort noch nicht gesetzt")).toBeInTheDocument(),
    );
    expect(screen.getByText("Zugang beenden")).toBeInTheDocument();
  });

  it("offers no portal access for participants without a contact", () => {
    renderIntl(
      <HandoverEditor
        initial={protocol({
          current_step: "participants",
          participants: [{ id: "0192abcd-0000-7000-8000-000000000065", role: "witness", company: "X", contact_id: null, sort_order: 0 }],
        })}
      />,
    );
    expect(screen.queryByTestId("portal-access")).not.toBeInTheDocument();
  });
});
