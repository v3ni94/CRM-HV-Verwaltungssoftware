"use client";

import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

import type { GateId, GateState } from "./useReleaseGate";

/** AJ28: gate badge plus the lock text shown while the gate is not open. */
export function GateStatusNotice({ gate, state, lockedText }: { gate: GateId; state: GateState; lockedText: string }) {
  const t = useTranslations("gatedMasks");
  const status = state.status === "open" ? "open" : state.status === "loading" ? "loading" : "closed";
  return (
    <div className="mt-2" data-testid={`gate-status-${gate}`} data-gate-open={status === "open" ? "true" : "false"}>
      <p className={ui.help}>
        {t(`gateStatus.${status}`, { gate })}
      </p>
      {status !== "open" ? (
        <p className={ui.notice} role="note">
          {lockedText}
        </p>
      ) : null}
    </div>
  );
}
