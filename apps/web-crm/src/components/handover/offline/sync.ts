/** Replay of the queue once the connection is back (rule M30-10, ADR 0016). Items go to the
 *  API in capture order with X-Handover-Client-Key (durable dedupe on the server),
 *  X-Captured-At (device time, reported value) and, for changes of existing rows,
 *  X-Base-Updated-At. The server stays the only place that decides what is stored: a 409
 *  MHVP-HDOV-0004 (server row newer) stops the replay and hands both states to the caller,
 *  any other refusal stops it with the message, a lost connection (status 0) stops it
 *  silently. Ids of items created offline are mapped to the server ids for later entries. */

import { bff, type BffResult } from "@/lib/bff";

import { base64ToBytes } from "./crypto";
import type { HandoverQueue, QueuedItem, QueuedOp } from "./queue";

export type IdMap = Map<string, string>;

const mapId = (ids: IdMap, id: string | null | undefined): string | null => (id ? (ids.get(id) ?? id) : null);

/** Fetch arguments of an operation; used online (no queue) and on replay (with the
 *  offline headers). Temporary ids inside bodies (room_id of a defect) are mapped too. */
export function requestFor(base: string, op: QueuedOp, ids: IdMap = new Map()): { path: string; init: RequestInit } {
  const mapBody = (body: Record<string, unknown>) =>
    Object.fromEntries(Object.entries(body).map(([k, v]) => [k, typeof v === "string" && ids.has(v) ? ids.get(v) : v]));
  switch (op.kind) {
    case "patch_protocol":
      return { path: base, init: { method: "PATCH", body: JSON.stringify(op.body) } };
    case "create_item":
      return { path: `${base}/${op.section}`, init: { method: "POST", body: JSON.stringify(mapBody(op.body)) } };
    case "patch_item":
      return { path: `${base}/${op.section}/${mapId(ids, op.itemId)}`, init: { method: "PATCH", body: JSON.stringify(mapBody(op.body)) } };
    case "delete_item":
      return { path: `${base}/${op.section}/${mapId(ids, op.itemId)}`, init: { method: "DELETE" } };
    case "document": {
      const data = new FormData();
      const bytes = base64ToBytes(op.dataBase64);
      data.append("file", new File([bytes as BlobPart], op.fileName, { type: op.mime }));
      if (op.section && op.itemId) {
        data.append("section", op.section);
        data.append("item_id", mapId(ids, op.itemId) ?? op.itemId);
      }
      return { path: `${base}/documents`, init: { method: "POST", body: data } };
    }
    case "signature":
      return { path: `${base}/signatures`, init: { method: "POST", body: JSON.stringify(mapBody(op.body)) } };
  }
}

export function offlineHeaders(item: QueuedItem): Record<string, string> {
  const headers: Record<string, string> = { "X-Handover-Client-Key": item.id, "X-Captured-At": item.capturedAt };
  const base = "baseUpdatedAt" in item.op ? item.op.baseUpdatedAt : null;
  if (base) headers["X-Base-Updated-At"] = base;
  return headers;
}

export type LogEntry = { at: string; capturedAt: string; kind: QueuedOp["kind"]; result: "ok" | "conflict" | "failed" | "offline" | "discarded" | "kept"; message: string | null };
export type Conflict = { item: QueuedItem; server: Record<string, unknown> | null; message: string };
export type ReplayResult = { done: number; conflict: Conflict | null; failed: { item: QueuedItem; message: string } | null; offline: boolean };

const logs = new Map<string, LogEntry[]>();
const logListeners = new Set<() => void>();

export function syncLog(protocolId: string): LogEntry[] {
  return logs.get(protocolId) ?? [];
}

export function subscribeSyncLog(fn: () => void): () => void {
  logListeners.add(fn);
  return () => logListeners.delete(fn);
}

export function appendLog(protocolId: string, entry: LogEntry): void {
  logs.set(protocolId, [...(logs.get(protocolId) ?? []), entry].slice(-100));
  for (const fn of logListeners) fn();
}

type Send = <T>(path: string, init?: RequestInit) => Promise<BffResult<T>>;

/** Replays the queue of one protocol. `ids` is kept by the caller across runs so that a
 *  replay resumed after a conflict still knows the server ids of earlier entries. */
export async function replay(queue: HandoverQueue, protocolId: string, base: string, ids: IdMap, send: Send = bff): Promise<ReplayResult> {
  let done = 0;
  for (const item of await queue.list(protocolId)) {
    const { path, init } = requestFor(base, item.op, ids);
    const res = await send<{ id?: string }>(path, { ...init, headers: offlineHeaders(item) });
    const at = new Date().toISOString();
    if (res.ok) {
      if (item.op.kind === "create_item" && res.data?.id) ids.set(item.op.tempId, res.data.id);
      await queue.remove(item.id);
      appendLog(protocolId, { at, capturedAt: item.capturedAt, kind: item.op.kind, result: "ok", message: null });
      done += 1;
      continue;
    }
    if (res.status === 0) {
      appendLog(protocolId, { at, capturedAt: item.capturedAt, kind: item.op.kind, result: "offline", message: res.message });
      return { done, conflict: null, failed: null, offline: true };
    }
    if (res.status === 409 && res.problem?.code === "MHVP-HDOV-0004") {
      appendLog(protocolId, { at, capturedAt: item.capturedAt, kind: item.op.kind, result: "conflict", message: res.message });
      const server = (res.problem as unknown as { server?: Record<string, unknown> }).server ?? null;
      return { done, conflict: { item, server, message: res.message }, failed: null, offline: false };
    }
    appendLog(protocolId, { at, capturedAt: item.capturedAt, kind: item.op.kind, result: "failed", message: res.message });
    return { done, conflict: null, failed: { item, message: res.message }, offline: false };
  }
  return { done, conflict: null, failed: null, offline: false };
}
