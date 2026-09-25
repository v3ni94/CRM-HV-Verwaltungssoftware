"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { useTranslations } from "next-intl";

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
  body: string | null;
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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
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

  useEffect(() => {
    if (!canApprove) return;
    void bff<Message[]>(`/api/bff/mail/messages?${queryFor("pending", "", "", "")}`).then((res) => {
      if (res.ok) setPendingCount(res.data.length);
    });
  }, [canApprove, tab, status, q]);

  const refresh = () => load(tab, status, mailboxId, q);

  const selected = useMemo(() => messages?.find((m) => m.id === selectedId) ?? null, [messages, selectedId]);

  const onUpdated = (next: Message) => {
    setMessages((prev) => (prev ? prev.map((m) => (m.id === next.id ? next : m)) : prev));
    // A status change can move the message out of the current tab's filter (e.g. submit,
    // approve, mark done); the list is reloaded so it reflects that.
    refresh();
    if (canApprove) {
      void bff<Message[]>(`/api/bff/mail/messages?${queryFor("pending", "", "", "")}`).then((res) => {
        if (res.ok) setPendingCount(res.data.length);
      });
    }
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
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <MailList messages={messages} selectedId={selectedId} onSelect={setSelectedId} loading={busy && messages === null} />
        <MailDetail message={selected} canApprove={canApprove} canReadMembers={canReadMembers} onUpdated={onUpdated} onCreated={onUpdated} />
      </div>
    </div>
  );
}
