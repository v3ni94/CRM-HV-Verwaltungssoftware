"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type OnlineOverview = {
  enabled: boolean;
  note: string;
  has_conference_link: boolean;
  confirmations: { contract_id: string; confirmed_at: string }[];
  proxies: {
    id: string;
    grantor_contract_id: string;
    proxy_kind: "owner" | "manager";
    proxy_contract_id: string | null;
    valid_from: string;
    valid_to: string | null;
    document_id: string;
    revoked_at: string | null;
    active: boolean;
  }[];
  speaker_requests: { id: string; contract_id: string; agenda_item_id: string | null; requested_at: string; note: string | null; status: string }[];
  items: { id: string; position: number; title: string; voting_state: string; online_votes: number }[];
};

/** Online-Teilnahme im CRM (AD06 / GA11-03): Zusagen aus dem Portal, Vollmachten mit Zeitraum
 *  und Widerruf, Wortmeldeliste mit Zeitstempel und Öffnen oder Schließen der Online-Abstimmung
 *  je TOP. Zulässigkeit der rein virtuellen Versammlung prüft das System nicht (Hinweis). */
export function OnlineParticipation({
  meetingId,
  data,
  units,
}: {
  meetingId: string;
  data: OnlineOverview;
  units: Record<string, string>;
}) {
  const t = useTranslations("HoaOnline");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unit = (cid: string | null) => (cid ? t("unit", { number: units[cid] ?? "?" }) : t("manager"));

  const post = async (path: string, body?: unknown) => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/hoa/meetings/${meetingId}/${path}`, {
      method: "POST",
      ...(body ? { body: JSON.stringify(body), headers: { "content-type": "application/json" } } : {}),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    router.refresh();
  };

  return (
    <section className={`${ui.card} flex flex-col gap-3`} data-testid="online-participation">
      <h2 className="font-medium">{t("title")}</h2>
      <p className={ui.notice}>{data.note}</p>
      {!data.enabled ? <p className="text-sm text-muted">{t("disabled")}</p> : null}
      {!data.has_conference_link ? <p className="text-sm text-muted">{t("noLink")}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}

      <h3 className={ui.label}>{t("items")}</h3>
      <ul className="flex flex-col gap-2">
        {data.items.map((i) => (
          <li key={i.id} className="flex flex-wrap items-center gap-2 text-sm" data-testid="online-item">
            <span className="break-words">
              {i.position}. {i.title}
            </span>
            <span className={ui.badge}>{t(`state.${i.voting_state}`)}</span>
            <span className="text-xs text-muted">{t("onlineVotes", { n: i.online_votes })}</span>
            {data.enabled && i.voting_state === "not_opened" ? (
              <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(`agenda/${i.id}/voting/open`)}>
                {t("open")}
              </button>
            ) : null}
            {data.enabled && i.voting_state === "open" ? (
              <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(`agenda/${i.id}/voting/close`)}>
                {t("close")}
              </button>
            ) : null}
          </li>
        ))}
      </ul>

      <h3 className={ui.label}>{t("confirmations", { n: data.confirmations.length })}</h3>
      <ul className="text-sm">
        {data.confirmations.map((c) => (
          <li key={c.contract_id}>
            {unit(c.contract_id)} · {formatDateTime(c.confirmed_at)}
          </li>
        ))}
      </ul>

      <h3 className={ui.label}>{t("speakers")}</h3>
      {data.speaker_requests.length === 0 ? <p className="text-sm text-muted">{t("noSpeakers")}</p> : null}
      <ol className="flex flex-col gap-1 text-sm">
        {data.speaker_requests.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-2" data-testid="speaker-request">
            <span>
              {formatDateTime(r.requested_at)} · {unit(r.contract_id)}
              {r.note ? ` · ${r.note}` : ""}
            </span>
            <span className={ui.badge}>{t(`speakerStatus.${r.status}`)}</span>
            {r.status === "open" ? (
              <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(`speaker-requests/${r.id}`, { status: "done" })}>
                {t("handled")}
              </button>
            ) : null}
          </li>
        ))}
      </ol>

      <h3 className={ui.label}>{t("proxies")}</h3>
      <ul className="flex flex-col gap-1 text-sm">
        {data.proxies.map((p) => (
          <li key={p.id} data-testid="proxy">
            {unit(p.grantor_contract_id)} → {p.proxy_kind === "manager" ? t("manager") : unit(p.proxy_contract_id)} ·{" "}
            {formatDate(p.valid_from)}
            {p.valid_to ? ` ${t("until", { date: formatDate(p.valid_to) })}` : ""} · {p.revoked_at ? t("revoked", { at: formatDateTime(p.revoked_at) }) : p.active ? t("active") : t("inactive")}
          </li>
        ))}
      </ul>
    </section>
  );
}
