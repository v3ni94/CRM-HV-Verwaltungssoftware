import { webcrypto } from "node:crypto";

import { applyQueued } from "./apply";
import { forgetSessionKey, getSessionKey } from "./crypto";
import { createQueue, type QueuedItem } from "./queue";
import { MemoryStore } from "./store";
import { offlineHeaders, replay, requestFor, syncLog } from "./sync";
import type { Full } from "../types";

// jsdom has no WebCrypto; the queue needs AES-GCM and random ids.
beforeAll(() => {
  if (!globalThis.crypto?.subtle) Object.defineProperty(globalThis, "crypto", { value: webcrypto, configurable: true });
});
beforeEach(() => forgetSessionKey());

const PID = "0192abcd-0000-7000-8000-000000000060";
const BASE = `/api/bff/handover/protocols/${PID}`;

function full(overrides: Partial<Full> = {}): Full {
  return {
    id: PID,
    number: "UP-1",
    version: 1,
    parent_id: null,
    change_reason: null,
    kind: "rental",
    status: "draft",
    current_step: "rooms",
    property_id: null,
    unit_id: null,
    contract_id: null,
    listing_id: null,
    street: null,
    house_number: null,
    postal_code: null,
    city: null,
    object_label: null,
    building: null,
    floor: null,
    unit_number: null,
    unit_label: null,
    unit_position: null,
    external_object_number: null,
    owner_name: null,
    handover_date: null,
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
    address: "",
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

describe("HandoverQueue", () => {
  it("seals every record: no plain text of the protocol, the bodies or photos in the store", async () => {
    const store = new MemoryStore();
    const queue = createQueue(store);
    await queue.enqueue(PID, { kind: "create_item", section: "rooms", tempId: "tmp-1", body: { name: "Kellerraum Erika Muster" } });
    await queue.enqueue(PID, { kind: "document", section: "rooms", itemId: "tmp-1", fileName: "foto.jpg", mime: "image/jpeg", dataBase64: btoa("JPEGDATA") });
    const records = await store.all();
    expect(records).toHaveLength(2);
    for (const record of records) {
      const raw = new TextDecoder().decode(new Uint8Array(record.data));
      expect(raw).not.toContain("Erika");
      expect(raw).not.toContain(PID);
      expect(raw).not.toContain("foto.jpg");
      expect(raw).not.toContain(btoa("JPEGDATA"));
      expect(record.iv).toHaveLength(12);
    }
  });

  it("decrypts in capture order with device time and dedupes by client key", async () => {
    const queue = createQueue(new MemoryStore());
    const first = await queue.enqueue(PID, { kind: "patch_protocol", body: { city: "Bernau" }, baseUpdatedAt: null });
    const second = await queue.enqueue(PID, { kind: "create_item", section: "rooms", tempId: "tmp-1", body: { name: "Küche" } });
    await queue.enqueue("other-protocol", { kind: "create_item", section: "keys", tempId: "tmp-2", body: {} });
    const again = await queue.enqueue(PID, { kind: "patch_protocol", body: { city: "Berlin" }, baseUpdatedAt: null }, first.id);
    expect(again.id).toBe(first.id);
    expect((again.op as { body: { city: string } }).body.city).toBe("Bernau");
    const items = await queue.list(PID);
    expect(items.map((x) => x.id)).toEqual([first.id, second.id]);
    expect(items[0]!.seq).toBeLessThan(items[1]!.seq);
    expect(items[0]!.capturedAt).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$/);
    expect(await queue.count()).toBe(3);
    expect(await queue.count(PID)).toBe(2);
  });

  it("wipe deletes everything and forgets the key; records of a lost key are discarded", async () => {
    const store = new MemoryStore();
    const queue = createQueue(store);
    await queue.enqueue(PID, { kind: "create_item", section: "rooms", tempId: "tmp-1", body: { name: "Bad" } });
    const before = await getSessionKey();
    await queue.wipe();
    expect(await store.all()).toHaveLength(0);
    expect(await getSessionKey()).not.toBe(before);

    // Reload while offline: the records survive in the store, the key does not.
    await queue.enqueue(PID, { kind: "create_item", section: "rooms", tempId: "tmp-2", body: { name: "Flur" } });
    forgetSessionKey();
    const listener = vi.fn();
    queue.subscribe(listener);
    expect(await queue.list(PID)).toEqual([]);
    expect(queue.lost).toBe(1);
    expect(await store.all()).toHaveLength(0);
    expect(listener).toHaveBeenCalled();
  });

  it("clearProtocol removes only the protocol's items and notifies", async () => {
    const queue = createQueue(new MemoryStore());
    await queue.enqueue(PID, { kind: "create_item", section: "rooms", tempId: "tmp-1", body: {} });
    await queue.enqueue("other", { kind: "create_item", section: "rooms", tempId: "tmp-2", body: {} });
    await queue.clearProtocol(PID);
    expect(await queue.count(PID)).toBe(0);
    expect(await queue.count("other")).toBe(1);
  });
});

describe("applyQueued", () => {
  it("renders the server copy plus the queued changes in order with pending markers", async () => {
    const queue = createQueue(new MemoryStore());
    await queue.enqueue(PID, { kind: "patch_protocol", body: { city: "Bernau" }, baseUpdatedAt: null });
    await queue.enqueue(PID, { kind: "create_item", section: "rooms", tempId: "tmp-1", body: { name: "Küche" } });
    await queue.enqueue(PID, { kind: "patch_item", section: "rooms", itemId: "tmp-1", body: { name: "Küche EG" }, baseUpdatedAt: null });
    await queue.enqueue(PID, { kind: "delete_item", section: "rooms", itemId: "r-server" });
    await queue.enqueue(PID, { kind: "document", section: "rooms", itemId: "tmp-1", fileName: "foto.jpg", mime: "image/jpeg", dataBase64: btoa("x") });
    await queue.enqueue(PID, { kind: "signature", body: { signer_name: "Erika" } });
    const view = applyQueued(full({ rooms: [{ id: "r-server", name: "Alt" }] }), await queue.list(PID));
    expect(view.city).toBe("Bernau");
    expect(view.status).toBe("signature_pending");
    expect(view.rooms).toEqual([expect.objectContaining({ id: "tmp-1", name: "Küche EG", _pending: true })]);
    expect(view.documents).toEqual([expect.objectContaining({ item_id: "tmp-1", kind: "photo", _pending: true })]);
    expect(view.signatures).toEqual([expect.objectContaining({ signer_name: "Erika", _pending: true })]);
  });
});

describe("replay", () => {
  function item(id: string, op: QueuedItem["op"], capturedAt = "2026-09-28T16:45:12+02:00"): QueuedItem {
    return { id, protocolId: PID, seq: 1, capturedAt, op };
  }

  it("builds requests with the offline headers and maps temporary ids", () => {
    const ids = new Map([["tmp-1", "srv-1"]]);
    const create = requestFor(BASE, { kind: "create_item", section: "defects", tempId: "tmp-9", body: { room_id: "tmp-1", title: "Riss" } }, ids);
    expect(create.path).toBe(`${BASE}/defects`);
    expect(JSON.parse(String(create.init.body))).toEqual({ room_id: "srv-1", title: "Riss" });
    const patch = requestFor(BASE, { kind: "patch_item", section: "rooms", itemId: "tmp-1", body: { name: "x" }, baseUpdatedAt: "2026-09-28T10:00:00Z" }, ids);
    expect(patch.path).toBe(`${BASE}/rooms/srv-1`);
    const doc = requestFor(BASE, { kind: "document", section: "rooms", itemId: "tmp-1", fileName: "f.jpg", mime: "image/jpeg", dataBase64: btoa("abc") }, ids);
    expect((doc.init.body as FormData).get("item_id")).toBe("srv-1");
    expect(((doc.init.body as FormData).get("file") as File).name).toBe("f.jpg");
    const headers = offlineHeaders(item("key-1", { kind: "patch_item", section: "rooms", itemId: "tmp-1", body: {}, baseUpdatedAt: "2026-09-28T10:00:00Z" }));
    expect(headers).toEqual({ "X-Handover-Client-Key": "key-1", "X-Captured-At": "2026-09-28T16:45:12+02:00", "X-Base-Updated-At": "2026-09-28T10:00:00Z" });
  });

  it("replays in order, maps created ids, stops on a conflict with both states and logs", async () => {
    const queue = createQueue(new MemoryStore());
    await queue.enqueue(PID, { kind: "create_item", section: "rooms", tempId: "tmp-1", body: { name: "Küche" } });
    await queue.enqueue(PID, { kind: "patch_item", section: "rooms", itemId: "tmp-1", body: { name: "Küche EG" }, baseUpdatedAt: "2026-09-28T10:00:00Z" });
    await queue.enqueue(PID, { kind: "create_item", section: "keys", tempId: "tmp-2", body: { key_type: "front" } });
    const calls: { path: string; headers: Record<string, string> }[] = [];
    const send = vi.fn(async (path: string, init?: RequestInit) => {
      calls.push({ path, headers: init?.headers as Record<string, string> });
      if (path.endsWith("/rooms")) return { ok: true as const, data: { id: "srv-1" }, status: 201, etag: null, totalCount: null, page: null, pageSize: null };
      return { ok: false as const, status: 409, problem: { code: "MHVP-HDOV-0004", server: { name: "Küche neu" } } as never, message: "Serverstand neuer" };
    });
    const ids = new Map<string, string>();
    const result = await replay(queue, PID, BASE, ids, send as never);
    expect(result.done).toBe(1);
    expect(result.conflict?.server).toEqual({ name: "Küche neu" });
    expect(calls.map((c) => c.path)).toEqual([`${BASE}/rooms`, `${BASE}/rooms/srv-1`]);
    expect(calls[0]!.headers["X-Captured-At"]).toMatch(/T/);
    expect(ids.get("tmp-1")).toBe("srv-1");
    expect(await queue.count(PID)).toBe(2);
    expect(syncLog(PID).map((e) => e.result)).toEqual(["ok", "conflict"]);
  });
});
