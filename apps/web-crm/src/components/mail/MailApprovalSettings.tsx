"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";
import { formatDateTime } from "@/lib/format";

/** M20-04 Vier-Augen-Prinzip beim Mailversand (docs/rules): Mandantenmodus
 *  `all` | `external_only` | `off` über `PATCH /tenant/settings`, Feld `mail_approval_mode`.
 *  Vertretungen (`MailApprovalDeputy`, M20-04a) über `GET/POST/DELETE /mail/mail-approval/deputies`:
 *  jedes Mitglied darf seine eigene Abwesenheit vertreten lassen, das Recht
 *  `tenant_settings:update` verwaltet beliebige Vertretungen. */
export type MailApprovalMode = "all" | "external_only" | "off";

export type MailApprovalDeputy = {
  id: string;
  absent_user_id: string;
  deputy_user_id: string;
  starts_at: string;
  ends_at: string;
  note: string | null;
};

export type DeputyMember = { user_id: string; display_name: string };

function DeputiesSection({
  initial,
  members,
  currentUserId,
  canUpdate,
  canManageDeputies,
}: {
  initial: MailApprovalDeputy[];
  members: DeputyMember[];
  currentUserId: string | null;
  canUpdate: boolean;
  canManageDeputies: boolean;
}) {
  const t = useTranslations("MailApprovalSettings.deputy");
  const [rows, setRows] = useState(initial);
  const [absentUserId, setAbsentUserId] = useState(canUpdate ? "" : (currentUserId ?? ""));
  const [deputyUserId, setDeputyUserId] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const nameOf = (userId: string) => members.find((m) => m.user_id === userId)?.display_name ?? userId;

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const res = await bff<MailApprovalDeputy>("/api/bff/mail/mail-approval/deputies", {
      method: "POST",
      body: JSON.stringify({
        absent_user_id: canUpdate ? absentUserId : currentUserId,
        deputy_user_id: deputyUserId,
        starts_at: new Date(startsAt).toISOString(),
        ends_at: new Date(endsAt).toISOString(),
        note: note.trim() || null,
      }),
    });
    setBusy(false);
    if (res.ok) {
      setRows([res.data, ...rows]);
      setDeputyUserId("");
      setStartsAt("");
      setEndsAt("");
      setNote("");
      if (canUpdate) setAbsentUserId("");
    } else {
      setError(res.message);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    setError(null);
    const res = await bff<null>(`/api/bff/mail/mail-approval/deputies/${id}`, { method: "DELETE" });
    setBusy(false);
    if (res.ok) {
      setRows(rows.filter((r) => r.id !== id));
    } else {
      setError(res.message);
    }
  }

  return (
    <div className="border-t border-hairline pt-3">
      <h3 className={ui.h3}>{t("title")}</h3>
      <p className={ui.help}>{t("help")}</p>
      <ul className="flex flex-col gap-2 py-2">
        {rows.length === 0 ? <li className={ui.help}>{t("empty")}</li> : null}
        {rows.map((row) => (
          <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span>
              {t("row", {
                absent: nameOf(row.absent_user_id),
                deputy: nameOf(row.deputy_user_id),
                from: formatDateTime(row.starts_at),
                to: formatDateTime(row.ends_at),
              })}
              {row.note ? ` (${row.note})` : ""}
            </span>
            {canManageDeputies && (canUpdate || row.absent_user_id === currentUserId) ? (
              <button type="button" className={ui.secondary} disabled={busy} onClick={() => void remove(row.id)}>
                {t("revoke")}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      {canManageDeputies ? (
        <form onSubmit={create} className="flex flex-col gap-2">
          {canUpdate ? (
            <label className={ui.label}>
              {t("absentUser")}
              <select className={ui.input} required value={absentUserId} onChange={(e) => setAbsentUserId(e.target.value)}>
                <option value="" disabled>
                  {t("selectMember")}
                </option>
                {members.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.display_name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <label className={ui.label}>
            {t("deputyUser")}
            <select className={ui.input} required value={deputyUserId} onChange={(e) => setDeputyUserId(e.target.value)}>
              <option value="" disabled>
                {t("selectMember")}
              </option>
              {members
                .filter((m) => m.user_id !== (canUpdate ? absentUserId : currentUserId))
                .map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.display_name}
                  </option>
                ))}
            </select>
          </label>
          <label className={ui.label}>
            {t("startsAt")}
            <input
              className={ui.input}
              type="datetime-local"
              required
              value={startsAt}
              onChange={(e) => setStartsAt(e.target.value)}
            />
          </label>
          <label className={ui.label}>
            {t("endsAt")}
            <input className={ui.input} type="datetime-local" required value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
          </label>
          <label className={ui.label}>
            {t("note")}
            <input className={ui.input} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
          </label>
          <div className={ui.formActions}>
            <button type="submit" className={ui.primary} disabled={busy}>
              {t("create")}
            </button>
          </div>
        </form>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function MailApprovalSettings({
  initial,
  canUpdate,
  deputies,
  members,
  currentUserId,
  canManageDeputies = false,
}: {
  initial: MailApprovalMode;
  canUpdate: boolean;
  deputies: MailApprovalDeputy[];
  members: DeputyMember[];
  currentUserId: string | null;
  /** GAI-301: creating and revoking deputies needs communication:update (API answers 403
   *  otherwise); without it the list stays read only. */
  canManageDeputies?: boolean;
}) {
  const t = useTranslations("MailApprovalSettings");
  const [mode, setMode] = useState<MailApprovalMode>(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(next: MailApprovalMode) {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ mail_approval_mode: MailApprovalMode }>("/api/bff/tenant/settings", {
      method: "PATCH",
      body: JSON.stringify({ mail_approval_mode: next }),
    });
    setBusy(false);
    if (res.ok) {
      setMode(res.data.mail_approval_mode);
      setMessage(t("saved"));
    } else {
      setError(res.message);
    }
  }

  return (
    <section className={ui.card} aria-labelledby="mail-approval-settings-title">
      <div className="flex flex-col gap-3">
        <h2 id="mail-approval-settings-title" className={ui.h2}>
          {t("title")}
        </h2>
        <p className={ui.help}>{t("description")}</p>
        <fieldset className="flex flex-col gap-2" disabled={!canUpdate || busy}>
          <legend className={ui.label}>{t("modeLabel")}</legend>
          {(["all", "external_only", "off"] as const).map((option) => (
            <label key={option} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="mail_approval_mode"
                checked={mode === option}
                onChange={() => void save(option)}
              />
              <span>{t(`modes.${option}`)}</span>
            </label>
          ))}
        </fieldset>
        {!canUpdate ? <p className={ui.help}>{t("readOnly")}</p> : null}
        {message ? <span className="text-xs text-success-fg">{message}</span> : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        <DeputiesSection initial={deputies} members={members} currentUserId={currentUserId} canUpdate={canUpdate} canManageDeputies={canManageDeputies} />
      </div>
    </section>
  );
}
