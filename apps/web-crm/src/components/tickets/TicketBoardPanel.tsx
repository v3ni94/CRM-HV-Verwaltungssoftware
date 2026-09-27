"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDateTime, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Beiratsbeteiligung am Ticket (M19-02, docs/rules/M19-02-beiratsbeteiligung.md): submissions
 *  to the Verwaltungsbeirat for information or an opinion, the answers (portal or recorded in
 *  the CRM) and the protocol. Shown only for WEG properties. The vote is information: the
 *  release of a work order stays with the management, no payment follows. */

export type BoardMember = { contact_id: string; name: string | null };
export type BoardVote = {
  id: string;
  contact_id: string;
  contact_name: string | null;
  vote: "approve" | "reject" | "comment";
  comment: string | null;
  source: "portal" | "crm";
  created_at: string;
};
export type BoardSubmission = {
  id: string;
  kind: "info" | "consent";
  title: string;
  note: string | null;
  amount: string | null;
  due_on: string;
  overdue: boolean;
  status: "open" | "closed";
  work_order_id: string | null;
  members: BoardMember[];
  votes: BoardVote[];
  tally: { approve: number; reject: number; comment: number };
  closed_at: string | null;
  closing_note: string | null;
  created_at: string;
};
export type BoardOverview = {
  is_hoa: boolean;
  members: BoardMember[];
  recommendation: { recommended: boolean; by_category: boolean; by_amount: boolean; kind: "info" | "consent"; deadline_days: number };
  submissions: BoardSubmission[];
};
export type BoardPolicy = {
  threshold_amount: string | null;
  categories: string[];
  default_kind: "info" | "consent";
  default_deadline_days: number;
};

function isoDatePlusDays(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function SubmissionForm({
  ticketId,
  overview,
  workOrders,
  onDone,
  onCancel,
}: {
  ticketId: string;
  overview: BoardOverview;
  workOrders: { id: string; description: string }[];
  onDone: (s: BoardSubmission) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("TicketBoard");
  const [kind, setKind] = useState<"info" | "consent">(overview.recommendation.kind);
  const [dueOn, setDueOn] = useState(isoDatePlusDays(overview.recommendation.deadline_days));
  const [workOrderId, setWorkOrderId] = useState<string>("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<BoardSubmission>(`/api/bff/tickets/${ticketId}/board-submissions`, {
      method: "POST",
      body: JSON.stringify({ kind, due_on: dueOn, work_order_id: workOrderId || null, note: note.trim() || null }),
    });
    setBusy(false);
    if (res.ok) onDone(res.data);
    else setError(res.message);
  };
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border-soft p-3">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("kind")}</span>
          <select className={ui.input} value={kind} onChange={(e) => setKind(e.target.value as "info" | "consent")}>
            <option value="info">{t("kinds.info")}</option>
            <option value="consent">{t("kinds.consent")}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("dueOn")}</span>
          <input type="date" className={ui.input} value={dueOn} onChange={(e) => setDueOn(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("workOrder")}</span>
          <select className={ui.input} value={workOrderId} onChange={(e) => setWorkOrderId(e.target.value)}>
            <option value="">{t("noWorkOrder")}</option>
            {workOrders.map((o) => (
              <option key={o.id} value={o.id}>
                {o.description}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("note")}</span>
        <textarea className={ui.input} rows={2} maxLength={4000} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="flex gap-2">
        <button type="button" className={ui.primary} disabled={busy || !dueOn} onClick={() => void submit()}>
          {t("submit")}
        </button>
        <button type="button" className={ui.button} onClick={onCancel}>
          {t("cancel")}
        </button>
      </div>
    </div>
  );
}

function RecordVoteForm({ submission, onDone }: { submission: BoardSubmission; onDone: (s: BoardSubmission) => void }) {
  const t = useTranslations("TicketBoard");
  const [contactId, setContactId] = useState(submission.members[0]?.contact_id ?? "");
  const [vote, setVote] = useState<"approve" | "reject" | "comment">("approve");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    setError(null);
    const res = await bff<BoardSubmission>(`/api/bff/tickets/board/submissions/${submission.id}/votes`, {
      method: "POST",
      body: JSON.stringify({ contact_id: contactId, vote, comment: comment.trim() || null }),
    });
    if (res.ok) {
      setComment("");
      onDone(res.data);
    } else setError(res.message);
  };
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("member")}</span>
        <select className={ui.input} value={contactId} onChange={(e) => setContactId(e.target.value)}>
          {submission.members.map((m) => (
            <option key={m.contact_id} value={m.contact_id}>
              {m.name ?? m.contact_id}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("record")}</span>
        <select className={ui.input} value={vote} onChange={(e) => setVote(e.target.value as typeof vote)}>
          <option value="approve">{t("vote.approve")}</option>
          <option value="reject">{t("vote.reject")}</option>
          <option value="comment">{t("vote.comment")}</option>
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("comment")}</span>
        <input className={ui.input} value={comment} maxLength={4000} onChange={(e) => setComment(e.target.value)} />
      </label>
      <button type="button" className={ui.buttonSm} disabled={!contactId} onClick={() => void save()}>
        {t("save")}
      </button>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

function PolicyForm({ onSaved }: { onSaved: () => void }) {
  const t = useTranslations("TicketBoard");
  const [policy, setPolicy] = useState<BoardPolicy | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void bff<BoardPolicy>("/api/bff/tickets/board/policy").then((res) => {
      if (res.ok) setPolicy(res.data);
    });
  }, []);
  if (!policy) return null;
  const save = async () => {
    setError(null);
    setNotice(null);
    const res = await bff<BoardPolicy>("/api/bff/tickets/board/policy", { method: "PUT", body: JSON.stringify(policy) });
    if (res.ok) {
      setPolicy(res.data);
      setNotice(t("policySaved"));
      onSaved();
    } else setError(res.message);
  };
  return (
    <details className="rounded-md border border-border-soft p-3">
      <summary className="cursor-pointer text-sm font-medium">{t("policy")}</summary>
      <p className={ui.help}>{t("policyHint")}</p>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("threshold")}</span>
          <input
            className={ui.input}
            inputMode="decimal"
            value={policy.threshold_amount ?? ""}
            onChange={(e) => setPolicy({ ...policy, threshold_amount: e.target.value.replace(",", ".") || null })}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("categories")}</span>
          <input
            className={ui.input}
            value={policy.categories.join(", ")}
            onChange={(e) =>
              setPolicy({ ...policy, categories: e.target.value.split(",").map((c) => c.trim()).filter(Boolean) })
            }
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("defaultKind")}</span>
          <select className={ui.input} value={policy.default_kind} onChange={(e) => setPolicy({ ...policy, default_kind: e.target.value as "info" | "consent" })}>
            <option value="info">{t("kinds.info")}</option>
            <option value="consent">{t("kinds.consent")}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("deadlineDays")}</span>
          <input
            type="number"
            min={1}
            max={90}
            className={ui.input}
            value={policy.default_deadline_days}
            onChange={(e) => setPolicy({ ...policy, default_deadline_days: Number(e.target.value) || 14 })}
          />
        </label>
        <button type="button" className={ui.buttonSm} onClick={() => void save()}>
          {t("save")}
        </button>
      </div>
      {notice ? (
        <p role="status" className={ui.success}>
          {notice}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </details>
  );
}

export function TicketBoardPanel({
  ticketId,
  workOrders,
  canSubmit,
  canManagePolicy,
}: {
  ticketId: string;
  workOrders: { id: string; description: string }[];
  canSubmit: boolean;
  canManagePolicy: boolean;
}) {
  const t = useTranslations("TicketBoard");
  const [overview, setOverview] = useState<BoardOverview | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<BoardOverview>(`/api/bff/tickets/${ticketId}/board-submissions`);
    if (res.ok) setOverview(res.data);
    else setError(res.message);
  }, [ticketId]);
  useEffect(() => {
    void load();
  }, [load]);

  if (!overview || !overview.is_hoa) return null;
  const replace = (s: BoardSubmission) =>
    setOverview((prev) => (prev ? { ...prev, submissions: prev.submissions.map((x) => (x.id === s.id ? s : x)) } : prev));
  const close = async (s: BoardSubmission) => {
    const note = typeof window !== "undefined" ? window.prompt(t("closingNote")) : null;
    if (note === null) return;
    const res = await bff<BoardSubmission>(`/api/bff/tickets/board/submissions/${s.id}/close`, {
      method: "POST",
      body: JSON.stringify({ closing_note: note.trim() || null }),
    });
    if (res.ok) replace(res.data);
    else setError(res.message);
  };
  const reason = overview.recommendation.by_category && overview.recommendation.by_amount
    ? t("reasonBoth")
    : overview.recommendation.by_amount
      ? t("reasonAmount")
      : t("reasonCategory");

  return (
    <section className="flex min-w-0 flex-col gap-2" aria-labelledby="ticket-board-title">
      <h2 id="ticket-board-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className={ui.help}>{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <p className="text-sm">
        <span className={ui.label}>{t("members")}</span>{" "}
        {overview.members.length === 0 ? (
          <span className={ui.badgeWarning}>{t("noMembers")}</span>
        ) : (
          overview.members.map((m) => (
            <span key={m.contact_id} className={`${ui.badge} mr-1`}>
              {m.name ?? m.contact_id}
            </span>
          ))
        )}
      </p>
      {overview.recommendation.recommended ? <p className={ui.info}>{t("recommended", { reason })}</p> : null}
      {canSubmit && !creating && overview.members.length > 0 ? (
        <div>
          <button type="button" className={ui.button} onClick={() => setCreating(true)}>
            {t("new")}
          </button>
        </div>
      ) : null}
      {creating ? (
        <SubmissionForm
          ticketId={ticketId}
          overview={overview}
          workOrders={workOrders}
          onCancel={() => setCreating(false)}
          onDone={(s) => {
            setCreating(false);
            setOverview((prev) => (prev ? { ...prev, submissions: [s, ...prev.submissions] } : prev));
          }}
        />
      ) : null}
      {overview.submissions.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {overview.submissions.map((s) => (
            <li key={s.id} className={`${ui.card} flex flex-col gap-2`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className={ui.badgeGold}>{t(`kinds.${s.kind}`)}</span>
                <span className={s.status === "open" ? ui.badgeInfo : ui.badge}>{t(`status.${s.status}`)}</span>
                {s.overdue ? <span className={ui.badgeWarning}>{t("overdue")}</span> : null}
                <span className="text-xs text-muted">
                  {t("dueOn")} {formatDate(s.due_on)}
                </span>
                {s.amount ? <span className="text-xs text-muted">{formatEur(s.amount)}</span> : null}
              </div>
              {s.note ? <p className="text-sm">{s.note}</p> : null}
              <p className="text-xs text-muted">{t("tally", s.tally)}</p>
              <div>
                <span className={ui.label}>{t("votes")}</span>
                {s.votes.length === 0 ? (
                  <p className="text-sm text-muted">{t("noVotes")}</p>
                ) : (
                  <ul className="flex flex-col gap-1 text-sm">
                    {s.votes.map((v) => (
                      <li key={v.id}>
                        <span className="font-medium">{v.contact_name ?? v.contact_id}</span>: {t(`vote.${v.vote}`)}
                        {v.comment ? ` (${v.comment})` : ""} <span className="text-xs text-muted">
                          {formatDateTime(v.created_at)}, {t(`source.${v.source}`)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {s.status === "closed" ? (
                <p className="text-xs text-muted">
                  {t("closed", { date: formatDateTime(s.closed_at) })}
                  {s.closing_note ? `: ${s.closing_note}` : ""}
                </p>
              ) : canSubmit ? (
                <div className="flex flex-col gap-2">
                  <RecordVoteForm submission={s} onDone={replace} />
                  <div>
                    <button type="button" className={ui.buttonSm} onClick={() => void close(s)}>
                      {t("close")}
                    </button>
                  </div>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {canManagePolicy ? <PolicyForm onSaved={() => void load()} /> : null}
    </section>
  );
}
