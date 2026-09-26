"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type BoardAccess = {
  id: string;
  account_id: string;
  contact_id: string;
  account_status: string | null;
  created_at: string;
  revoked_at: string | null;
};

export type BoardNote = {
  id: string;
  audit_item_id: string | null;
  cost_item_id: string | null;
  kind: string;
  text: string;
  answer: string | null;
  created_at: string;
  answered_at: string | null;
};

export type BoardSection = {
  engagement_id: string;
  auditor_contact_ids: string[];
  access: BoardAccess[];
  notes: BoardNote[];
};

/** Abschnitt Beiratszugang und Rückfragen am Prüfauftrag (A52, PÜ08): Zugang je Prüfer
 *  anlegen (Einladung wie bei Eigentümern, Einladungslink wird einmal angezeigt), Zugang
 *  beenden, Rückfragen des Beirats nachvollziehbar beantworten. */
export function BoardAuditPanel({
  auditId,
  section,
  items,
  contactNames,
  formatDate,
}: {
  auditId: string;
  section: BoardSection;
  items: { id: string; label: string }[];
  contactNames: Record<string, string>;
  formatDate: (value: string | null) => string;
}) {
  const t = useTranslations("HoaWork");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invitation, setInvitation] = useState<string | null>(null);
  const [contactId, setContactId] = useState(section.auditor_contact_ids[0] ?? "");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const name = (id: string) => contactNames[id] ?? id;
  const itemLabel = (id: string | null) => (id ? (items.find((i) => i.id === id)?.label ?? id) : t("audit.wholeEngagement"));
  const activeContacts = new Set(section.access.filter((a) => !a.revoked_at).map((a) => a.contact_id));

  async function call<T>(path: string, body?: unknown): Promise<T | null> {
    setBusy(true);
    setError(null);
    const res = await bff<T>(`/api/bff/hoa/audit-engagements/${auditId}/${path}`, {
      method: "POST",
      body: body === undefined ? "{}" : JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return null;
    }
    router.refresh();
    return res.data;
  }

  async function grant(event: React.FormEvent) {
    event.preventDefault();
    if (!contactId) return;
    const body: Record<string, string> = { contact_id: contactId };
    if (email.trim()) body.email = email.trim();
    if (displayName.trim()) body.display_name = displayName.trim();
    const res = await call<{ invitation_token: string | null }>("board-access", body);
    if (res) {
      setInvitation(res.invitation_token);
      setEmail("");
      setDisplayName("");
    }
  }

  async function revoke(accessId: string) {
    if (!window.confirm(t("audit.revokeConfirm"))) return;
    await call(`board-access/${accessId}/revoke`);
  }

  async function answer(noteId: string) {
    const text = (answers[noteId] ?? "").trim();
    if (!text) return;
    const res = await call(`notes/${noteId}/answer`, { answer: text });
    if (res !== null) setAnswers((prev) => ({ ...prev, [noteId]: "" }));
  }

  return (
    <section className="flex flex-col gap-3">
      <h2 className={ui.h2}>{t("audit.board")}</h2>
      <p className={ui.help}>{t("audit.boardHint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <ul className="text-sm">
        {section.access.map((a) => (
          <li key={a.id} className="flex flex-wrap items-center gap-2">
            <span>{name(a.contact_id)}</span>
            <span className={ui.badge}>
              {a.revoked_at ? t("audit.accessRevoked") : t(`audit.accountStatus.${a.account_status ?? "unknown"}`)}
            </span>
            <span className="text-xs text-subtle">{formatDate(a.created_at)}</span>
            {!a.revoked_at ? (
              <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void revoke(a.id)}>
                {t("audit.revoke")}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      <form onSubmit={grant} className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("audit.auditor")}</span>
          <select className={ui.input} value={contactId} onChange={(e) => setContactId(e.target.value)}>
            {section.auditor_contact_ids.map((id) => (
              <option key={id} value={id} disabled={activeContacts.has(id)}>
                {name(id)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("audit.email")}</span>
          <input className={ui.input} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("audit.displayName")}</span>
          <input className={ui.input} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </label>
        <button type="submit" className={ui.button} disabled={busy || !contactId}>
          {t("audit.grant")}
        </button>
      </form>
      <p className={ui.help}>{t("audit.grantHint")}</p>
      {invitation ? (
        <p className={ui.success}>
          {t("audit.invitationToken")}: <code className="break-all">{invitation}</code>
        </p>
      ) : null}

      <h3 className="font-medium">{t("audit.notes")}</h3>
      {section.notes.length === 0 ? <p className="text-sm text-muted">{t("audit.noNotes")}</p> : null}
      <ul className="flex flex-col gap-2 text-sm">
        {section.notes.map((n) => (
          <li key={n.id} className={`${ui.card} flex flex-col gap-1`}>
            <span className="flex flex-wrap items-center gap-2 text-xs text-subtle">
              <span>{formatDate(n.created_at)}</span>
              <span>{itemLabel(n.audit_item_id)}</span>
              <span className={ui.badge}>{t(`audit.noteKind.${n.kind}`)}</span>
            </span>
            <span>{n.text}</span>
            {n.answer ? (
              <span className="text-muted">
                {t("audit.answer")} ({formatDate(n.answered_at)}): {n.answer}
              </span>
            ) : null}
            {n.kind === "question" ? (
              <div className="flex flex-wrap items-end gap-2">
                <label className="flex flex-1 flex-col gap-1">
                  <span className={ui.label}>{t("audit.answer")}</span>
                  <textarea
                    className={ui.input}
                    rows={2}
                    value={answers[n.id] ?? ""}
                    onChange={(e) => setAnswers((prev) => ({ ...prev, [n.id]: e.target.value }))}
                  />
                </label>
                <button type="button" className={ui.buttonSm} disabled={busy || !(answers[n.id] ?? "").trim()} onClick={() => void answer(n.id)}>
                  {t("audit.sendAnswer")}
                </button>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
