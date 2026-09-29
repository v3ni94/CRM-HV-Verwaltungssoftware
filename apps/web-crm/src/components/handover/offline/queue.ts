/** Offline queue of one CRM page session (rule M30-10, ADR 0016). Every queued change is a
 *  sealed record with its own client key (the record id, sent as X-Handover-Client-Key on
 *  replay), the protocol, a sequence number that keeps the order of capture and the device
 *  time of capture (`capturedAt`, ISO 8601 with offset, reported by the device and never
 *  proof). The queue is deleted on logout, on page unload, after a successful replay and by
 *  the explicit action "Lokale Entwürfe löschen". */

import { forgetSessionKey, openJson, sealJson } from "./crypto";
import { defaultStore, type QueueStore } from "./store";

export type Section = "participants" | "meters" | "rooms" | "defects" | "keys" | "items" | "notes";

export type QueuedOp =
  | { kind: "patch_protocol"; body: Record<string, unknown>; baseUpdatedAt: string | null }
  | { kind: "create_item"; section: Section; tempId: string; body: Record<string, unknown> }
  | { kind: "patch_item"; section: Section; itemId: string; body: Record<string, unknown>; baseUpdatedAt: string | null }
  | { kind: "delete_item"; section: Section; itemId: string }
  | { kind: "document"; section: Section | null; itemId: string | null; fileName: string; mime: string; dataBase64: string }
  | { kind: "signature"; body: Record<string, unknown> };

export type QueuedItem = { id: string; protocolId: string; seq: number; capturedAt: string; op: QueuedOp };

type Listener = () => void;

function deviceNow(): string {
  const d = new Date();
  const offset = -d.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  const pad = (n: number) => String(Math.abs(n)).padStart(2, "0");
  const local = new Date(d.getTime() + offset * 60_000).toISOString().slice(0, 19);
  return `${local}${sign}${pad(Math.trunc(offset / 60))}:${pad(offset % 60)}`;
}

export class HandoverQueue {
  private listeners = new Set<Listener>();
  private seq = 0;
  /** Records that could not be opened (key lost, for example after a reload) and were
   *  discarded on the last read. */
  lost = 0;

  constructor(private readonly store: QueueStore) {}

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private notify(): void {
    for (const fn of this.listeners) fn();
  }

  /** Adds a change; an id that already exists is ignored (dedupe by client key). */
  async enqueue(protocolId: string, op: QueuedOp, id?: string): Promise<QueuedItem> {
    const existing = await this.all();
    const key = id ?? globalThis.crypto.randomUUID();
    const found = existing.find((x) => x.id === key);
    if (found) return found;
    this.seq = Math.max(this.seq, ...existing.map((x) => x.seq)) + 1;
    const item: QueuedItem = { id: key, protocolId, seq: this.seq, capturedAt: deviceNow(), op };
    const sealed = await sealJson(item);
    await this.store.put({ id: key, seq: item.seq, iv: sealed.iv, data: sealed.data });
    this.notify();
    return item;
  }

  /** All readable items in capture order; unreadable records are discarded and counted. */
  async all(): Promise<QueuedItem[]> {
    const records = await this.store.all();
    const items: QueuedItem[] = [];
    let lost = 0;
    for (const record of records) {
      try {
        items.push(await openJson<QueuedItem>({ iv: record.iv, data: record.data }));
      } catch {
        lost += 1;
        await this.store.remove(record.id);
      }
    }
    if (lost) {
      this.lost += lost;
      this.notify();
    }
    return items.sort((a, b) => a.seq - b.seq);
  }

  async list(protocolId: string): Promise<QueuedItem[]> {
    return (await this.all()).filter((x) => x.protocolId === protocolId);
  }

  async count(protocolId?: string): Promise<number> {
    return (protocolId ? await this.list(protocolId) : await this.all()).length;
  }

  async remove(id: string): Promise<void> {
    await this.store.remove(id);
    this.notify();
  }

  async clearProtocol(protocolId: string): Promise<void> {
    for (const item of await this.list(protocolId)) await this.store.remove(item.id);
    this.notify();
  }

  /** Deletes every record and forgets the key (logout, session end, explicit action). */
  async wipe(): Promise<void> {
    await this.store.clear();
    forgetSessionKey();
    this.lost = 0;
    this.notify();
  }
}

let singleton: HandoverQueue | null = null;

/** The queue of this page session. Registered once: page unload wipes the records, because
 *  the key does not survive the unload either and nothing readable must stay on the device. */
export function getQueue(): HandoverQueue {
  if (!singleton) {
    singleton = new HandoverQueue(defaultStore());
    if (typeof window !== "undefined") {
      const q = singleton;
      window.addEventListener("pagehide", () => {
        void q.wipe();
      });
    }
  }
  return singleton;
}

export function createQueue(store: QueueStore): HandoverQueue {
  return new HandoverQueue(store);
}
