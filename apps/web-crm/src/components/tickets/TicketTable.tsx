"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

import { STATUSES } from "./TicketForms";

export type TicketRow = {
  id: string;
  number: number;
  title: string;
  priority: string;
  status: string;
  sla_due_at: string | null;
  sla_breached: boolean;
};

/** Zulässige Ziele der Sammelaktion (new ist kein sinnvolles Ziel). */
const BULK_TARGETS = STATUSES.filter((s) => s !== "new");

export function TicketTable({ rows }: { rows: TicketRow[] }) {
  const t = useTranslations("Tickets");
  const router = useRouter();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [target, setTarget] = useState<string>("done");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const allSelected = rows.length > 0 && selected.size === rows.length;

  const apply = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    const res = await bff<{ updated: number; skipped: { id: string; reason: string }[] }>(
      "/api/bff/tickets/bulk-status",
      { method: "POST", body: JSON.stringify({ ticket_ids: [...selected], status: target }) },
    );
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setSelected(new Set());
    setNotice(
      res.data.skipped.length
        ? t("bulk.partial", { updated: res.data.updated, skipped: res.data.skipped.length })
        : t("bulk.done", { updated: res.data.updated }),
    );
    router.refresh();
  };

  return (
    <div className="flex flex-col gap-2">
      {selected.size > 0 ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-gold/50 bg-gold-tint px-3 py-2 text-sm">
          <span className="font-medium">{t("bulk.selected", { count: selected.size })}</span>
          <label className="flex items-center gap-1.5">
            <span className={ui.label}>{t("bulk.target")}</span>
            <select className={ui.input} value={target} onChange={(e) => setTarget(e.target.value)}>
              {BULK_TARGETS.map((s) => (
                <option key={s} value={s}>
                  {t(`statuses.${s}`)}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className={ui.primary} disabled={busy} onClick={apply}>
            {t("bulk.apply")}
          </button>
          <button type="button" className={ui.button} onClick={() => setSelected(new Set())}>
            {t("bulk.clear")}
          </button>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {notice ? <p className={ui.notice}>{notice}</p> : null}
      <table className="w-full border-collapse text-sm" data-testid="ticket-table">
        <thead className="border-b border-border text-left text-xs text-muted">
          <tr>
            <th className="w-8 py-1.5 pr-2">
              <input
                type="checkbox"
                aria-label={t("bulk.selectAll")}
                checked={allSelected}
                onChange={() => setSelected(allSelected ? new Set() : new Set(rows.map((r) => r.id)))}
              />
            </th>
            <th className="py-1.5 pr-3 font-medium">{t("number")}</th>
            <th className="py-1.5 pr-3 font-medium">{t("titleField")}</th>
            <th className="py-1.5 pr-3 font-medium">{t("priority")}</th>
            <th className="py-1.5 pr-3 font-medium">{t("status")}</th>
            <th className="py-1.5 font-medium">{t("sla")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((tk) => (
            <tr key={tk.id} className="border-b border-border">
              <td className="py-1.5 pr-2">
                <input
                  type="checkbox"
                  aria-label={t("bulk.selectOne", { number: tk.number })}
                  checked={selected.has(tk.id)}
                  onChange={() => toggle(tk.id)}
                />
              </td>
              <td className="py-1.5 pr-3 tabular-nums">{tk.number}</td>
              <td className="py-1.5 pr-3">
                <Link href={`/tickets/${tk.id}`} className="font-medium hover:underline">
                  {tk.title}
                </Link>
              </td>
              <td className="py-1.5 pr-3">{t(`priorities.${tk.priority}`)}</td>
              <td className="py-1.5 pr-3">{t(`statuses.${tk.status}`)}</td>
              <td className="py-1.5">
                {tk.sla_due_at ? formatDateTime(tk.sla_due_at) : ""}
                {tk.sla_breached ? <span className="ml-1 text-danger-fg">{t("breached")}</span> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
