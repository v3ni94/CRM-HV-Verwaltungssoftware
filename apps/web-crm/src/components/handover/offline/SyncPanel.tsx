"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Sheet } from "@/components/ui/Sheet";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

import type { HandoverOffline } from "./useHandoverOffline";

function fieldsOf(value: Record<string, unknown> | null | undefined): [string, string][] {
  if (!value) return [];
  return Object.entries(value)
    .filter(([k, v]) => !k.startsWith("_") && !["id", "tenant_id", "protocol_id", "created_at", "updated_at", "created_by", "updated_by", "import_source", "sort_order"].includes(k) && v !== null && v !== undefined && v !== "")
    .map(([k, v]) => [k, typeof v === "object" ? JSON.stringify(v) : String(v)]);
}

/** Replay log of one protocol (rule M30-10) and the conflict question: when the server row
 *  is newer than the copy a queued change was based on, both states are shown and the
 *  person decides which one stays. Nothing is decided automatically. */
export function SyncPanel({ offline }: { offline: HandoverOffline }) {
  const t = useTranslations("Handover.offline");
  const [open, setOpen] = useState(false);
  if (!offline.enabled) return null;
  const conflict = offline.conflict;
  const mine = conflict && "body" in conflict.item.op ? (conflict.item.op.body as Record<string, unknown>) : null;
  return (
    <>
      {offline.log.length > 0 ? (
        <details className={`${ui.card} text-sm`} data-testid="sync-log" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
          <summary className="cursor-pointer font-medium">{t("log.title", { count: offline.log.length })}</summary>
          <ul className="mt-2 flex flex-col gap-1">
            {offline.log.map((entry, i) => (
              <li key={`${entry.at}-${i}`} className="flex flex-wrap gap-x-2">
                <span className={ui.num}>{formatDateTime(entry.at)}</span>
                <span>{t(`log.kind.${entry.kind}`)}</span>
                <span className="text-muted">{t("log.captured", { at: formatDateTime(entry.capturedAt) })}</span>
                <span className={entry.result === "ok" ? "text-success-fg" : entry.result === "offline" ? "text-muted" : "text-warning-fg"}>{t(`log.result.${entry.result}`)}</span>
                {entry.message ? <span className="text-muted">{entry.message}</span> : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      <Sheet
        open={conflict !== null}
        onClose={() => void offline.resolveConflict("server")}
        title={t("conflict.title")}
        size="md"
        testId="offline-conflict"
        footer={
          <div className={ui.formActions}>
            <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={() => void offline.resolveConflict("server")} data-testid="conflict-keep-server">
              {t("conflict.keepServer")}
            </button>
            <button type="button" className={`${ui.primary} ${ui.actionFull}`} onClick={() => void offline.resolveConflict("mine")} data-testid="conflict-keep-mine">
              {t("conflict.keepMine")}
            </button>
          </div>
        }
      >
        {conflict ? (
          <div className="flex flex-col gap-3 text-sm">
            <p>{conflict.message}</p>
            <p className="text-muted">{t("conflict.captured", { at: formatDateTime(conflict.item.capturedAt) })}</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className={ui.card}>
                <p className="font-medium">{t("conflict.server")}</p>
                <dl>
                  {fieldsOf(conflict.server).map(([k, v]) => (
                    <div key={k} className="flex gap-2">
                      <dt className="text-muted">{k}</dt>
                      <dd>{v}</dd>
                    </div>
                  ))}
                </dl>
              </div>
              <div className={ui.card}>
                <p className="font-medium">{t("conflict.mine")}</p>
                <dl>
                  {fieldsOf(mine).map(([k, v]) => (
                    <div key={k} className="flex gap-2">
                      <dt className="text-muted">{k}</dt>
                      <dd>{v}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </div>
          </div>
        ) : null}
      </Sheet>
    </>
  );
}
