"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import type { PortalBoardSubmission } from "./types";

/** Abstimmung des Beirats zu einer Vorlage (M19-02): Zustimmung, Ablehnung oder Kommentar bis
 *  zur Frist; danach und nach Abschluss nur lesend. Das Votum ist Information für die
 *  Verwaltung, es gibt nichts frei. */
function SubmissionCard({ initial }: { initial: PortalBoardSubmission }) {
  const t = useTranslations("BoardSubmissions");
  const format = useFormatter();
  const [row, setRow] = useState(initial);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const date = (value: string) => format.dateTime(new Date(`${value}T00:00:00`), { day: "2-digit", month: "2-digit", year: "numeric" });

  const send = async (vote: "approve" | "reject" | "comment") => {
    setBusy(true);
    setError(null);
    setNotice(null);
    const res = await bff<PortalBoardSubmission>(`/api/bff/portal/board/submissions/${row.id}/votes`, {
      method: "POST",
      body: JSON.stringify({ vote, comment: comment.trim() || null }),
    });
    setBusy(false);
    if (res.ok) {
      setRow(res.data);
      setComment("");
      setNotice(t("saved"));
    } else setError(res.message);
  };

  return (
    <li className={`${ui.card} flex flex-col gap-2`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{row.title}</span>
        <span className={ui.badge}>{t(`kinds.${row.kind}`)}</span>
      </div>
      {row.note ? <p className="text-sm">{row.note}</p> : null}
      {row.amount ? <p className="text-sm text-muted">{t("amount", { amount: format.number(Number(row.amount), { style: "currency", currency: "EUR" }) })}</p> : null}
      <p className="text-xs text-subtle">
        {t("dueOn", { date: date(row.due_on) })}
        {row.overdue ? ` · ${t("overdue")}` : ""}
        {row.status === "closed" ? ` · ${t("closed")}` : ""}
      </p>
      <p className="text-xs text-subtle">{t("tally", { ...row.tally, members: row.member_count })}</p>
      {row.my_votes.length > 0 ? (
        <div className="text-sm">
          <span className={ui.label}>{t("myVotes")}</span>
          <ul>
            {row.my_votes.map((v) => (
              <li key={v.id}>
                {t(`vote.${v.vote}`)}
                {v.comment ? `: ${v.comment}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {row.can_vote ? (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("comment")}</span>
            <textarea className={ui.input} rows={2} maxLength={4000} value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={ui.primary} disabled={busy} onClick={() => void send("approve")}>
              {t("approve")}
            </button>
            <button type="button" className={ui.button} disabled={busy} onClick={() => void send("reject")}>
              {t("reject")}
            </button>
            <button type="button" className={ui.button} disabled={busy || !comment.trim()} onClick={() => void send("comment")}>
              {t("sendComment")}
            </button>
          </div>
        </div>
      ) : (
        <p className="text-xs text-muted">{t("notPossible")}</p>
      )}
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
    </li>
  );
}

export function BoardSubmissions({ initial }: { initial: PortalBoardSubmission[] }) {
  const t = useTranslations("BoardSubmissions");
  if (initial.length === 0) return <p className={ui.notice}>{t("empty")}</p>;
  return (
    <ul className="flex flex-col gap-3">
      {initial.map((row) => (
        <SubmissionCard key={row.id} initial={row} />
      ))}
    </ul>
  );
}
