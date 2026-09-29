"use client";

import { useEffect, useRef, useState, type MouseEvent } from "react";

import { useTranslations } from "next-intl";

import { StatusChip } from "@/components/ui/StatusChip";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

import { syncHint, type Message } from "./MailWorkspace";

function counterpart(message: Message): string {
  if (message.direction === "in") return message.from_address ?? "";
  return message.to_addresses.join(", ");
}

type BulkResult = { changed: string[]; failed: { id: string; reason: string }[] };

export function MailList({
  messages,
  selectedId,
  onSelect,
  loading,
  onBulkChanged,
}: {
  messages: Message[] | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
  onBulkChanged?: (changed: string[]) => void;
}) {
  const t = useTranslations("Mail");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const anchor = useRef<string | null>(null);

  // Auswahl auf die aktuell geladenen Zeilen beschränken (Filterwechsel, Neuladen).
  useEffect(() => {
    setChecked((prev) => {
      if (prev.size === 0) return prev;
      const visible = new Set((messages ?? []).map((m) => m.id));
      const next = new Set([...prev].filter((id) => visible.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [messages]);

  useEffect(() => {
    if (checked.size === 0) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setChecked(new Set());
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [checked.size]);

  if (loading) return <p className="text-sm text-muted">{t("loading")}</p>;
  if (!messages) return null;
  if (messages.length === 0) return <p className="text-sm text-muted">{t("empty")}</p>;

  const toggle = (id: string) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    anchor.current = id;
  };
  const selectRange = (id: string) => {
    const ids = messages.map((m) => m.id);
    const from = anchor.current ? ids.indexOf(anchor.current) : -1;
    const to = ids.indexOf(id);
    if (from < 0) {
      toggle(id);
      return;
    }
    const [lo, hi] = from < to ? [from, to] : [to, from];
    setChecked((prev) => new Set([...prev, ...ids.slice(lo, hi + 1)]));
  };
  const onRowClick = (event: MouseEvent<HTMLButtonElement>, id: string) => {
    if (event.metaKey || event.ctrlKey) {
      event.preventDefault();
      toggle(id);
    } else if (event.shiftKey) {
      event.preventDefault();
      selectRange(id);
    } else {
      anchor.current = id;
      onSelect(id);
    }
  };
  const allChecked = messages.every((m) => checked.has(m.id));
  const toggleAll = () => setChecked(allChecked ? new Set() : new Set(messages.map((m) => m.id)));

  const markDone = async () => {
    setBulkBusy(true);
    setBulkError(null);
    const res = await bff<BulkResult>("/api/bff/mail/messages/bulk", {
      method: "POST",
      body: JSON.stringify({ ids: [...checked], action: "done" }),
    });
    setBulkBusy(false);
    if (!res.ok) {
      setBulkError(res.message);
      return;
    }
    setChecked(new Set(res.data.failed.map((f) => f.id)));
    if (res.data.failed.length > 0) setBulkError(t("bulkFailed", { count: res.data.failed.length }));
    onBulkChanged?.(res.data.changed);
  };

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-2 px-1 text-xs text-muted">
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={allChecked} onChange={toggleAll} aria-label={t("selectAll")} />
          <span>{t("selectAll")}</span>
        </label>
      </div>
      {checked.size > 0 ? (
        <div
          className="sticky top-[var(--mhvp-header-h)] z-10 flex flex-wrap items-center gap-2 rounded-lg border border-gold bg-surface-2 px-3 py-2"
          role="toolbar"
          aria-label={t("bulkToolbar")}
          data-testid="mail-bulk-bar"
        >
          <span className="text-sm font-medium">{t("selectedCount", { count: checked.size })}</span>
          <button type="button" className={ui.button} disabled={bulkBusy} onClick={() => void markDone()}>
            {t("bulkMarkDone")}
          </button>
          <button type="button" className={ui.button} disabled={bulkBusy} onClick={() => setChecked(new Set())}>
            {t("clearSelection")}
          </button>
        </div>
      ) : null}
      {bulkError ? (
        <p role="alert" className={ui.alert}>
          {bulkError}
        </p>
      ) : null}
      <ul className="flex flex-col gap-1.5" data-testid="mail-list">
        {messages.map((message) => {
          const category = typeof message.classification.category === "string" ? message.classification.category : null;
          const isChecked = checked.has(message.id);
          const inProgress = message.in_progress === true;
          const handler = message.handler_display_name ?? null;
          // Gelbe Kennzeichnung "in Bearbeitung" (Betreiber 27.09.2026): dezenter
          // Warnhintergrund, Auswahl und Markierung behalten den goldenen Rahmen.
          const rowClass = isChecked
            ? `border-gold ${inProgress ? "bg-progress-bg" : "bg-gold/10"}`
            : message.id === selectedId
              ? `border-gold ${inProgress ? "bg-progress-bg" : "bg-surface-2"}`
              : inProgress
                ? "border-gold/60 bg-progress-bg hover:border-gold"
                : "border-border bg-surface hover:border-gold/60";
          return (
            <li key={message.id} className="flex min-w-0 items-start gap-2" data-in-progress={inProgress || undefined}>
              <input
                type="checkbox"
                className="mt-3 shrink-0"
                checked={isChecked}
                onChange={() => toggle(message.id)}
                aria-label={t("selectMessageRow", { subject: message.subject || t("noSubject") })}
              />
              <button
                type="button"
                onClick={(event) => onRowClick(event, message.id)}
                aria-pressed={isChecked || undefined}
                className={`block w-full min-w-0 rounded-lg border px-3 py-2.5 text-left transition ${rowClass}`}
              >
                <div className="flex min-w-0 items-start justify-between gap-2">
                  <span className="min-w-0 truncate text-sm font-medium">{counterpart(message) || t("noAddress")}</span>
                  <span className="flex shrink-0 flex-col items-end gap-0.5 text-xs text-subtle">
                    <span>{formatDateTime(message.direction === "in" ? message.received_at : message.sent_at)}</span>
                    {inProgress ? (
                      <span
                        className="inline-flex items-center gap-1.5 rounded-full bg-progress-label-bg px-2.5 py-0.5 text-xs font-medium text-progress-label-fg"
                        title={handler ? t("inProgressBy", { name: handler }) : t("inProgress")}
                        data-testid="mail-handler"
                      >
                        {handler ?? t("inProgress")}
                      </span>
                    ) : null}
                  </span>
                </div>
                <p className="min-w-0 truncate text-sm text-muted">{message.subject || t("noSubject")}</p>
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                  <StatusChip domain="mail" status={message.status} label={t(`status.${message.status}`)} />
                  {message.ticket_id ? <span className={ui.badge}>{t("ticketBadge")}</span> : null}
                  {message.duplicate_of_id ? (
                    <span className={ui.badge} title={t("duplicateHint")}>
                      {t("duplicateBadge")}
                    </span>
                  ) : null}
                  {category ? <span className={ui.badge}>{category}</span> : null}
                  {message.gmail_sync && message.gmail_sync.state !== "aus" && message.direction === "in" ? (
                    <StatusChip
                      domain="mailSync"
                      status={message.gmail_sync.state}
                      label={t(`sync.${message.gmail_sync.state}`)}
                      explanation={syncHint(message.gmail_sync, t) || undefined}
                    />
                  ) : null}
                  {message.done_source === "gmail" ? (
                    <span className={ui.badge} data-testid="done-from-gmail">
                      {t("doneFromGmail", { address: message.gmail_sync?.copies.find((c) => c.authoritative)?.mailbox_address ?? "" })}
                    </span>
                  ) : null}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
