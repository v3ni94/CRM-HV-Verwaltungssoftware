"use client";

import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { problemMessage, readProblem } from "@/lib/problem";
import { ui } from "@/lib/ui";

type HelperAccess = {
  grant_id: string;
  account_id: string;
  contact_id: string;
  name: string | null;
  kind: "helper" | "tenant" | "owner" | string;
  right: string;
  valid_from: string;
  valid_to: string | null;
  account_status: string;
  activated: boolean;
  has_email?: boolean;
};

type Created = {
  grant_id: string;
  invitation_token: string | null;
  mail_draft_id: string | null;
};

/** Gehilfenzugänge (M30, ported from U-Protokoll "Gehilfenzugänge"): staff creates a portal
 *  access scoped to exactly this protocol for a helper, tenant or owner, optionally also
 *  registered as a participant moving in/out. Revoke here; the invitation goes out as mail draft or letter (M30-01). */
export function HelperAccessSection({
  base,
  disabled,
  t,
}: {
  base: string;
  disabled: boolean;
  t: (key: string, values?: Record<string, string | number>) => string;
}) {
  const [rows, setRows] = useState<HelperAccess[] | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [kind, setKind] = useState<"helper" | "tenant" | "owner">("helper");
  const [registerParticipant, setRegisterParticipant] = useState(false);
  const [participantRole, setParticipantRole] = useState<"moving_in" | "moving_out">("moving_in");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Created | null>(null);
  const [asMailDraft, setAsMailDraft] = useState(true);
  const [drafted, setDrafted] = useState(false);
  const url = `${base}/helper-access`;

  async function load() {
    const res = await bff<HelperAccess[]>(url);
    if (res.ok) setRows(res.data);
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setCreated(null);
    const body: Record<string, unknown> = {
      name: name.trim(),
      email: email.trim(),
      kind,
      register_as_participant: registerParticipant,
      invitation_as_mail_draft: asMailDraft,
    };
    if (registerParticipant) body.participant_role = participantRole;
    const res = await bff<Created>(url, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) {
      setCreated(res.data);
      setName("");
      setEmail("");
      await load();
    } else setError(res.message);
  }

  async function revoke(grantId: string) {
    if (!window.confirm(t("helperAccess.confirmRevoke"))) return;
    setBusy(true);
    const res = await bff(`${url}/${grantId}`, { method: "DELETE" });
    setBusy(false);
    if (res.ok) await load();
    else setError(res.message);
  }

  /** M30-01: the code is stored as a hash only, so each delivery issues a fresh code. */
  async function invitationDraft(grantId: string) {
    if (!window.confirm(t("helperAccess.confirmNewCode"))) return;
    setBusy(true);
    setError(null);
    setCreated(null);
    setDrafted(false);
    const res = await bff<{ mail_draft_id: string }>(`${url}/${grantId}/invitation-draft`, {
      method: "POST",
    });
    setBusy(false);
    if (res.ok) setDrafted(true);
    else setError(res.message);
  }

  async function invitationLetter(grantId: string) {
    if (!window.confirm(t("helperAccess.confirmNewCode"))) return;
    setBusy(true);
    setError(null);
    setCreated(null);
    setDrafted(false);
    try {
      const response = await fetch(`${url}/${grantId}/invitation-letter`, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) {
        setError(problemMessage(await readProblem(response), response.status));
        return;
      }
      const blob = await response.blob();
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = `einladung-${grantId}.pdf`;
      a.click();
      URL.revokeObjectURL(href);
    } catch {
      setError(problemMessage(null, 0));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`${ui.card} flex flex-col gap-3`} data-testid="helper-access">
      <h2 className={ui.h2}>{t("helperAccess.title")}</h2>
      <p className="text-sm text-muted">{t("helperAccess.help")}</p>
      {rows && rows.length ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted">
              <th className="pb-1">{t("helperAccess.name")}</th>
              <th className="pb-1">{t("helperAccess.kind")}</th>
              <th className="pb-1">{t("helperAccess.status")}</th>
              <th className="pb-1">{t("helperAccess.validTo")}</th>
              <th className="pb-1" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.grant_id} className="border-t border-border-soft">
                <td className="py-1">{r.name || "–"}</td>
                <td className="py-1">{t(`helperAccess.kinds.${r.kind}`)}</td>
                <td className="py-1">
                  {r.activated ? t("helperAccess.activated") : t("helperAccess.invited")}
                </td>
                <td className="py-1">
                  {r.valid_to ? r.valid_to.split("-").reverse().join(".") : "–"}
                </td>
                <td className="py-1 text-right">
                  {!disabled ? (
                    <div className="flex justify-end gap-2">
                      {!r.activated ? (
                        r.has_email === false ? (
                          <button
                            type="button"
                            className={ui.buttonSm}
                            disabled={busy}
                            onClick={() => invitationLetter(r.grant_id)}
                          >
                            {t("helperAccess.invitationLetter")}
                          </button>
                        ) : (
                          <>
                            <button
                              type="button"
                              className={ui.buttonSm}
                              disabled={busy}
                              onClick={() => invitationDraft(r.grant_id)}
                            >
                              {t("helperAccess.invitationDraft")}
                            </button>
                            <button
                              type="button"
                              className={ui.buttonSm}
                              disabled={busy}
                              onClick={() => invitationLetter(r.grant_id)}
                            >
                              {t("helperAccess.invitationLetter")}
                            </button>
                          </>
                        )
                      ) : null}
                      <button
                        type="button"
                        className={ui.buttonSm}
                        disabled={busy}
                        onClick={() => revoke(r.grant_id)}
                      >
                        {t("helperAccess.revoke")}
                      </button>
                    </div>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-sm text-muted">{t("helperAccess.empty")}</p>
      )}
      {!disabled ? (
        <form onSubmit={create} className="flex flex-col gap-2 border-t border-border-soft pt-3">
          <div className="grid gap-2 md:grid-cols-3">
            <div>
              <label htmlFor="helper-name" className={ui.label}>
                {t("helperAccess.name")}
              </label>
              <input
                id="helper-name"
                className={ui.input}
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="helper-email" className={ui.label}>
                {t("helperAccess.email")}
              </label>
              <input
                id="helper-email"
                type="email"
                className={ui.input}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <label htmlFor="helper-kind" className={ui.label}>
                {t("helperAccess.kind")}
              </label>
              <select
                id="helper-kind"
                className={ui.input}
                value={kind}
                onChange={(e) => setKind(e.target.value as typeof kind)}
              >
                <option value="helper">{t("helperAccess.kinds.helper")}</option>
                <option value="tenant">{t("helperAccess.kinds.tenant")}</option>
                <option value="owner">{t("helperAccess.kinds.owner")}</option>
              </select>
            </div>
          </div>
          <label className="flex items-center gap-1.5 text-sm">
            <input
              type="checkbox"
              checked={registerParticipant}
              onChange={(e) => setRegisterParticipant(e.target.checked)}
            />
            {t("helperAccess.registerParticipant")}
          </label>
          <label className="flex items-center gap-1.5 text-sm">
            <input
              type="checkbox"
              checked={asMailDraft}
              onChange={(e) => setAsMailDraft(e.target.checked)}
            />
            {t("helperAccess.mailDraftOption")}
          </label>
          {registerParticipant ? (
            <fieldset className="flex gap-4">
              <label className="flex items-center gap-1.5 text-sm">
                <input
                  type="radio"
                  name="participant-role"
                  checked={participantRole === "moving_in"}
                  onChange={() => setParticipantRole("moving_in")}
                />
                {t("helperAccess.movingIn")}
              </label>
              <label className="flex items-center gap-1.5 text-sm">
                <input
                  type="radio"
                  name="participant-role"
                  checked={participantRole === "moving_out"}
                  onChange={() => setParticipantRole("moving_out")}
                />
                {t("helperAccess.movingOut")}
              </label>
            </fieldset>
          ) : null}
          {error ? (
            <p role="alert" className={ui.alert}>
              {error}
            </p>
          ) : null}
          <div>
            <button type="submit" className={ui.button} disabled={busy}>
              {t("helperAccess.create")}
            </button>
          </div>
        </form>
      ) : null}
      {created ? (
        created.invitation_token ? (
          <div className={ui.notice} data-testid="helper-invitation-token">
            <p className="font-medium">{t("helperAccess.tokenTitle")}</p>
            <p>{asMailDraft ? t("helperAccess.tokenHelp") : t("helperAccess.tokenHelpManual")}</p>
            <code className="mt-1 block select-all break-all rounded bg-bg px-2 py-1 font-mono text-xs">
              {created.invitation_token}
            </code>
          </div>
        ) : (
          <p className="text-sm text-muted">{t("helperAccess.mailDrafted")}</p>
        )
      ) : null}
      {drafted ? <p className="text-sm text-muted">{t("helperAccess.mailDrafted")}</p> : null}
    </div>
  );
}
