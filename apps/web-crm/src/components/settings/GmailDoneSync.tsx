"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type GmailDoneSyncSettings = {
  gmail_done_sync_mode: "off" | "record_only" | "done";
  gmail_done_closes_ticket: boolean;
  gmail_close_assigned_tickets: boolean;
  gmail_done_on_trash: boolean;
  gmail_reopen_on_unarchive: boolean;
  gmail_restore_inbox_on_reopen: boolean;
  gmail_settle_seconds: number;
  gmail_reconcile_grace_seconds: number;
  gmail_keep_open_labels: string[];
  gmail_spike_confirmed_at: string | null;
};

export const GMAIL_DONE_SYNC_DEFAULTS: GmailDoneSyncSettings = {
  gmail_done_sync_mode: "record_only",
  gmail_done_closes_ticket: false,
  gmail_close_assigned_tickets: false,
  gmail_done_on_trash: true,
  gmail_reopen_on_unarchive: true,
  gmail_restore_inbox_on_reopen: false,
  gmail_settle_seconds: 180,
  gmail_reconcile_grace_seconds: 300,
  gmail_keep_open_labels: [],
  gmail_spike_confirmed_at: null,
};

const MODES = ["off", "record_only", "done"] as const;
const SWITCHES = [
  "gmail_done_closes_ticket",
  "gmail_close_assigned_tickets",
  "gmail_done_on_trash",
  "gmail_reopen_on_unarchive",
  "gmail_restore_inbox_on_reopen",
] as const;
const SWITCH_LABELS: Record<(typeof SWITCHES)[number], string> = {
  gmail_done_closes_ticket: "closesTicket",
  gmail_close_assigned_tickets: "closeAssigned",
  gmail_done_on_trash: "doneOnTrash",
  gmail_reopen_on_unarchive: "reopenOnUnarchive",
  gmail_restore_inbox_on_reopen: "restoreInbox",
};

/** Rule M20-08 "Erledigt aus Gmail übernehmen": mode off, record only (default) or done with
 *  its guards; `PATCH /tenant/settings` with If-Match, every change is logged as
 *  `tenant_settings.updated`. Mode done stays disabled until the spike is confirmed. */
export function GmailDoneSync({
  initial,
  version,
  canUpdate,
}: {
  initial: GmailDoneSyncSettings;
  version: number;
  canUpdate: boolean;
}) {
  const t = useTranslations("GmailDoneSync");
  const [values, setValues] = useState(initial);
  const [etag, setEtag] = useState(version);
  const [labelsText, setLabelsText] = useState(initial.gmail_keep_open_labels.join(", "));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const spikeConfirmed = Boolean(values.gmail_spike_confirmed_at);
  const [spikeRef, setSpikeRef] = useState("");

  async function confirmSpike() {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<GmailDoneSyncSettings & { version: number }>(
      "/api/bff/tenant/settings/gmail-spike-confirm",
      { method: "POST", body: JSON.stringify({ protocol_ref: spikeRef.trim() }) },
    );
    setBusy(false);
    if (res.ok) {
      setValues({ ...values, ...res.data });
      setEtag(res.data.version);
      setMessage(t("spikeConfirmed"));
    } else setError(res.message);
  }

  const set = <K extends keyof GmailDoneSyncSettings>(key: K, value: GmailDoneSyncSettings[K]) =>
    setValues((prev) => ({ ...prev, [key]: value }));

  async function save() {
    const settle = Number(values.gmail_settle_seconds);
    const grace = Number(values.gmail_reconcile_grace_seconds);
    const labels = labelsText
      .split(",")
      .map((l) => l.trim())
      .filter(Boolean);
    if (!Number.isInteger(settle) || settle < 0 || settle > 3600 || !Number.isInteger(grace) || grace < 60 || grace > 3600 || labels.length > 20) {
      setError(t("invalid"));
      setMessage(null);
      return;
    }
    setBusy(true);
    setMessage(null);
    setError(null);
    const body = {
      gmail_done_sync_mode: values.gmail_done_sync_mode,
      gmail_done_closes_ticket: values.gmail_done_closes_ticket,
      gmail_close_assigned_tickets: values.gmail_close_assigned_tickets,
      gmail_done_on_trash: values.gmail_done_on_trash,
      gmail_reopen_on_unarchive: values.gmail_reopen_on_unarchive,
      gmail_restore_inbox_on_reopen: values.gmail_restore_inbox_on_reopen,
      gmail_settle_seconds: settle,
      gmail_reconcile_grace_seconds: grace,
      gmail_keep_open_labels: labels,
    };
    const res = await bff<GmailDoneSyncSettings & { version: number }>("/api/bff/tenant/settings", {
      method: "PATCH",
      headers: { "If-Match": `"${etag}"` },
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (res.ok) {
      setValues({ ...values, ...res.data });
      setLabelsText((res.data.gmail_keep_open_labels ?? labels).join(", "));
      setEtag(res.data.version);
      setMessage(t("saved"));
    } else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="gmail-done-sync-title" id="gmail-done-sync">
      <div className="flex flex-col gap-3">
        <h2 id="gmail-done-sync-title" className={ui.h2}>
          {t("title")}
        </h2>
        <p className={ui.help}>{t("description")}</p>
        <fieldset className="flex flex-col gap-1">
          <legend className={ui.label}>{t("mode")}</legend>
          {MODES.map((mode) => {
            const locked = mode === "done" && !spikeConfirmed;
            return (
              <label key={mode} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="gmail-done-sync-mode"
                  value={mode}
                  checked={values.gmail_done_sync_mode === mode}
                  disabled={!canUpdate || busy || locked}
                  onChange={() => set("gmail_done_sync_mode", mode)}
                  data-testid={`gmail-mode-${mode}`}
                />
                {t(mode === "off" ? "modeOff" : mode === "record_only" ? "modeRecordOnly" : "modeDone")}
                {locked ? <span className="text-xs text-muted">({t("spikeRequired")})</span> : null}
              </label>
            );
          })}
        </fieldset>
        {!spikeConfirmed && canUpdate ? (
          <div className="flex flex-col gap-2 rounded border border-border-soft p-3" data-testid="gmail-spike-confirm">
            <p className={ui.help}>{t("spikeHelp")}</p>
            <label className="flex flex-col gap-1 text-sm">
              {t("spikeRef")}
              <input
                className={ui.input}
                value={spikeRef}
                onChange={(e) => setSpikeRef(e.target.value)}
                maxLength={500}
                data-testid="gmail-spike-ref"
              />
            </label>
            <button
              type="button"
              className={ui.secondary}
              disabled={busy || spikeRef.trim().length === 0}
              onClick={confirmSpike}
              data-testid="gmail-spike-confirm-button"
            >
              {t("spikeConfirm")}
            </button>
          </div>
        ) : null}
        <div className="flex flex-col gap-1">
          {SWITCHES.map((key) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={values[key]}
                disabled={!canUpdate || busy}
                onChange={(e) => set(key, e.target.checked)}
                data-testid={`gmail-${key}`}
              />
              {t(SWITCH_LABELS[key])}
            </label>
          ))}
          <p className={ui.help}>{t("closesTicketHint")}</p>
          <p className={ui.help}>{t("restoreInboxHint")}</p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className={ui.label}>{t("settleSeconds")}</span>
            <input
              type="number"
              min={0}
              max={3600}
              className={ui.input}
              value={values.gmail_settle_seconds}
              disabled={!canUpdate || busy}
              onChange={(e) => set("gmail_settle_seconds", Number(e.target.value))}
              data-testid="gmail-settle-seconds"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className={ui.label}>{t("graceSeconds")}</span>
            <input
              type="number"
              min={60}
              max={3600}
              className={ui.input}
              value={values.gmail_reconcile_grace_seconds}
              disabled={!canUpdate || busy}
              onChange={(e) => set("gmail_reconcile_grace_seconds", Number(e.target.value))}
              data-testid="gmail-grace-seconds"
            />
          </label>
          <label className="flex min-w-[16rem] flex-1 flex-col gap-1 text-sm">
            <span className={ui.label}>{t("keepOpenLabels")}</span>
            <input
              type="text"
              className={ui.input}
              value={labelsText}
              disabled={!canUpdate || busy}
              onChange={(e) => setLabelsText(e.target.value)}
              data-testid="gmail-keep-open-labels"
            />
          </label>
        </div>
        <p className={ui.help}>{t("settleHint")}</p>
        <p className={ui.help}>{t("graceHint")}</p>
        <p className={ui.help}>{t("keepOpenLabelsHint")}</p>
        <p className={ui.help}>{t("latencyHint")}</p>
        <div className="flex items-center gap-2">
          <button type="button" className={ui.secondary} disabled={!canUpdate || busy} onClick={() => void save()}>
            {t("save")}
          </button>
          {message ? <span className="text-xs text-success-fg">{message}</span> : null}
        </div>
        {!canUpdate ? <p className={ui.help}>{t("readOnly")}</p> : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
