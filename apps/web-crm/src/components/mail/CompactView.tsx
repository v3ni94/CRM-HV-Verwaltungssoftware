"use client";

import { useEffect, useState, type ReactNode } from "react";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { SafeText } from "@/components/ui/SafeText";
import { ui } from "@/lib/ui";

/** Response of GET /mail/messages/{id}/compact (operator request 30.09.2026). */
export type CompactData = {
  message_id: string;
  thread_count: number;
  summary: { source: "ai" | "excerpt"; text: string; open_points: string[]; model: string | null };
  crm: {
    contact: { id: string; display_name: string } | null;
    property: { id: string; number: string; name: string } | null;
    open_tickets: { count: number; items: { id: string; number: number; title: string; status: string }[] } | null;
    open_items: { count: number; overdue: number; remaining: string } | null;
    recent: { id: string; direction: string; subject: string | null; at: string }[];
  };
  reply: { source: "suggestion" | "preparation" | "template"; text: string };
  can_reply: boolean;
  body_long: boolean;
};

type Draft = { id: string; status: string };

/** Compact block above a mail or a ticket's mail thread: summary, CRM hint and reply
 *  proposal. "Kurz senden" creates the reply draft and submits it through the existing path
 *  (POST reply-draft, POST submit); four eyes rule and re-authentication stay on the server
 *  side approval, this component never sends directly. */
export function CompactView({
  messageId,
  canUpdate,
  onDraftCreated,
}: {
  messageId: string;
  canUpdate: boolean;
  onDraftCreated?: (draft: Draft) => void;
}) {
  const t = useTranslations("MailCompact");
  const [data, setData] = useState<CompactData | null>(null);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    void bff<CompactData>(`/api/bff/mail/messages/${messageId}/compact`).then((res) => {
      if (cancelled) return;
      if (res.ok && res.data && typeof res.data === "object" && "summary" in res.data) {
        setData(res.data);
        setReply(res.data.reply.text);
      } else if (!res.ok) setError(res.message);
    });
    return () => {
      cancelled = true;
    };
  }, [messageId]);

  const summarize = async () => {
    setBusy(true);
    setInfo(null);
    const res = await bff<{ status: string; text?: string; open_points?: string[]; model?: string | null }>(
      `/api/bff/mail/messages/${messageId}/compact/summary`,
      { method: "POST", body: "{}" },
    );
    setBusy(false);
    if (!res.ok) return setError(res.message);
    if (res.data.status === "ready" && data) {
      setData({ ...data, summary: { source: "ai", text: res.data.text ?? "", open_points: res.data.open_points ?? [], model: res.data.model ?? null } });
    } else setInfo(res.data.status === "skipped" ? t("summarySkipped") : t("summaryFailed"));
  };

  const quickSend = async () => {
    setBusy(true);
    setError(null);
    setInfo(null);
    const draft = await bff<Draft>(`/api/bff/mail/messages/${messageId}/reply-draft`, {
      method: "POST",
      body: JSON.stringify({ body: reply }),
    });
    if (!draft.ok) {
      setBusy(false);
      return setError(draft.message);
    }
    const submitted = await bff<Draft>(`/api/bff/mail/messages/${draft.data.id}/submit`, { method: "POST" });
    setBusy(false);
    if (!submitted.ok) {
      onDraftCreated?.(draft.data);
      return setError(submitted.message);
    }
    onDraftCreated?.(submitted.data);
    setInfo(t("quickSent"));
  };

  if (error && !data) return <p className={ui.alert} role="alert">{error}</p>;
  if (!data) return <p className="text-sm text-muted">{t("loading")}</p>;
  const { crm } = data;
  const hasCrm = crm.contact || crm.property || (crm.open_tickets?.count ?? 0) > 0 || (crm.open_items?.count ?? 0) > 0 || crm.recent.length > 0;
  const replySource = { suggestion: t("replySuggestion"), preparation: t("replyPreparation"), template: t("replyTemplate") }[data.reply.source];

  return (
    <section className={`${ui.card} flex min-w-0 flex-col gap-3`} data-testid="mail-compact" aria-label={t("title")}>
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">{t("summary")}</h3>
          <span className="text-xs text-muted">{data.summary.source === "ai" ? t("sourceAi") : t("sourceExcerpt")}</span>
        </div>
        <SafeText className="text-sm" testId="mail-compact-summary">{data.summary.text}</SafeText>
        {data.summary.open_points.length > 0 ? (
          <ul className="list-disc pl-5 text-sm" aria-label={t("openPoints")}>
            {data.summary.open_points.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
        ) : null}
        {canUpdate && data.summary.source === "excerpt" ? (
          <div>
            <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void summarize()}>
              {t("summarize")}
            </button>
          </div>
        ) : null}
      </div>

      <div className="flex flex-col gap-1" data-testid="mail-compact-crm">
        <h3 className="text-sm font-semibold">{t("crm")}</h3>
        {!hasCrm ? <p className="text-sm text-muted">{t("noAssignment")}</p> : null}
        {crm.contact ? (
          <p className="text-sm">
            {t("contact")}: <Link className="underline" href={`/contacts/${crm.contact.id}`}>{crm.contact.display_name}</Link>
          </p>
        ) : null}
        {crm.property ? (
          <p className="text-sm">
            {t("property")}: <Link className="underline" href={`/properties/${crm.property.id}`}>{crm.property.number} {crm.property.name}</Link>
          </p>
        ) : null}
        {crm.open_tickets && crm.open_tickets.count > 0 ? (
          <p className="text-sm">
            {t("openTickets", { count: crm.open_tickets.count })}{" "}
            {crm.open_tickets.items.map((tk) => (
              <Link key={tk.id} className="mr-2 underline" href={`/tickets/${tk.id}`}>#{tk.number}</Link>
            ))}
          </p>
        ) : null}
        {crm.open_items && crm.open_items.count > 0 ? (
          <p className="text-sm">{t("openItems", { count: crm.open_items.count, overdue: crm.open_items.overdue, sum: formatEur(crm.open_items.remaining) })}</p>
        ) : null}
        {crm.recent.length > 0 ? (
          <div className="text-xs text-muted">
            {t("recent")}:{" "}
            {crm.recent.map((r) => (
              <span key={r.id} className="mr-2">{r.direction === "in" ? "←" : "→"} {r.subject ?? ""}</span>
            ))}
          </div>
        ) : null}
      </div>

      {data.can_reply ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{t("reply")}</h3>
            <span className="text-xs text-muted">{replySource}</span>
          </div>
          <textarea className={ui.input} rows={5} value={reply} onChange={(e) => setReply(e.target.value)} aria-label={t("reply")} disabled={!canUpdate} />
          {canUpdate ? (
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className={ui.primary} disabled={busy || !reply.trim()} onClick={() => void quickSend()}>
                {t("quickSend")}
              </button>
              <span className="text-xs text-muted">{t("quickSendHint")}</span>
            </div>
          ) : null}
        </div>
      ) : null}
      {info ? <p className="text-xs text-success-fg" role="status">{info}</p> : null}
      {error ? <p className={ui.alert} role="alert">{error}</p> : null}
    </section>
  );
}

/** Long mail text folded behind "Vollständig anzeigen" (operator request 30.09.2026). */
export function CollapsibleBody({ text, limit = 600, children }: { text: string | null | undefined; limit?: number; children: (shown: string) => ReactNode }) {
  const t = useTranslations("MailCompact");
  const [open, setOpen] = useState(false);
  const full = text ?? "";
  const long = full.length > limit;
  const shown = long && !open ? `${full.slice(0, limit).trimEnd()} …` : full;
  return (
    <div className="flex min-w-0 flex-col gap-1">
      {children(shown)}
      {long ? (
        <div>
          <button type="button" className={ui.buttonSm} onClick={() => setOpen((v) => !v)}>
            {open ? t("showLess") : t("showFull")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
