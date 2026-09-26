"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { ResolutionDialog, isClosingStatus, type Resolution } from "@/components/tickets/ResolutionDialog";
import { STATUSES } from "@/components/tickets/TicketForms";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

const STATUS_VARIANT: Record<string, StatusPillVariant> = {
  new: "gold",
  in_progress: "warning",
  waiting: "neutral",
  done: "success",
  closed: "neutral",
  rejected: "danger",
};

const PRIORITY_VARIANT: Record<string, StatusPillVariant> = {
  low: "neutral",
  normal: "neutral",
  high: "warning",
  urgent: "danger",
  immediate: "danger",
};

type Ticket = {
  id: string;
  number: number;
  title: string | null;
  priority: string;
  status: string;
  sla_due_at: string | null;
  sla_breached: boolean;
};

const BULK_LIMIT_STANDARD = 10;

export function TicketsList({ initialTickets, canApprove }: { initialTickets: Ticket[]; canApprove: boolean }) {
  const t = useTranslations("Tickets");
  const router = useRouter();
  const [tickets] = useState(initialTickets);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkStatus, setBulkStatus] = useState<string>("in_progress");
  const [busy, setBusy] = useState(false);
  const [askResolution, setAskResolution] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ changed: number; failed: { id: string; reason: string }[] } | null>(null);

  const selectedIds = useMemo(() => Array.from(selected), [selected]);
  const overLimit = !canApprove && selectedIds.length > BULK_LIMIT_STANDARD;

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected((prev) => (prev.size === tickets.length ? new Set() : new Set(tickets.map((tk) => tk.id))));
  }

  async function applyBulk(resolution?: Resolution) {
    if (isClosingStatus(bulkStatus) && !resolution) {
      setAskResolution(true);
      return;
    }
    setAskResolution(false);
    setBusy(true);
    setError(null);
    setResult(null);
    const res = await bff<{ changed: { id: string }[]; failed: { id: string; reason: string }[] }>("/api/bff/tickets/bulk-status", {
      method: "POST",
      body: JSON.stringify({ ticket_ids: selectedIds, status: bulkStatus, ...(resolution ? { resolution } : {}) }),
    });
    setBusy(false);
    if (res.ok) {
      setResult({ changed: res.data.changed.length, failed: res.data.failed });
      setSelected(new Set());
      router.refresh();
    } else {
      setError(res.message);
    }
  }

  return (
    <div className="flex flex-col gap-4 pb-20">
      <ul className="flex flex-col gap-2 sm:hidden" data-testid="tickets-cards">
        {tickets.map((tk) => (
          <li key={tk.id} className={ui.cardLink} data-testid="ticket-card">
            <div className="flex items-start gap-2">
              <input
                type="checkbox"
                aria-label={t("selectRow")}
                checked={selected.has(tk.id)}
                onChange={() => toggle(tk.id)}
                className="mt-1"
              />
              <Link href={`/tickets/${tk.id}`} className="flex flex-1 flex-col gap-1.5">
                <span className="flex items-center justify-between gap-2">
                  <span className="min-w-0 break-words font-medium [overflow-wrap:anywhere]">
                    #{tk.number} {tk.title ?? ""}
                  </span>
                </span>
                <span className="flex flex-wrap gap-1.5">
                  <StatusPill variant={PRIORITY_VARIANT[tk.priority] ?? "neutral"} label={t(`priorities.${tk.priority}`)} />
                  <StatusPill variant={STATUS_VARIANT[tk.status] ?? "neutral"} label={t(`statuses.${tk.status}`)} />
                </span>
                {tk.sla_due_at ? (
                  <span className="text-sm text-muted">
                    {formatDateTime(tk.sla_due_at)}
                    {tk.sla_breached ? <span className="ml-1 text-danger-fg">{t("breached")}</span> : null}
                  </span>
                ) : null}
              </Link>
            </div>
          </li>
        ))}
      </ul>
      <div className="hidden overflow-x-auto sm:block">
        <table className="mhvp-table w-full table-fixed sm:table-auto">
          <thead>
            <tr>
              <th>
                <input type="checkbox" aria-label={t("selectAll")} checked={selected.size === tickets.length && tickets.length > 0} onChange={toggleAll} />
              </th>
              <th>{t("number")}</th>
              <th>{t("titleField")}</th>
              <th>{t("priority")}</th>
              <th>{t("status")}</th>
              <th>{t("sla")}</th>
            </tr>
          </thead>
          <tbody>
            {tickets.map((tk) => (
              <tr key={tk.id}>
                <td>
                  <input type="checkbox" aria-label={t("selectRow")} checked={selected.has(tk.id)} onChange={() => toggle(tk.id)} />
                </td>
                <td className="tabular-nums">
                  <Link href={`/tickets/${tk.id}`} className="hover:underline">
                    {tk.number}
                  </Link>
                </td>
                <td className="max-w-[28rem] min-w-0">
                  <Link href={`/tickets/${tk.id}`} className="block max-w-full truncate font-medium hover:underline" title={tk.title ?? ""}>
                    {tk.title ?? ""}
                  </Link>
                </td>
                <td>
                  <StatusPill variant={PRIORITY_VARIANT[tk.priority] ?? "neutral"} label={t(`priorities.${tk.priority}`)} />
                </td>
                <td>
                  <StatusPill variant={STATUS_VARIANT[tk.status] ?? "neutral"} label={t(`statuses.${tk.status}`)} />
                </td>
                <td>
                  {tk.sla_due_at ? formatDateTime(tk.sla_due_at) : ""}
                  {tk.sla_breached ? <span className="ml-1 text-danger-fg">{t("breached")}</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selectedIds.length > 0 ? (
        <div
          className="fixed inset-x-0 bottom-0 z-10 flex flex-col gap-2 border-t border-border bg-surface p-3 shadow-lg sm:flex-row sm:items-center"
          data-testid="bulk-bar"
        >
          <span className="font-medium">
            {selectedIds.length} {t("selected")}
          </span>
          <select className={ui.input} value={bulkStatus} onChange={(e) => {
              setBulkStatus(e.target.value);
              setAskResolution(false);
            }}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`statuses.${s}`)}
              </option>
            ))}
          </select>
          <button type="button" className={ui.primary} disabled={busy || overLimit} onClick={() => void applyBulk()}>
            {t("bulkStatusApply")}
          </button>
          {!canApprove ? <span className="text-xs text-muted">{t("bulkLimitHint")}</span> : null}
          {overLimit ? (
            <span role="alert" className="text-xs text-danger-fg">
              {t("bulkLimitHint")}
            </span>
          ) : null}
        </div>
      ) : null}
      {askResolution && selectedIds.length > 0 ? (
        <div className="fixed inset-x-0 bottom-28 z-20 mx-auto w-full max-w-lg px-3 sm:bottom-20">
          <ResolutionDialog
            status={bulkStatus}
            count={selectedIds.length}
            busy={busy}
            onCancel={() => setAskResolution(false)}
            onConfirm={(resolution) => void applyBulk(resolution)}
          />
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {result ? (
        <p className="text-sm text-muted">
          {t("bulkChanged")}: {result.changed}
          {result.failed.length > 0 ? (
            <>
              {" "}
              · {t("bulkFailed")}: {result.failed.map((f) => f.reason).join("; ")}
            </>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}
