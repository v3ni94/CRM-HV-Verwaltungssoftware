"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type MfaResetRequest = {
  id: string;
  membership_id: string;
  reason: string;
  status: "requested" | "approved" | "rejected";
  requested_by: string;
  decision_comment?: string | null;
  created_at: string;
};

type MemberOption = { membership_id: string; display_name: string };

/** AJ08 (GAI-603): Maske zum Zurücksetzen des zweiten Faktors im Vier-Augen-Verfahren. Die
 *  Regeln (Schalter, andere Person, Begründung) prüft die API; Wiederherstellungscodes sind
 *  offen (AI09-01). */
export function MfaResetAdmin({
  members,
  initialRequests,
  enabled,
}: {
  members: MemberOption[];
  initialRequests: MfaResetRequest[];
  enabled: boolean;
}) {
  const t = useTranslations("MfaReset");
  const [requests, setRequests] = useState(initialRequests);
  const [membershipId, setMembershipId] = useState("");
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const nameOf = (id: string) => members.find((m) => m.membership_id === id)?.display_name ?? id;

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<MfaResetRequest>("/api/bff/auth/mfa-reset/requests", {
      method: "POST",
      body: JSON.stringify({ membership_id: membershipId, reason }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setRequests((prev) => [res.data, ...prev]);
    setReason("");
    setMembershipId("");
    setMessage(t("requested"));
  }

  async function decide(row: MfaResetRequest, action: "approve" | "reject") {
    if (busy) return;
    if (action === "approve" && !window.confirm(t("confirmApprove"))) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<MfaResetRequest>(`/api/bff/auth/mfa-reset/requests/${row.id}/${action}`, {
      method: "POST",
      body: JSON.stringify({ comment: comment.trim() || null }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setRequests((prev) => prev.map((r) => (r.id === row.id ? res.data : r)));
    setComment("");
    setMessage(t("decided"));
  }

  return (
    <section className={ui.card} aria-labelledby="mfa-reset-title">
      <h2 id="mfa-reset-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      {!enabled ? <p className={`${ui.notice} mt-2`}>{t("disabled")}</p> : null}
      {enabled ? (
        <form onSubmit={(e) => void create(e)} className="mt-3 flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("member")}</span>
            <select className={ui.input} required value={membershipId} onChange={(e) => setMembershipId(e.target.value)}>
              <option value="">{t("selectMember")}</option>
              {members.map((m) => (
                <option key={m.membership_id} value={m.membership_id}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("reason")}</span>
            <textarea className={ui.input} required minLength={10} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <button type="submit" className={`${ui.primary} self-start`} disabled={busy || !membershipId || reason.trim().length < 10}>
            {busy ? t("working") : t("request")}
          </button>
        </form>
      ) : null}
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="mt-2 text-sm">
          {message}
        </p>
      ) : null}
      <h3 className={`${ui.label} mt-4`}>{t("requests")}</h3>
      {requests.length === 0 ? <p className="text-sm text-muted">{t("none")}</p> : null}
      {requests.some((r) => r.status === "requested") ? (
        <label className="mt-2 flex flex-col gap-1">
          <span className={ui.label}>{t("comment")}</span>
          <input className={ui.input} maxLength={2000} value={comment} onChange={(e) => setComment(e.target.value)} />
        </label>
      ) : null}
      <ul className="mt-2 flex flex-col gap-2">
        {requests.map((r) => (
          <li key={r.id} className="rounded-md border border-border p-2 text-sm" data-testid="mfa-reset-request">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{nameOf(r.membership_id)}</span>
              <span className="text-xs text-muted">{t(`status.${r.status}`)}</span>
            </div>
            <p className="text-muted">{r.reason}</p>
            {r.decision_comment ? <p className="text-xs text-muted">{r.decision_comment}</p> : null}
            {r.status === "requested" ? (
              <div className="mt-1 flex gap-2">
                <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void decide(r, "approve")}>
                  {t("approve")}
                </button>
                <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void decide(r, "reject")}>
                  {t("reject")}
                </button>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
