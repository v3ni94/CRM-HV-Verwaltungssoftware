import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { webcrypto } from "node:crypto";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HandoverEditor } from "../HandoverEditor";
import type { Full } from "../types";
import { getQueue } from "./queue";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/makler/uebergabe/1",
  useSearchParams: () => new URLSearchParams(),
}));

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
  if (!globalThis.crypto?.subtle) Object.defineProperty(globalThis, "crypto", { value: webcrypto, configurable: true });
});
afterEach(async () => {
  vi.restoreAllMocks();
  await getQueue().wipe();
  Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
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
    contract_id: null,
    listing_id: null,
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
    external_object_number: null,
    owner_name: null,
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
    hints: [],
    hint_codes: [],
    contract: null,
    content_locked: false,
    changes: [],
    versions: [],
    ...overrides,
  } as Full;
}

describe("HandoverEditor offline capture (M30-10)", () => {
  it("queues a new room while offline, shows the banner with the count and replays it once online", async () => {
    const calls: { url: string; method: string; headers: Headers }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, headers: new Headers(init?.headers) });
      if (!navigator.onLine) throw new TypeError("network");
      if (method === "POST" && url.endsWith("/rooms")) return jsonResponse({ id: "0192abcd-0000-7000-8000-000000000061", name: "Küche" }, 201);
      if (method === "GET") return jsonResponse(protocol({ rooms: [{ id: "0192abcd-0000-7000-8000-000000000061", name: "Küche", condition: null, sort_order: 0 }] }));
      return jsonResponse({}, 200);
    });
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    renderIntl(<HandoverEditor initial={protocol()} offlineEnabled />);
    expect(screen.getByTestId("offline-banner")).toHaveTextContent("Keine Verbindung. Offline Erfassung aktiv.");
    expect(screen.queryByTestId("offline-notice")).toBeNull();

    await userEvent.click(screen.getByText("Raum hinzufügen"));
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Küche");
    await userEvent.click(screen.getByText("Speichern"));
    // The room is visible from the queue, nothing was sent, the banner counts one change.
    await waitFor(() => expect(screen.getByTestId("offline-pending")).toHaveTextContent("1 Änderung wartet auf den Abgleich."));
    expect(within(screen.getByTestId("section-rooms")).getAllByText("Küche").length).toBeGreaterThan(0);
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
    expect(screen.getByTestId("step-rooms")).toHaveTextContent("Räume1");

    // Connection back: the queue is replayed with the offline headers and then deleted.
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
    window.dispatchEvent(new Event("online"));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toBe(`/api/bff/handover/protocols/${ID}/rooms`);
    expect(post.headers.get("x-handover-client-key")).toMatch(/^[0-9a-f-]{36}$/);
    expect(post.headers.get("x-captured-at")).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    await waitFor(() => expect(screen.queryByTestId("offline-pending")).toBeNull());
    expect(await getQueue().count(ID)).toBe(0);
    expect(screen.getByTestId("sync-log")).toHaveTextContent("übertragen");
  });

  it("keeps the plain notice and stores nothing while the tenant switch is off", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}, 200));
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    renderIntl(<HandoverEditor initial={protocol()} />);
    expect(screen.getByTestId("offline-notice")).toBeInTheDocument();
    expect(screen.queryByTestId("offline-banner")).toBeNull();
    expect(await getQueue().count(ID)).toBe(0);
  });
});
