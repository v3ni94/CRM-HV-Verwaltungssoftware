"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { useTranslations } from "next-intl";

import type { Preparation } from "@/lib/ai";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { MailDetail } from "./MailDetail";
import { MailList } from "./MailList";

export type Message = {
  id: string;
  channel: string;
  direction: "in" | "out";
  status: string;
  from_address: string | null;
  to_addresses: string[];
  subject: string | null;
  // The list delivers only `body_preview` (200 characters, review 26.09.2026, M3); the
  // detail endpoint fills `body` and `body_html`.
  body?: string | null;
  body_html?: string | null;
  body_preview?: string | null;
  received_at: string | null;
  sent_at: string | null;
  contact_id: string | null;
  property_id: string | null;
  ticket_id: string | null;
  thread_id: string | null;
  document_id: string | null;
  attachment_document_ids: string[];
  classification: Record<string, unknown>;
  appointment_suggestions: unknown[];
  created_by: string | null;
  mailbox_id: string | null;
  submitted_by: string | null;
  submitted_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  rejection_note: string | null;
  suggestion: {
    category?: string | null;
    urgency?: "low" | "normal" | "high" | "emergency" | null;
    summary?: string;
    property_number?: string | null;
    contact_name?: string | null;
    reply_draft?: string | null;
    playbook_id?: string | null;
    playbook_score?: number | null;
    reason?: string;
    preparation?: Preparation;
  };
  suggestion_status: "none" | "pending" | "ready" | "failed" | "skipped";
};

export type Mailbox = { id: string; address: string };

type Tab = "inbox" | "drafts" | "pending" | "sent";

const INBOX_STATUSES = ["new", "assigned", "done"] as const;

function queryFor(tab: Tab, status: string, mailboxId: string, q: string): string {
  const params = new URLSearchParams();
  if (tab === "inbox") {
    params.set("direction", "in");
    if (status) params.set("status", status);
  } else if (tab === "drafts") {
    params.set("direction", "out");
    params.set("status", "draft");
  } else if (tab === "pending") {
    params.set("direction", "out");
    params.set("status", "pending");
  } else {
    params.set("direction", "out");
    params.set("status", "sent");
  }
  if (mailboxId) params.set("mailbox_id", mailboxId);
  if (q.trim()) params.set("q", q.trim());
  return params.toString();
}

export function MailWorkspace({ canApprove, canReadMembers }: { canApprove: boolean; canReadMembers: boolean }) {
  const t = useTranslations("Mail");
  const [tab, setTab] = useState<Tab>("inbox");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [queryText, setQueryText] = useState("");
  const [mailboxId, setMailboxId] = useState("");
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [messages, setMessages] = useState<Message[] | null>(null);
  // Deep link from the ticket mail thread (operator 26.09.2026): /mail?message=<id>.
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("message"),
  );
  const [pendingCount, setPendingCount] = useState(0);
  const [detail, setDetail] = useState<Message | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void bff<Mailbox[]>("/api/bff/mail/mailboxes").then((res) => {
      if (res.ok) setMailboxes(res.data);
    });
  }, []);

  useEffect(() => {
    const handle = setTimeout(() => setQ(queryText), 300);
    return () => clearTimeout(handle);
  }, [queryText]);

  const load = useCallback(
    (activeTab: Tab, activeStatus: string, activeMailbox: string, activeQ: string) => {
      setBusy(true);
      setError(null);
      void bff<Message[]>(`/api/bff/mail/messages?${queryFor(activeTab, activeStatus, activeMailbox, activeQ)}`).then((res) => {
        setBusy(false);
        if (res.ok) {
          setMessages(res.data);
          setSelectedId((prev) => (prev && res.data.some((m) => m.id === prev) ? prev : (res.data[0]?.id ?? null)));
        } else {
          setMessages([]);
          setError(res.message);
        }
      });
    },
    [],
  );

  useEffect(() => {
    load(tab, status, mailboxId, q);
  }, [tab, status, mailboxId, q, load]);

  // Badge "Freigaben": count endpoint instead of loading the whole pending list (M3).
  const loadPendingCount = useCallback(() => {
    if (!canApprove) return;
    void bff<{ count: number }>(`/api/bff/mail/messages/count?${queryFor("pending", "", "", "")}`).then((res) => {
      if (res.ok) setPendingCount(res.data.count);
    });
  }, [canApprove]);

  useEffect(() => {
    loadPendingCount();
  }, [loadPendingCount, tab, status, q]);

  // The list carries only a preview; the selected message is loaded with its full text.
  useEffect(() => {
    setDetail(null);
    if (!selectedId) return;
    let active = true;
    void bff<Message>(`/api/bff/mail/messages/${selectedId}`).then((res) => {
      if (active && res.ok) setDetail(res.data);
    });
    return () => {
      active = false;
    };
  }, [selectedId]);

  const refresh = () => load(tab, status, mailboxId, q);

  const selected = useMemo(() => {
    if (!selectedId) return null;
    if (detail && detail.id === selectedId) return detail;
    return messages?.find((m) => m.id === selectedId) ?? null;
  }, [messages, selectedId, detail]);

  const onUpdated = (next: Message) => {
    setMessages((prev) => (prev ? prev.map((m) => (m.id === next.id ? next : m)) : prev));
    if (next.id === selectedId) setDetail(next);
    // A status change can move the message out of the current tab's filter (e.g. submit,
    // approve, mark done); the list is reloaded so it reflects that.
    refresh();
    loadPendingCount();
  };

  const tabs: { key: Tab; label: string; badge?: number }[] = [
    { key: "inbox", label: t("tabs.inbox") },
    { key: "drafts", label: t("tabs.drafts") },
    ...(canApprove ? [{ key: "pending" as Tab, label: t("tabs.pending"), badge: pendingCount }] : []),
    { key: "sent", label: t("tabs.sent") },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 border-b border-border-soft pb-2">
        {tabs.map((tabItem) => (
          <button
            key={tabItem.key}
            type="button"
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
              tab === tabItem.key ? "bg-accent text-accent-fg" : "text-muted hover:bg-surface"
            }`}
            onClick={() => {
              setTab(tabItem.key);
              setStatus("");
            }}
          >
            {tabItem.label}
            {tabItem.badge ? <span className="ml-1.5 rounded-full bg-danger-bg px-1.5 text-xs text-danger-fg">{tabItem.badge}</span> : null}
          </button>
        ))}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {tab === "inbox" ? (
            <select className={ui.input} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">{t("statusFilter.all")}</option>
              {INBOX_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {t(`status.${s}`)}
                </option>
              ))}
            </select>
          ) : null}
          {mailboxes.length > 0 ? (
            <select className={ui.input} value={mailboxId} onChange={(e) => setMailboxId(e.target.value)}>
              <option value="">{t("mailboxFilter.all")}</option>
              {mailboxes.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.address}
                </option>
              ))}
            </select>
          ) : null}
          <input
            className={ui.input}
            placeholder={t("searchPlaceholder")}
            value={queryText}
            onChange={(e) => setQueryText(e.target.value)}
          />
          <button type="button" className={ui.button} disabled={busy} onClick={refresh}>
            {t("refresh")}
          </button>
        </div>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="grid min-w-0 gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className={`min-w-0 ${selectedId ? "hidden md:block" : ""}`}>
          <MailList messages={messages} selectedId={selectedId} onSelect={setSelectedId} loading={busy && messages === null} />
        </div>
        <div className={`min-w-0 ${selectedId ? "" : "hidden md:block"}`}>
          {selectedId ? (
            <button
              type="button"
              className={`${ui.button} mb-3 md:hidden`}
              onClick={() => setSelectedId(null)}
            >
              {t("backToList")}
            </button>
          ) : null}
          <MailDetail message={selected} canApprove={canApprove} canReadMembers={canReadMembers} onUpdated={onUpdated} onCreated={onUpdated} />
        </div>
      </div>
    </div>
  );
}
