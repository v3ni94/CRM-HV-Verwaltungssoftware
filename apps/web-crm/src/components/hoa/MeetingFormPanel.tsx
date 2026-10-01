"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type MeetingFormData = {
  mode: string;
  status: string;
  invited_at: string | null;
  invitation_weeks: number | null;
  latest_invitation_at: string | null;
  invitation_short_notice: boolean;
  invitation_short_notice_reason: string | null;
  short_notice_note: string | null;
  invitation_notice: string | null;
  virtual_basis: { id: string; number: number; decided_on: string } | null;
  virtual_basis_valid_until: string | null;
  virtual_basis_term_notice?: string | null;
  has_dial_in: boolean;
};

export type AttendanceRow = {
  contract_id: string;
  unit_number: string | null;
  party_name: string | null;
  channel: string;
  proxy_name: string | null;
};

const KNOWN_MODE = new Set(["presence", "hybrid", "virtual"]);
const KNOWN_CHANNEL = new Set(["presence", "online", "proxy", "absent"]);

/** Versammlungsform, Einladungsfrist und Einwahldaten (M25-03, V13). Das späteste Versanddatum
 *  ist Orientierung aus der Mandanteneinstellung (zu verifizieren); Einwahldaten werden nur
 *  Eigentümern der Gemeinschaft im Portal gezeigt und nie in die Einladung gedruckt. */
export function MeetingFormPanel({
  meetingId,
  data,
  attendance,
}: {
  meetingId: string;
  data: MeetingFormData;
  attendance: AttendanceRow[];
}) {
  const t = useTranslations("HoaWork.meetingForm");
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [access, setAccess] = useState("");
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const online = data.mode === "hybrid" || data.mode === "virtual";

  async function saveDialIn(event: React.FormEvent) {
    event.preventDefault();
    setState("saving");
    const result = await bff(`/api/bff/hoa/meetings/${meetingId}/dial-in`, {
      method: "PUT",
      body: JSON.stringify({ dial_in_url: url.trim() || null, dial_in_access: access.trim() || null }),
    });
    if (result.ok) {
      setState("saved");
      setMessage(null);
      router.refresh();
    } else {
      setState("error");
      setMessage(result.message);
    }
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`} data-testid="meeting-form-panel">
      <h2 className={ui.h2}>{t("title")}</h2>
      <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
        <dt className={ui.label}>{t("mode")}</dt>
        <dd>{KNOWN_MODE.has(data.mode) ? t(`modes.${data.mode}`) : data.mode}</dd>
        <dt className={ui.label}>{t("latestInvitation")}</dt>
        <dd data-testid="latest-invitation">
          {data.latest_invitation_at ? formatDate(data.latest_invitation_at) : t("noValue")}
          {data.invitation_weeks ? ` (${t("weeks", { n: data.invitation_weeks })})` : ""}
        </dd>
        {data.mode === "virtual" ? (
          <>
            <dt className={ui.label}>{t("virtualBasis")}</dt>
            <dd>
              {data.virtual_basis
                ? t("basisRef", { number: data.virtual_basis.number, date: formatDate(data.virtual_basis.decided_on) })
                : t("noValue")}
              {data.virtual_basis_valid_until ? ` · ${t("validUntil", { date: formatDate(data.virtual_basis_valid_until) })}` : ""}
            </dd>
          </>
        ) : null}
      </dl>
      <p className="text-xs text-muted">{t("deadlineHint")}</p>
      {data.virtual_basis_term_notice ? (
        <p role="status" className={ui.notice} data-testid="basis-term-notice">
          <span className={ui.label}>{t("termNotice")}: </span>
          {data.virtual_basis_term_notice}
        </p>
      ) : null}
      {data.invitation_short_notice ? (
        <p role="status" className={ui.alert} data-testid="short-notice">
          {data.short_notice_note ?? t("shortNotice")}
        </p>
      ) : null}
      {data.invitation_notice ? (
        <div className="flex flex-col gap-1">
          <span className={ui.label}>{t("invitationNotice")}</span>
          <p className="whitespace-pre-line text-sm" data-testid="invitation-notice">
            {data.invitation_notice}
          </p>
        </div>
      ) : null}
      {online && data.status !== "closed" ? (
        <form onSubmit={saveDialIn} className="flex flex-col gap-2" aria-labelledby="dial-in-title">
          <h3 id="dial-in-title" className={ui.label}>
            {t("dialIn")}
            {data.has_dial_in ? ` · ${t("dialInStored")}` : ""}
          </h3>
          <p className="text-xs text-muted">{t("dialInHint")}</p>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("dialInUrl")}</span>
            <input className={ui.input} type="url" maxLength={1000} value={url} onChange={(e) => setUrl(e.target.value)} data-testid="dial-in-url" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("dialInAccess")}</span>
            <textarea className={ui.input} maxLength={2000} rows={2} value={access} onChange={(e) => setAccess(e.target.value)} data-testid="dial-in-access" />
          </label>
          <div className={ui.formActions}>
            <button type="submit" className={ui.primary} disabled={state === "saving"}>
              {t("saveDialIn")}
            </button>
          </div>
          {state === "saved" ? <p className={ui.success}>{t("saved")}</p> : null}
          {state === "error" && message ? (
            <p role="alert" className={ui.alert}>
              {message}
            </p>
          ) : null}
        </form>
      ) : null}
      {attendance.length ? (
        <div className="flex flex-col gap-1">
          <span className={ui.label}>{t("attendance")}</span>
          <div className={ui.tableScroll}>
            <table className="w-full text-sm" data-testid="attendance-list">
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th className="py-1">{t("unit")}</th>
                  <th className="py-1">{t("owner")}</th>
                  <th className="py-1">{t("channel")}</th>
                </tr>
              </thead>
              <tbody>
                {attendance.map((row) => (
                  <tr key={row.contract_id} className="border-t border-border">
                    <td className="py-1">{row.unit_number ?? ""}</td>
                    <td className="py-1">{row.party_name ?? ""}</td>
                    <td className="py-1">
                      {KNOWN_CHANNEL.has(row.channel) ? t(`channels.${row.channel}`) : row.channel}
                      {row.proxy_name ? ` (${row.proxy_name})` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}
