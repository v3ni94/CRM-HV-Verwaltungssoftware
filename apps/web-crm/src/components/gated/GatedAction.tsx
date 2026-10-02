"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { GateStatusNotice } from "./GateStatusNotice";
import { type GateId, useReleaseGate } from "./useReleaseGate";

/**
 * AJ28: one POST action behind a release gate. Visible always, disabled while the gate is not
 * open (or its state unknown), while a request runs (no double submit) and while `blocked`
 * holds. The API keeps its own lock; a refusal is shown as returned.
 */
export function GatedAction<T>({
  gate,
  url,
  label,
  lockedText,
  hint,
  blocked = false,
  body,
  onDone,
  testId,
}: {
  gate: GateId;
  url: string;
  label: string;
  lockedText: string;
  hint?: string;
  blocked?: boolean;
  body?: unknown;
  onDone?: (data: T) => void;
  testId: string;
}) {
  const t = useTranslations("gatedMasks");
  const state = useReleaseGate(gate);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const open = state.status === "open";

  const run = async () => {
    if (!open || busy || blocked) return;
    setBusy(true);
    setError(null);
    const res = await bff<T>(url, { method: "POST", body: JSON.stringify(body ?? {}) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setDone(true);
    onDone?.(res.data);
  };

  return (
    <div className="flex flex-col gap-1" data-testid={testId}>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={ui.buttonSm} onClick={() => void run()} disabled={!open || busy || blocked} aria-busy={busy}>
          {busy ? t("busy") : label}
        </button>
        {hint ? <span className={ui.help}>{hint}</span> : null}
      </div>
      <GateStatusNotice gate={gate} state={state} lockedText={lockedText} />
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {done ? (
        <p role="status" className={ui.success}>
          {t("done")}
        </p>
      ) : null}
    </div>
  );
}
