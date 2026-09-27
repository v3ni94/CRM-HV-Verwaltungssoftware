"use client";
/** Autosave per field for inline editing (ADR 0012): every change becomes one PATCH via the
 *  BFF with `If-Match` from the current `version`. Saves are debounced per field, sent one after
 *  the other (the version of the response feeds the next request), a network failure is retried
 *  once, a 412 is surfaced as a conflict ("Von jemand anderem geändert, neu laden") and a 422
 *  is shown at the field from the problem details (ADR 0004). */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { bff, type BffResult } from "@/lib/bff";
import { fieldPath, type Problem } from "@/lib/problem";

export type AutosaveStatus = "idle" | "saving" | "saved" | "error" | "conflict";

export type FieldState = { status: AutosaveStatus; message: string | null };

export type AutosaveOptions<T> = {
  /** API path relative to the BFF, e.g. `properties/<id>` or `contracts/<id>/notes`. */
  path: string;
  /** Current record version (ETag); `null` sends no `If-Match` (e.g. contract notes). */
  version?: number | null;
  /** Called with the server response after each successful save. */
  onSaved?: (data: T) => void;
  /** Wait after the last change of a field before the PATCH is sent. Default 400 ms. */
  debounceMs?: number;
  /** Wraps a single field into the request body; default `{ [field]: value }`. */
  body?: (field: string, value: unknown) => Record<string, unknown>;
};

export type Autosave<T> = {
  /** Queues the value of a field; the PATCH goes out after the debounce. */
  save: (field: string, value: unknown) => void;
  /** Sends every pending field now (e.g. before leaving the edit mode). */
  flush: () => Promise<void>;
  fieldState: (field: string) => FieldState;
  /** Overall status: saving while anything is in flight, conflict after a 412. */
  status: AutosaveStatus;
  version: number | null;
  /** True after a 412; edits are blocked until the page is reloaded. */
  conflict: boolean;
  /** Last record returned by the server. */
  data: T | null;
};

const IDLE: FieldState = { status: "idle", message: null };

function fieldMessage(problem: Problem | null, field: string, fallback: string): string {
  const hit = problem?.errors?.find((e) => (fieldPath(e.location) ?? e.field) === field);
  return hit?.message ?? fallback;
}

export function useAutosave<T extends { version?: number } = { version?: number }>(options: AutosaveOptions<T>): Autosave<T> {
  const { path, onSaved, debounceMs = 400, body } = options;
  const [states, setStates] = useState<Record<string, FieldState>>({});
  const [version, setVersion] = useState<number | null>(options.version ?? null);
  const [conflict, setConflict] = useState(false);
  const [data, setData] = useState<T | null>(null);
  const versionRef = useRef<number | null>(options.version ?? null);
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const pending = useRef<Map<string, unknown>>(new Map());
  const queue = useRef<Promise<void>>(Promise.resolve());
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;
  const bodyRef = useRef(body);
  bodyRef.current = body;

  useEffect(() => {
    if (options.version != null && options.version !== versionRef.current) {
      versionRef.current = options.version;
      setVersion(options.version);
      setConflict(false);
    }
  }, [options.version]);

  const setField = useCallback((field: string, state: FieldState) => {
    setStates((prev) => ({ ...prev, [field]: state }));
  }, []);

  const send = useCallback(
    async (field: string, value: unknown): Promise<void> => {
      setField(field, { status: "saving", message: null });
      const request = (): Promise<BffResult<T>> => {
        const headers: Record<string, string> = {};
        if (versionRef.current != null) headers["if-match"] = String(versionRef.current);
        const payload = bodyRef.current ? bodyRef.current(field, value) : { [field]: value };
        return bff<T>(`/api/bff/${path}`, { method: "PATCH", headers, body: JSON.stringify(payload) });
      };
      let result = await request();
      // One retry on a network failure (status 0); every other answer is final.
      if (!result.ok && result.status === 0) result = await request();
      if (result.ok) {
        const next = result.data?.version ?? (result.etag ? Number(result.etag.replace(/"/g, "")) : null);
        if (next != null && Number.isFinite(next)) {
          versionRef.current = next;
          setVersion(next);
        }
        setData(result.data);
        onSavedRef.current?.(result.data);
        setField(field, { status: "saved", message: null });
        return;
      }
      if (result.status === 412) {
        setConflict(true);
        setField(field, { status: "conflict", message: result.message });
        return;
      }
      setField(field, { status: "error", message: fieldMessage(result.problem, field, result.message) });
    },
    [path, setField],
  );

  const enqueue = useCallback(
    (field: string) => {
      const value = pending.current.get(field);
      pending.current.delete(field);
      queue.current = queue.current.then(() => send(field, value)).catch(() => undefined);
      return queue.current;
    },
    [send],
  );

  const save = useCallback(
    (field: string, value: unknown) => {
      if (conflict) return;
      pending.current.set(field, value);
      const existing = timers.current.get(field);
      if (existing) clearTimeout(existing);
      timers.current.set(
        field,
        setTimeout(() => {
          timers.current.delete(field);
          void enqueue(field);
        }, debounceMs),
      );
    },
    [conflict, debounceMs, enqueue],
  );

  const flush = useCallback(async () => {
    for (const [field, timer] of timers.current) {
      clearTimeout(timer);
      timers.current.delete(field);
      void enqueue(field);
    }
    await queue.current;
  }, [enqueue]);

  useEffect(() => {
    const active = timers.current;
    return () => {
      for (const timer of active.values()) clearTimeout(timer);
      active.clear();
    };
  }, []);

  const status = useMemo<AutosaveStatus>(() => {
    if (conflict) return "conflict";
    const all = Object.values(states);
    if (all.some((s) => s.status === "saving")) return "saving";
    if (all.some((s) => s.status === "error")) return "error";
    if (all.some((s) => s.status === "saved")) return "saved";
    return "idle";
  }, [conflict, states]);

  const fieldState = useCallback((field: string) => states[field] ?? IDLE, [states]);

  return { save, flush, fieldState, status, version, conflict, data };
}
