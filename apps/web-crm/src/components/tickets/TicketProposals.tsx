"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Change = { field: string; old: string | null; new: string | null; confidence?: number };
type ContactSnapshot = {
  id: string;
  display_name: string;
  salutation: string | null;
  title: string | null;
  first_name: string | null;
  last_name: string | null;
  company_name: string | null;
  street: string | null;
  house_number: string | null;
  postal_code: string | null;
  city: string | null;
  phone: string | null;
  email: string | null;
};
type Proposal = {
  id: string;
  ticket_id: string;
  decision: "pending" | "accepted" | "modified" | "rejected";
  proposed: {
    title: string;
    contact_id: string | null;
    contact_display_name: string | null;
    matched_by: string | null;
    candidates: { id: string; display_name: string }[];
    changes: Change[];
    bank_change_mentioned: boolean;
    bank_hint: string | null;
    reason: string | null;
    reply_draft: { subject: string; body: string } | null;
    source?: { ai?: string };
  };
  final: { changes?: Change[] } | null;
  contact: ContactSnapshot | null;
  reply_message_id: string | null;
  reply_message_status: string | null;
};

const FIELDS = [
  "salutation",
  "title",
  "first_name",
  "last_name",
  "company_name",
  "street",
  "house_number",
  "postal_code",
  "city",
  "phone",
  "email",
] as const;

function oldValue(change: Change, contact: ContactSnapshot | null): string {
  const current = contact ? (contact as unknown as Record<string, string | null>)[change.field] : null;
  return current ?? change.old ?? "";
}

/** Vorschläge zur Stammdatenänderung am Ticket (lernendes Ticketsystem, 26.09.2026). Jede Karte
 *  zeigt den Diff alt zu neu und die Aktionen Akzeptieren, Korrigieren (Formular) und Ablehnen;
 *  nach der Übernahme den vorbereiteten Antwortentwurf. "Senden" legt den Entwurf am Ticket an
 *  und reicht ihn über den bestehenden Mail-Antwortweg zur Freigabe ein (Vier-Augen-Prinzip);
 *  hier wird nichts direkt versendet. */
export function TicketProposals({ ticketId }: { ticketId: string }) {
  const t = useTranslations("Tickets.proposals");
  const router = useRouter();
  const [rows, setRows] = useState<Proposal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<Change[]>([]);
  const [draftContact, setDraftContact] = useState<string>("");
  const [rejectReason, setRejectReason] = useState<string>("");
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<Proposal[]>(`/api/bff/tickets/${ticketId}/proposals`);
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }, [ticketId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(proposal: Proposal, action: "accept" | "reject" | "correct", body?: unknown) {
    setBusy(proposal.id);
    setError(null);
    setNotice(null);
    const res = await bff<Proposal>(`/api/bff/tickets/${ticketId}/proposals/${proposal.id}/${action}`, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    setBusy(null);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setEditing(null);
    await load();
    router.refresh();
  }

  async function send(proposal: Proposal) {
    setBusy(proposal.id);
    setError(null);
    setNotice(null);
    const created = await bff<{ id: string; status: string }>(
      `/api/bff/tickets/${ticketId}/proposals/${proposal.id}/reply-draft`,
      { method: "POST" },
    );
    if (!created.ok) {
      setBusy(null);
      setError(created.message);
      return;
    }
    if (created.data.status === "draft") {
      const submitted = await bff(`/api/bff/mail/messages/${created.data.id}/submit`, { method: "POST" });
      if (!submitted.ok) {
        setBusy(null);
        setError(submitted.message);
        await load();
        return;
      }
    }
    setBusy(null);
    setNotice(t("submitted"));
    await load();
  }

  function startEdit(proposal: Proposal) {
    setEditing(proposal.id);
    setDraft(proposal.proposed.changes.map((c) => ({ ...c })));
    setDraftContact(proposal.proposed.contact_id ?? "");
    setError(null);
  }

  if (rows === null) return error ? <p role="alert" className={ui.alert}>{error}</p> : null;
  if (rows.length === 0) return null;

  return (
    <section className="flex flex-col gap-2" data-testid="ticket-proposals">
      <h2 className={ui.h2}>{t("title")}</h2>
      {rows.map((p) => {
        const changes = p.decision === "pending" ? p.proposed.changes : (p.final?.changes ?? p.proposed.changes);
        const isEditing = editing === p.id;
        return (
          <article key={p.id} className={ui.card} data-testid="ticket-proposal">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-medium">{p.proposed.title}</h3>
              <span className={p.decision === "pending" ? ui.badgeWarning : p.decision === "rejected" ? ui.badge : ui.badgeSuccess}>
                {t(`decision.${p.decision}`)}
              </span>
            </div>
            <p className="text-xs text-muted">
              {p.contact
                ? t("contact", { name: p.contact.display_name })
                : t("contactMissing")}
              {p.proposed.reason ? ` · ${t("reason", { reason: p.proposed.reason })}` : ""}
              {p.proposed.source?.ai === "used" ? ` · ${t("aiUsed")}` : ` · ${t("aiSkipped")}`}
            </p>
            {p.proposed.bank_change_mentioned ? (
              <p className={ui.notice} data-testid="bank-hint">
                {p.proposed.bank_hint ?? t("bankHint")}
              </p>
            ) : null}
            {!isEditing ? (
              <table className={`${ui.table} mt-2 text-sm`}>
                <thead>
                  <tr>
                    <th>{t("field")}</th>
                    <th>{t("old")}</th>
                    <th>{t("new")}</th>
                  </tr>
                </thead>
                <tbody>
                  {changes.map((c) => (
                    <tr key={c.field}>
                      <td>{t(`fields.${c.field}`)}</td>
                      <td className="text-muted line-through">{oldValue(c, p.contact)}</td>
                      <td className="font-medium">{c.new ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <form
                className="mt-2 flex flex-col gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void act(p, "correct", {
                    contact_id: draftContact || null,
                    changes: draft.filter((c) => (c.new ?? "").trim()).map((c) => ({ field: c.field, old: c.old, new: c.new })),
                  });
                }}
              >
                {!p.proposed.contact_id && p.proposed.candidates.length > 0 ? (
                  <label className="flex flex-col gap-1 sm:max-w-xs">
                    <span className={ui.label}>{t("chooseContact")}</span>
                    <select className={ui.input} value={draftContact} onChange={(e) => setDraftContact(e.target.value)}>
                      <option value="">{t("chooseContactEmpty")}</option>
                      {p.proposed.candidates.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.display_name}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                {draft.map((c, i) => (
                  <div key={`${c.field}-${i}`} className="flex flex-wrap items-end gap-2">
                    <label className="flex flex-col gap-1">
                      <span className={ui.label}>{t("field")}</span>
                      <select
                        className={ui.input}
                        value={c.field}
                        onChange={(e) => setDraft((prev) => prev.map((x, j) => (j === i ? { ...x, field: e.target.value } : x)))}
                      >
                        {FIELDS.map((f) => (
                          <option key={f} value={f}>
                            {t(`fields.${f}`)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className={ui.label}>{t("new")}</span>
                      <input
                        className={ui.input}
                        aria-label={`${t("new")} ${t(`fields.${c.field}`)}`}
                        value={c.new ?? ""}
                        onChange={(e) => setDraft((prev) => prev.map((x, j) => (j === i ? { ...x, new: e.target.value } : x)))}
                      />
                    </label>
                    <button type="button" className={ui.buttonSm} onClick={() => setDraft((prev) => prev.filter((_, j) => j !== i))}>
                      {t("removeField")}
                    </button>
                  </div>
                ))}
                <div className={ui.formActions}>
                  <button
                    type="button"
                    className={ui.buttonSm}
                    onClick={() => setDraft((prev) => [...prev, { field: "last_name", old: null, new: "" }])}
                  >
                    {t("addField")}
                  </button>
                  <button type="submit" className={ui.primary} disabled={busy === p.id}>
                    {t("apply")}
                  </button>
                  <button type="button" className={ui.secondary} onClick={() => setEditing(null)}>
                    {t("cancel")}
                  </button>
                </div>
              </form>
            )}
            {p.decision === "pending" && !isEditing ? (
              <div className={`${ui.formActions} mt-3`}>
                <button
                  type="button"
                  className={ui.primary}
                  disabled={busy === p.id || !p.proposed.contact_id}
                  onClick={() => void act(p, "accept")}
                >
                  {t("accept")}
                </button>
                <button type="button" className={ui.secondary} disabled={busy === p.id} onClick={() => startEdit(p)}>
                  {t("correct")}
                </button>
                <input
                  className={ui.input}
                  placeholder={t("rejectReason")}
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                />
                <button
                  type="button"
                  className={ui.danger}
                  disabled={busy === p.id}
                  onClick={() => void act(p, "reject", { reason: rejectReason || null })}
                >
                  {t("reject")}
                </button>
              </div>
            ) : null}
            {(p.decision === "accepted" || p.decision === "modified") && p.proposed.reply_draft ? (
              <div className="mt-3 flex flex-col gap-2 border-t border-border pt-3" data-testid="reply-draft">
                <h4 className={ui.label}>{t("reply")}</h4>
                <div className="text-sm font-medium">{p.proposed.reply_draft.subject}</div>
                <pre className="whitespace-pre-wrap font-sans text-sm">{p.proposed.reply_draft.body}</pre>
                {p.reply_message_id ? (
                  <p className="text-xs text-muted">{t("replyStatus", { status: p.reply_message_status ?? "" })}</p>
                ) : (
                  <div className={ui.formActions}>
                    <button type="button" className={ui.primary} disabled={busy === p.id} onClick={() => void send(p)}>
                      {t("send")}
                    </button>
                    <span className={ui.help}>{t("sendHint")}</span>
                  </div>
                )}
              </div>
            ) : null}
          </article>
        );
      })}
      {notice ? <p className={ui.success}>{notice}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
