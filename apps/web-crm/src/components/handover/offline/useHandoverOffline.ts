"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { bff, type BffResult } from "@/lib/bff";
import { useOnline } from "@/lib/useOnline";

import type { Full } from "../types";
import { applyQueued } from "./apply";
import { bytesToBase64 } from "./crypto";
import { getQueue, type HandoverQueue, type QueuedItem, type QueuedOp, type Section } from "./queue";
import { appendLog, type Conflict, type IdMap, type LogEntry, replay, requestFor, subscribeSyncLog, syncLog } from "./sync";

export type SyncState = "idle" | "running" | "conflict" | "failed";

export type HandoverOffline = {
  enabled: boolean;
  online: boolean;
  pending: QueuedItem[];
  lost: number;
  /** Optimistic view: server copy plus queued changes. */
  view: Full;
  /** Sends an operation online, or queues it while offline (or when the API is unreachable). */
  send: <T>(op: QueuedOp) => Promise<BffResult<T>>;
  /** Reloads the server copy; while offline the current view is kept. */
  reload: () => Promise<void>;
  setServer: (p: Full) => void;
  sync: () => Promise<void>;
  syncState: SyncState;
  conflict: Conflict | null;
  /** "server" keeps the server row and drops the queued change, "mine" resends it. */
  resolveConflict: (choice: "server" | "mine") => Promise<void>;
  failure: string | null;
  discardAll: () => Promise<void>;
  log: LogEntry[];
};

function optimistic<T>(op: QueuedOp, capturedAt: string): BffResult<T> {
  const data =
    op.kind === "create_item"
      ? { id: op.tempId, ...op.body, _pending: true, captured_at: capturedAt }
      : op.kind === "patch_item"
        ? { id: op.itemId, ...op.body, _pending: true }
        : op.kind === "patch_protocol"
          ? { ...op.body, _pending: true }
          : { _pending: true };
  return { ok: true, data: data as T, status: 202, etag: null, totalCount: null, page: null, pageSize: null };
}

/** Offline capture of one protocol in the CRM editor (rule M30-10, ADR 0016, tenant switch
 *  handover_offline_enabled). With the switch off `send` is a plain API call and nothing is
 *  ever stored on the device. */
export function useHandoverOffline(initial: Full, enabled: boolean, queue: HandoverQueue | null = null): HandoverOffline {
  const online = useOnline();
  const q = useMemo(() => queue ?? (enabled ? getQueue() : null), [queue, enabled]);
  const base = `/api/bff/handover/protocols/${initial.id}`;
  const [server, setServer] = useState<Full>(initial);
  const [pending, setPending] = useState<QueuedItem[]>([]);
  const [lost, setLost] = useState(0);
  const [syncState, setSyncState] = useState<SyncState>("idle");
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [log, setLog] = useState<LogEntry[]>(() => syncLog(initial.id));
  const ids = useRef<IdMap>(new Map());
  const running = useRef(false);

  const refresh = useCallback(async () => {
    if (!q) return;
    setPending(await q.list(initial.id));
    setLost(q.lost);
  }, [q, initial.id]);

  useEffect(() => {
    if (!q) return;
    void refresh();
    return q.subscribe(() => void refresh());
  }, [q, refresh]);

  useEffect(() => subscribeSyncLog(() => setLog(syncLog(initial.id))), [initial.id]);

  const reload = useCallback(async () => {
    const res = await bff<Full>(base);
    if (res.ok) setServer(res.data);
  }, [base]);

  const send = useCallback(
    async <T,>(op: QueuedOp): Promise<BffResult<T>> => {
      if (q && (!online || pending.length > 0)) {
        // Order matters: while something waits, every later change waits too.
        const item = await q.enqueue(initial.id, op);
        return optimistic<T>(op, item.capturedAt);
      }
      const { path, init } = requestFor(base, op);
      const res = await bff<T>(path, init);
      if (!res.ok && res.status === 0 && q) {
        const item = await q.enqueue(initial.id, op);
        return optimistic<T>(op, item.capturedAt);
      }
      if (!res.ok && res.status === 401 && q) await q.wipe();
      return res;
    },
    [q, online, pending.length, base, initial.id],
  );

  const sync = useCallback(async () => {
    if (!q || running.current) return;
    running.current = true;
    setSyncState("running");
    setFailure(null);
    try {
      const result = await replay(q, initial.id, base, ids.current);
      if (result.conflict) {
        setConflict(result.conflict);
        setSyncState("conflict");
      } else if (result.failed) {
        setFailure(result.failed.message);
        setSyncState("failed");
      } else {
        setSyncState("idle");
        if (!result.offline) {
          await q.clearProtocol(initial.id);
          await reload();
        }
      }
    } finally {
      running.current = false;
      await refresh();
    }
  }, [q, initial.id, base, reload, refresh]);

  // Replay as soon as the connection is back and something waits.
  useEffect(() => {
    if (online && pending.length > 0 && syncState === "idle") void sync();
  }, [online, pending.length, syncState, sync]);

  const resolveConflict = useCallback(
    async (choice: "server" | "mine") => {
      if (!q || !conflict) return;
      const { item } = conflict;
      if (choice === "server") {
        await q.remove(item.id);
        appendLog(initial.id, { at: new Date().toISOString(), capturedAt: item.capturedAt, kind: item.op.kind, result: "discarded", message: null });
      } else if ("baseUpdatedAt" in item.op) {
        await q.remove(item.id);
        await q.enqueue(initial.id, { ...item.op, baseUpdatedAt: null }, item.id);
        appendLog(initial.id, { at: new Date().toISOString(), capturedAt: item.capturedAt, kind: item.op.kind, result: "kept", message: null });
      }
      setConflict(null);
      setSyncState("idle");
    },
    [q, conflict, initial.id],
  );

  const discardAll = useCallback(async () => {
    if (!q) return;
    await q.clearProtocol(initial.id);
    ids.current = new Map();
    setConflict(null);
    setFailure(null);
    setSyncState("idle");
    appendLog(initial.id, { at: new Date().toISOString(), capturedAt: new Date().toISOString(), kind: "patch_protocol", result: "discarded", message: "Lokale Entwürfe gelöscht" });
    await reload();
  }, [q, initial.id, reload]);

  const view = useMemo(() => (pending.length ? applyQueued(server, pending) : server), [server, pending]);

  return { enabled: Boolean(q), online, pending, lost, view, send, reload, setServer, sync, syncState, conflict, resolveConflict, failure, discardAll, log };
}

/** Reads a picked file into the queue format (already downscaled by the caller). */
export async function fileToDocumentOp(file: File | Blob, fileName: string, section: Section | null, itemId: string | null): Promise<QueuedOp> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  return { kind: "document", section, itemId, fileName, mime: file.type || "application/octet-stream", dataBase64: bytesToBase64(bytes) };
}

export type Send = <T>(op: QueuedOp) => Promise<BffResult<T>>;

/** The `send` of the editor for the sub components (section lists, item forms, photos). */
export const SendContext = createContext<Send | null>(null);

/** `send` from the editor context, or a plain API call for components rendered on their own. */
export function useSend(base: string): Send {
  const fromContext = useContext(SendContext);
  return useMemo(() => fromContext ?? (<T,>(op: QueuedOp) => { const { path, init } = requestFor(base, op); return bff<T>(path, init); }), [fromContext, base]);
}
