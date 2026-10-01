"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import type { PortalMeetingDetail } from "@/components/portal/types";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const CHOICES = ["yes", "no", "abstain"] as const;

/** Online-Teilnahme an einer Versammlung (AD06 / GA11-03): Zusage, Videolink der Verwaltung
 *  (kein eigener Videostack), Wortmeldung, Vollmacht und Stimmabgabe je TOP, nur solange die
 *  Verwaltung die Abstimmung geöffnet hat. Ergebnisse erst nach der Verkündung. Schalter des
 *  Mandanten und Freigabestufe G4 prüft die API. */
export function OnlineMeetingPanel({ meetingId }: { meetingId: string }) {
  const t = useTranslations("OnlineMeeting");
  const [detail, setDetail] = useState<PortalMeetingDetail | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [proxy, setProxy] = useState({ grantor: "", kind: "owner", target: "", from: "", to: "" });
  const [file, setFile] = useState<File | null>(null);

  async function load() {
    const res = await bff<PortalMeetingDetail>(`/api/bff/portal/meetings/${meetingId}`);
    if (res.ok) setDetail(res.data);
    else setMessage(t("error", { message: res.message }));
  }

  async function act(path: string, body: unknown, done?: string) {
    setBusy(true);
    setMessage(null);
    const res = await bff(path, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setMessage(t("error", { message: res.message }));
      return false;
    }
    if (done) setMessage(done);
    await load();
    return true;
  }

  /** AE31: a vote that meets a vote of the other source is stored for review and not counted
   *  (default rule of the tenant); the owner is told so instead of "voted". */
  async function vote(itemId: string, contractId: string, choice: string) {
    setBusy(true);
    setMessage(null);
    const res = await bff<{ conflict?: boolean; counted?: boolean }>(`/api/bff/portal/meetings/${meetingId}/agenda/${itemId}/votes`, {
      method: "POST",
      body: JSON.stringify({ contract_id: contractId, choice }),
    });
    setBusy(false);
    if (!res.ok) {
      setMessage(t("error", { message: res.message }));
      return;
    }
    await load();
    if (res.data?.conflict && res.data.counted === false) setMessage(t("voteReview"));
  }

  async function grantProxy() {
    if (!file) return;
    setBusy(true);
    const form = new FormData();
    form.append("file", file);
    const upload = await bff<{ id: string }>("/api/bff/portal/uploads", { method: "POST", body: form });
    setBusy(false);
    if (!upload.ok) {
      setMessage(t("error", { message: upload.message }));
      return;
    }
    await act(
      "/api/bff/portal/meeting-proxies",
      {
        grantor_contract_id: proxy.grantor,
        proxy_kind: proxy.kind,
        proxy_contract_id: proxy.kind === "owner" ? proxy.target : null,
        meeting_id: meetingId,
        valid_from: proxy.from,
        valid_to: proxy.to || null,
        document_id: upload.data.id,
      },
      t("proxyDone"),
    );
  }

  if (!detail) {
    return (
      <div className="flex flex-col gap-2">
        <button type="button" className={ui.secondary} onClick={() => void load()}>
          {t("load")}
        </button>
        {message ? <p className={ui.alert}>{message}</p> : null}
      </div>
    );
  }
  if (!detail.online_enabled) return <p className={ui.notice}>{t("disabled")}</p>;

  const own = detail.units.filter((u) => u.own);
  const others = detail.units.filter((u) => !u.own);
  const label = (cid: string) => t("unit", { number: detail.units.find((u) => u.contract_id === cid)?.unit_number ?? "" });
  const votable = [...detail.own_contract_ids, ...detail.represented_contract_ids];
  const confirmed = detail.confirmed_contract_ids.length > 0;
  const openSpeaker = detail.speaker_requests.some((r) => r.status === "open");

  return (
    <section className="flex flex-col gap-3 rounded-md border border-border p-3" data-testid="online-meeting">
      <h2 className="font-medium">{t("title")}</h2>
      <p className={ui.help}>{detail.online_note}</p>
      {message ? <p className={ui.notice} role="status">{message}</p> : null}
      {detail.conference_url ? (
        <a className="text-sm underline break-all" href={detail.conference_url} rel="noreferrer" target="_blank">
          {t("conference")}
        </a>
      ) : null}
      {detail.conference_access ? <p className="text-sm whitespace-pre-line">{detail.conference_access}</p> : null}
      <div className={ui.formActions}>
        {confirmed ? (
          <span className={ui.badge}>{t("confirmed")}</span>
        ) : (
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void act(`/api/bff/portal/meetings/${meetingId}/participation`, {})}>
            {t("confirm")}
          </button>
        )}
        {openSpeaker ? (
          <span className={ui.badge}>{t("speakOpen")}</span>
        ) : (
          <button type="button" className={ui.secondary} disabled={busy || !confirmed} onClick={() => void act(`/api/bff/portal/meetings/${meetingId}/speaker-requests`, {})}>
            {t("speak")}
          </button>
        )}
      </div>

      <h3 className={ui.label}>{t("agenda")}</h3>
      <ul className="flex flex-col gap-2">
        {detail.items.map((item) => (
          <li key={item.id} className="flex flex-col gap-1" data-testid="online-item">
            <span className="text-sm font-medium break-words">
              {item.position}. {item.title}
            </span>
            <span className="text-xs text-subtle">{t(`state.${item.voting_state}`)}</span>
            {item.voting_state === "announced" && item.result?.votes ? (
              <span className="text-sm">
                {t("result", {
                  yes: item.result.votes.yes ?? "0",
                  no: item.result.votes.no ?? "0",
                  abstain: item.result.votes.abstain ?? "0",
                })}
              </span>
            ) : null}
            {item.voting_state === "open" && confirmed
              ? votable.map((cid) =>
                  item.voted_contract_ids.includes(cid) ? (
                    <span key={cid} className="text-xs text-subtle">
                      {label(cid)}: {t("voted")}
                    </span>
                  ) : (
                    <div key={cid} className="flex flex-wrap items-center gap-2">
                      <span className="text-xs">
                        {label(cid)}
                        {detail.represented_contract_ids.includes(cid) ? ` (${t("represented")})` : ""}
                      </span>
                      {CHOICES.map((choice) => (
                        <button
                          key={choice}
                          type="button"
                          className={ui.buttonSm}
                          disabled={busy}
                          onClick={() => void vote(item.id, cid, choice)}
                        >
                          {t(`choice.${choice}`)}
                        </button>
                      ))}
                    </div>
                  ),
                )
              : null}
          </li>
        ))}
      </ul>

      {own.length > 0 ? (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void grantProxy();
          }}
        >
          <h3 className={ui.label}>{t("proxyTitle")}</h3>
          <label className={ui.label}>
            {t("proxyUnit")}
            <select className={ui.input} required value={proxy.grantor} onChange={(e) => setProxy({ ...proxy, grantor: e.target.value })}>
              <option value="" />
              {own.map((u) => (
                <option key={u.contract_id} value={u.contract_id}>
                  {t("unit", { number: u.unit_number })}
                </option>
              ))}
            </select>
          </label>
          <label className={ui.label}>
            {t("proxyKind")}
            <select className={ui.input} value={proxy.kind} onChange={(e) => setProxy({ ...proxy, kind: e.target.value })}>
              <option value="owner">{t("proxyOwner")}</option>
              <option value="manager">{t("proxyManager")}</option>
            </select>
          </label>
          {proxy.kind === "owner" ? (
            <label className={ui.label}>
              {t("proxyTarget")}
              <select className={ui.input} required value={proxy.target} onChange={(e) => setProxy({ ...proxy, target: e.target.value })}>
                <option value="" />
                {others.map((u) => (
                  <option key={u.contract_id} value={u.contract_id}>
                    {t("unit", { number: u.unit_number })}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <label className={ui.label}>
            {t("proxyFrom")}
            <input className={ui.input} type="date" required value={proxy.from} onChange={(e) => setProxy({ ...proxy, from: e.target.value })} />
          </label>
          <label className={ui.label}>
            {t("proxyTo")}
            <input className={ui.input} type="date" value={proxy.to} onChange={(e) => setProxy({ ...proxy, to: e.target.value })} />
          </label>
          <label className={ui.label}>
            {t("proxyFile")}
            <input className={ui.input} type="file" required accept="application/pdf,image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <button type="submit" className={ui.secondary} disabled={busy}>
            {t("proxySubmit")}
          </button>
        </form>
      ) : null}
    </section>
  );
}
