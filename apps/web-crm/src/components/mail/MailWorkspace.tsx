"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { Pagination } from "@/components/ui/Pagination";
import type { Preparation } from "@/lib/ai";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { MailDetail } from "./MailDetail";
import { MailList } from "./MailList";

// Seitengröße der Nachrichtenliste (Betreibermeldung 27.09.2026): echte Seitensteuerung statt
// "Seite 2, 3 zeigt weiter Seite 1"; GET /mail/messages meldet die Gesamtzahl in X-Total-Count.
const PAGE_SIZE = 50;

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
  // Gmail archive tracking (operator 27.09.2026): pending, archived, skipped, failed,
  // scope_missing; null before the first request.
  archive_status?: string | null;
  archive_error?: string | null;
  archive_attempted_at?: string | null;
  archived_at?: string | null;
};

export type Mailbox = { id: string; address: string; archive_scope_missing?: boolean };

type Tab = "inbox" | "drafts" | "pending" | "sent";

const TABS: Tab[] = ["inbox", "drafts", "pending", "sent"];

const INBOX_STATUSES = ["new", "assigned", "done"] as const;

function queryFor(
  tab: Tab,
  status: string,
  mailboxId: string,
  q: string,
  showClosed = false,
  page = 1,
): string {
  const params = new URLSearchParams();
  if (tab === "inbox") {
    params.set("direction", "in");
    if (status) params.set("status", status);
    // Operator 26.09.2026: done mails (or mails of closed tickets) stay hidden unless shown.
    else if (showClosed) params.set("include_closed", "true");
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
  params.set("page", String(page));
  params.set("page_size", String(PAGE_SIZE));
  return params.toString();
}

export function MailWorkspace({
  canApprove,
  canReadMembers,
}: {
  canApprove: boolean;
  canReadMembers: boolean;
}) {
  const t = useTranslations("Mail");
  // Reiterwahl per URL (?tab=), vorwählbar und beim Wechsel geschrieben (offener Restpunkt,
  // additiv neben dem Paging der Nachrichtenliste).
  const [tab, setTab] = useState<Tab>(() => {
    if (typeof window === "undefined") return "inbox";
    const fromUrl = new URLSearchParams(window.location.search).get("tab");
    return fromUrl && TABS.includes(fromUrl as Tab) ? (fromUrl as Tab) : "inbox";
  });
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [queryText, setQueryText] = useState("");
  const [mailboxId, setMailboxId] = useState("");
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [messages, setMessages] = useState<Message[] | null>(null);
  // Deep link from the ticket mail thread (operator 26.09.2026): /mail?message=<id>.
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    typeof window === "undefined"
      ? null
      : new URLSearchParams(window.location.search).get("message"),
  );
  // Operator 26.09.2026: "Erledigte anzeigen", mirrored in the URL as erledigt=1.
  const [showClosed, setShowClosed] = useState<boolean>(() =>
    typeof window === "undefined"
      ? false
      : new URLSearchParams(window.location.search).get("erledigt") === "1",
  );
  const [pendingCount, setPendingCount] = useState(0);
  const [detail, setDetail] = useState<Message | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Seite der Nachrichtenliste, im URL-Zustand als ?seite= (Betreibermeldung 27.09.2026).
  const [page, setPage] = useState<number>(() => {
    if (typeof window === "undefined") return 1;
    const raw = Number.parseInt(new URLSearchParams(window.location.search).get("seite") ?? "1", 10);
    return Number.isFinite(raw) && raw > 0 ? raw : 1;
  });
  const [totalCount, setTotalCount] = useState(0);

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
    (
      activeTab: Tab,
      activeStatus: string,
      activeMailbox: string,
      activeQ: string,
      activeShowClosed: boolean,
      activePage: number,
    ) => {
      setBusy(true);
      setError(null);
      void bff<Message[]>(
        `/api/bff/mail/messages?${queryFor(activeTab, activeStatus, activeMailbox, activeQ, activeShowClosed, activePage)}`,
      ).then((res) => {
        setBusy(false);
        if (res.ok) {
          setMessages(res.data);
          setTotalCount(res.totalCount ?? res.data.length);
          setSelectedId((prev) =>
            prev && res.data.some((m) => m.id === prev)
              ? prev
              : (res.data[0]?.id ?? null),
          );
        } else {
          setMessages([]);
          setTotalCount(0);
          setError(res.message);
        }
      });
    },
    [],
  );

  useEffect(() => {
    load(tab, status, mailboxId, q, showClosed, page);
  }, [tab, status, mailboxId, q, showClosed, page, load]);

  // Filterwechsel setzt auf Seite 1 zurück (Betreibermeldung 27.09.2026); der Seitenwechsel
  // selbst löst load() über den Effekt oben aus. Der erste Durchlauf beim Einhängen darf eine
  // Seite aus dem URL-Zustand (?seite=) nicht überschreiben.
  const filtersMounted = useRef(false);
  useEffect(() => {
    if (!filtersMounted.current) {
      filtersMounted.current = true;
      return;
    }
    setPage(1);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.delete("seite");
      window.history.replaceState(null, "", url.toString());
    }
  }, [tab, status, mailboxId, q, showClosed]);

  const changePage = (next: number) => {
    setPage(next);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      if (next > 1) url.searchParams.set("seite", String(next));
      else url.searchParams.delete("seite");
      window.history.replaceState(null, "", url.toString());
      window.scrollTo({ top: 0 });
    }
  };

  // Badge "Freigaben": count endpoint instead of loading the whole pending list (M3).
  const loadPendingCount = useCallback(() => {
    if (!canApprove) return;
    void bff<{ count: number }>(
      `/api/bff/mail/messages/count?${queryFor("pending", "", "", "")}`,
    ).then((res) => {
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

  const refresh = () => load(tab, status, mailboxId, q, showClosed, page);

  const toggleClosed = (next: boolean) => {
    setShowClosed(next);
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    if (next) url.searchParams.set("erledigt", "1");
    else url.searchParams.delete("erledigt");
    window.history.replaceState(null, "", url.toString());
  };

  const selected = useMemo(() => {
    if (!selectedId) return null;
    if (detail && detail.id === selectedId) return detail;
    return messages?.find((m) => m.id === selectedId) ?? null;
  }, [messages, selectedId, detail]);

  const onUpdated = (next: Message) => {
    setMessages((prev) =>
      prev ? prev.map((m) => (m.id === next.id ? next : m)) : prev,
    );
    if (next.id === selectedId) setDetail(next);
    // A status change can move the message out of the current tab's filter (e.g. submit,
    // approve, mark done); the list is reloaded so it reflects that.
    refresh();
    loadPendingCount();
  };

  const onBulkChanged = (changed: string[]) => {
    if (changed.length === 0) return;
    if (selectedId && changed.includes(selectedId)) setDetail(null);
    refresh();
    loadPendingCount();
  };

  const tabs: { key: Tab; label: string; badge?: number }[] = [
    { key: "inbox", label: t("tabs.inbox") },
    { key: "drafts", label: t("tabs.drafts") },
    ...(canApprove
      ? [
          {
            key: "pending" as Tab,
            label: t("tabs.pending"),
            badge: pendingCount,
          },
        ]
      : []),
    { key: "sent", label: t("tabs.sent") },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div
        className="flex flex-wrap items-center gap-2 border-b border-border-soft pb-2"
        role="tablist"
      >
        {tabs.map((tabItem) => (
          <button
            key={tabItem.key}
            type="button"
            role="tab"
            aria-selected={tab === tabItem.key}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
              tab === tabItem.key
                ? "bg-accent text-accent-fg"
                : "text-muted hover:bg-surface"
            }`}
            onClick={() => {
              setTab(tabItem.key);
              setStatus("");
              if (typeof window !== "undefined") {
                const url = new URL(window.location.href);
                url.searchParams.set("tab", tabItem.key);
                window.history.replaceState(null, "", url.toString());
              }
            }}
          >
            {tabItem.label}
            {tabItem.badge ? (
              <span className="ml-1.5 rounded-full bg-danger-bg px-1.5 text-xs text-danger-fg">
                {tabItem.badge}
              </span>
            ) : null}
          </button>
        ))}
      </div>
      <div
        className="flex flex-wrap items-center gap-2"
        data-testid="mail-filters"
      >
        {tab === "inbox" ? (
          <select
            className={`${ui.input} w-auto min-w-[10rem]`}
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">{t("statusFilter.all")}</option>
            {INBOX_STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`status.${s}`)}
              </option>
            ))}
          </select>
        ) : null}
        {tab === "inbox" && !status ? (
          <label className="inline-flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={showClosed}
              onChange={(e) => toggleClosed(e.target.checked)}
              data-testid="toggle-closed"
            />
            {t("showClosed")}
          </label>
        ) : null}
        {mailboxes.length > 0 ? (
          <select
            className={`${ui.input} w-auto min-w-[12rem]`}
            value={mailboxId}
            onChange={(e) => setMailboxId(e.target.value)}
          >
            <option value="">{t("mailboxFilter.all")}</option>
            {mailboxes.map((m) => (
              <option key={m.id} value={m.id}>
                {m.address}
              </option>
            ))}
          </select>
        ) : null}
        <input
          className={`${ui.input} w-full sm:w-auto sm:min-w-[14rem] sm:flex-1`}
          placeholder={t("searchPlaceholder")}
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
        />
        <button
          type="button"
          className={`${ui.button} sm:ml-auto`}
          disabled={busy}
          onClick={refresh}
        >
          {t("refresh")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {mailboxes.some((m) => m.archive_scope_missing) ? (
        <p role="status" className={ui.warning} data-testid="archive-scope-banner">
          {t("archiveScopeMissing", {
            addresses: mailboxes.filter((m) => m.archive_scope_missing).map((m) => m.address).join(", "),
          })}{" "}
          <Link href="/einstellungen/postfaecher" className="font-medium underline">
            {t("archiveScopeLink")}
          </Link>
        </p>
      ) : null}
      <div className="grid min-w-0 gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className={`min-w-0 flex flex-col gap-3 ${selectedId ? "hidden md:flex" : ""}`}>
          <MailList
            messages={messages}
            selectedId={selectedId}
            onSelect={setSelectedId}
            loading={busy && messages === null}
            onBulkChanged={onBulkChanged}
          />
          {messages && messages.length > 0 ? (
            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={totalCount}
              shown={messages.length}
              control={{ kind: "button", onChange: changePage, disabled: busy }}
              labels={{
                label: t("pagination.label"),
                range: (from, to, total) => t("pagination.range", { from, to, total }),
                page: (currentPage, pages) => t("pagination.page", { page: currentPage, pages }),
                prev: t("pagination.prev"),
                next: t("pagination.next"),
              }}
              testId="mail-pagination"
            />
          ) : null}
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
          <MailDetail
            message={selected}
            canApprove={canApprove}
            canReadMembers={canReadMembers}
            onUpdated={onUpdated}
            onCreated={onUpdated}
          />
        </div>
      </div>
    </div>
  );
}
