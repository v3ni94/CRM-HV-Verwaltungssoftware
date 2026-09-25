"use client";

import { useTranslations } from "next-intl";

import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

import type { Message } from "./MailWorkspace";

function counterpart(message: Message): string {
  if (message.direction === "in") return message.from_address ?? "";
  return message.to_addresses.join(", ");
}

function statusBadgeClass(status: string): string {
  if (status === "done" || status === "sent") return ui.badgeSuccess;
  if (status === "pending") return ui.badgeWarning;
  if (status === "draft") return ui.badge;
  return ui.badgeGold;
}

export function MailList({
  messages,
  selectedId,
  onSelect,
  loading,
}: {
  messages: Message[] | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
}) {
  const t = useTranslations("Mail");
  if (loading) return <p className="text-sm text-muted">{t("loading")}</p>;
  if (!messages) return null;
  if (messages.length === 0) return <p className="text-sm text-muted">{t("empty")}</p>;
  return (
    <ul className="flex flex-col gap-1.5" data-testid="mail-list">
      {messages.map((message) => {
        const category = typeof message.classification.category === "string" ? message.classification.category : null;
        return (
          <li key={message.id}>
            <button
              type="button"
              onClick={() => onSelect(message.id)}
              className={`w-full rounded-lg border px-3 py-2.5 text-left transition ${
                message.id === selectedId ? "border-gold bg-surface" : "border-border bg-bg hover:border-gold/60"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium">{counterpart(message) || t("noAddress")}</span>
                <span className="shrink-0 text-xs text-subtle">
                  {formatDateTime(message.direction === "in" ? message.received_at : message.sent_at)}
                </span>
              </div>
              <p className="truncate text-sm text-muted">{message.subject || t("noSubject")}</p>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                <span className={statusBadgeClass(message.status)}>{t(`status.${message.status}`)}</span>
                {message.ticket_id ? <span className={ui.badge}>{t("ticketBadge")}</span> : null}
                {category ? <span className={ui.badge}>{category}</span> : null}
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
