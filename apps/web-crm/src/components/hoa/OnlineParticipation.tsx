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
  items: { id: string; position: number; title: string; voting_state: string; online_votes: number; open_conflicts?: number }[];
  /** AE31 (AD06-02/03): Regel Vollmacht gegen eigene Stimme, Stimmkonflikte, Prüfpunkte zur Form. */
  proxy_conflict_mode?: string;
  conflict_note?: string;
  vote_conflicts?: VoteConflict[];
  admissibility?: Admissibility;
};

export type VoteConflict = {
  id: string;
  agenda_item_id: string;
  contract_id: string;
  first_source: "own" | "proxy";
  first_choice: string;
  second_source: "own" | "proxy";
  second_choice: string;
  mode: string;
  status: "open" | "resolved";
  resolution: "keep_first" | "apply_second" | "rule_second" | null;
  decision_note: string | null;
};

export type Admissibility = {
  applicable: boolean;
  complete: boolean;
  note: string;
  checks: { key: string; state: "ok" | "open" | "missing" | "info"; state_label: string; label: string; detail: string }[];
};

const STATE_BADGE = { ok: "badgeSuccess", open: "badgeWarning", missing: "badgeDanger", info: "badgeInfo" } as const;

/** Online-Teilnahme im CRM (AD06 / GA11-03): Zusagen aus dem Portal, Vollmachten mit Zeitraum
 *  und Widerruf, Wortmeldeliste mit Zeitstempel und Öffnen oder Schließen der Online-Abstimmung
 *  je TOP. Zulässigkeit der rein virtuellen Versammlung prüft das System nicht (Hinweis).
 *  AE31: Prüfpunkte zur Versammlungsform (erfasste Angaben, keine Rechtsauskunft) und
 *  Entscheidung der Versammlungsleitung bei Stimmkonflikten (Vollmacht gegen eigene Stimme). */
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
  const [note, setNote] = useState("");
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

      {data.admissibility?.applicable ? (
        <div className="flex flex-col gap-2" data-testid="admissibility">
          <h3 className={ui.label}>{t("admissibility.title")}</h3>
          <p className="text-xs text-muted">{data.admissibility.note}</p>
          <ul className="flex flex-col gap-1 text-sm">
            {data.admissibility.checks.map((c) => (
              <li key={c.key} className="flex flex-wrap items-center gap-2" data-testid="admissibility-check">
                <span className={ui[STATE_BADGE[c.state]]}>{t(`admissibility.state.${c.state}`)}</span>
                <span className="font-medium">{c.label}</span>
                <span className="break-words text-muted">{c.detail}</span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted">{data.admissibility.complete ? t("admissibility.complete") : t("admissibility.incomplete")}</p>
        </div>
      ) : null}

      {data.proxy_conflict_mode ? (
        <p className="text-xs text-muted" data-testid="proxy-conflict-mode">
          {t("rule", { mode: t(`mode.${data.proxy_conflict_mode}`) })}
          {data.conflict_note ? ` ${data.conflict_note}` : ""}
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
            {i.open_conflicts ? <span className={ui.badgeWarning}>{t("openConflicts", { n: i.open_conflicts })}</span> : null}
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

      {data.vote_conflicts && data.vote_conflicts.length > 0 ? (
        <div className="flex flex-col gap-2" data-testid="vote-conflicts">
          <h3 className={ui.label}>{t("conflicts.title")}</h3>
          <label className="flex flex-col gap-1 text-xs text-muted">
            {t("conflicts.note")}
            <input className={ui.input} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} data-testid="conflict-note" />
          </label>
          <ul className="flex flex-col gap-2">
            {data.vote_conflicts.map((c) => {
              const top = data.items.find((i) => i.id === c.agenda_item_id);
              return (
                <li key={c.id} className="flex flex-col gap-1 text-sm" data-testid="vote-conflict">
                  <span className="break-words">
                    {unit(c.contract_id)}
                    {top ? ` · ${top.position}. ${top.title}` : ""}
                  </span>
                  <span className="text-xs text-muted">
                    {t("conflicts.first", { source: t(`conflicts.source.${c.first_source}`), choice: t(`conflicts.choice.${c.first_choice}`) })}
                    {" · "}
                    {t("conflicts.second", { source: t(`conflicts.source.${c.second_source}`), choice: t(`conflicts.choice.${c.second_choice}`) })}
                  </span>
                  {c.status === "open" ? (
                    <span className="flex flex-wrap items-center gap-2">
                      <span className={ui.badgeWarning}>{t("conflicts.open")}</span>
                      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(`vote-conflicts/${c.id}/resolve`, { decision: "keep_first", ...(note.trim() ? { note: note.trim() } : {}) })}>
                        {t("conflicts.keepFirst")}
                      </button>
                      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(`vote-conflicts/${c.id}/resolve`, { decision: "apply_second", ...(note.trim() ? { note: note.trim() } : {}) })}>
                        {t("conflicts.applySecond")}
                      </button>
                    </span>
                  ) : (
                    <span className={ui.badge}>{t(`conflicts.resolution.${c.resolution ?? "keep_first"}`)}</span>
                  )}
                  {c.decision_note ? <span className="text-xs text-muted">{c.decision_note}</span> : null}
                </li>
              );
            })}
          </ul>
          <p className="text-xs text-muted">{t("conflicts.hint")}</p>
        </div>
      ) : null}

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
