"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Einstellungen, Schadenbearbeiter (INT-SDT-01): connection to the claims adjuster. Token,
 *  HMAC secret and webhook secret are write only; the API returns "gesetzt" and the last four
 *  characters of the token. Enabling requires the AVV confirmation first. */
export type SchadenstoolConfig = {
  base_url: string | null;
  enabled: boolean;
  token_set: boolean;
  token_last4: string | null;
  token_invalid: boolean;
  hmac_secret_set: boolean;
  webhook_secret_set: boolean;
  webhook_path: string;
  avv_confirmed_on: string | null;
  avv_confirmed_by: string | null;
  avv_note: string | null;
  last_tested_at: string | null;
  last_test_ok: boolean | null;
  last_test_message: string | null;
  last_pull_at: string | null;
  last_pull_message: string | null;
};

export function SchadenstoolSettings({ initial, canManage }: { initial: SchadenstoolConfig; canManage: boolean }) {
  const t = useTranslations("Schadenstool");
  const [saved, setSaved] = useState(initial);
  const [baseUrl, setBaseUrl] = useState(initial.base_url ?? "");
  const [token, setToken] = useState("");
  const [hmacSecret, setHmacSecret] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [avvDate, setAvvDate] = useState(initial.avv_confirmed_on ?? "");
  const [avvNote, setAvvNote] = useState(initial.avv_note ?? "");
  const [enabled, setEnabled] = useState(initial.enabled);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function apply(data: SchadenstoolConfig, note: string) {
    setSaved(data);
    setEnabled(data.enabled);
    setToken("");
    setHmacSecret("");
    setWebhookSecret("");
    setMessage(note);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<SchadenstoolConfig>("/api/bff/integrations/schadenstool/config", {
      method: "PUT",
      body: JSON.stringify({
        base_url: baseUrl.trim(),
        enabled,
        ...(token ? { token } : {}),
        ...(hmacSecret ? { hmac_secret: hmacSecret } : {}),
        ...(webhookSecret ? { webhook_secret: webhookSecret } : {}),
        ...(avvDate ? { avv_confirmed_on: avvDate } : {}),
        avv_note: avvNote,
      }),
    });
    setBusy(false);
    if (res.ok) apply(res.data, t("saved"));
    else setError(res.message);
  }

  async function action(path: "config/test" | "pull") {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<SchadenstoolConfig | { queued: boolean }>(`/api/bff/integrations/schadenstool/${path}`, { method: "POST" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    if (path === "pull") setMessage(t("pullQueued"));
    else {
      const data = res.data as SchadenstoolConfig;
      apply(data, data.last_test_ok ? t("testOk") : t("testFailed", { reason: data.last_test_message ?? "" }));
    }
  }

  const disabled = busy || !canManage;
  return (
    <form onSubmit={submit} className={`${ui.card} flex flex-col gap-3`}>
      <h2 className={ui.h2}>{t("connection")}</h2>
      <p className={ui.help}>{t("intro")}</p>
      {saved.token_invalid ? (
        <p role="alert" className={ui.alert}>
          {t("tokenInvalid")}
        </p>
      ) : null}
      <div>
        <label htmlFor="sdt-base-url" className={ui.label}>
          {t("baseUrl")}
        </label>
        <input id="sdt-base-url" className={ui.input} value={baseUrl} maxLength={300} disabled={disabled} placeholder="https://" onChange={(e) => setBaseUrl(e.target.value)} />
      </div>
      <div>
        <label htmlFor="sdt-token" className={ui.label}>
          {t("token")}
        </label>
        <input
          id="sdt-token"
          type="password"
          autoComplete="new-password"
          className={ui.input}
          value={token}
          disabled={disabled}
          placeholder={saved.token_set ? t("tokenStored", { last4: saved.token_last4 ?? "" }) : t("secretMissing")}
          onChange={(e) => setToken(e.target.value)}
        />
      </div>
      <div>
        <label htmlFor="sdt-hmac" className={ui.label}>
          {t("hmacSecret")}
        </label>
        <input
          id="sdt-hmac"
          type="password"
          autoComplete="new-password"
          className={ui.input}
          value={hmacSecret}
          disabled={disabled}
          placeholder={saved.hmac_secret_set ? t("secretStored") : t("optional")}
          onChange={(e) => setHmacSecret(e.target.value)}
        />
      </div>
      <div>
        <label htmlFor="sdt-webhook-secret" className={ui.label}>
          {t("webhookSecret")}
        </label>
        <input
          id="sdt-webhook-secret"
          type="password"
          autoComplete="new-password"
          className={ui.input}
          value={webhookSecret}
          minLength={16}
          disabled={disabled}
          placeholder={saved.webhook_secret_set ? t("secretStored") : t("secretMissing")}
          onChange={(e) => setWebhookSecret(e.target.value)}
        />
        <p className={ui.help}>{t("webhookHint")}</p>
      </div>
      {saved.webhook_path ? (
        <p className="text-sm">
          <span className="text-muted">{t("webhookUrl")}</span>{" "}
          <code className="break-all rounded bg-surface-2 px-1 py-0.5 text-xs">{saved.webhook_path}</code>
        </p>
      ) : null}
      <fieldset className="flex flex-col gap-2">
        <legend className={ui.label}>{t("avvTitle")}</legend>
        <p className={ui.help}>{t("avvHint")}</p>
        <label htmlFor="sdt-avv-date" className={ui.label}>
          {t("avvDate")}
        </label>
        <input id="sdt-avv-date" type="date" className={ui.input} value={avvDate} disabled={disabled} onChange={(e) => setAvvDate(e.target.value)} />
        <label htmlFor="sdt-avv-note" className={ui.label}>
          {t("avvNote")}
        </label>
        <input id="sdt-avv-note" className={ui.input} value={avvNote} maxLength={500} disabled={disabled} onChange={(e) => setAvvNote(e.target.value)} />
        {saved.avv_confirmed_on ? <p className={ui.help}>{t("avvConfirmed", { date: formatDate(saved.avv_confirmed_on) })}</p> : null}
      </fieldset>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={enabled} disabled={disabled} onChange={(e) => setEnabled(e.target.checked)} />
        {t("enabled")}
      </label>
      <p className={ui.help}>{t("dataHint")}</p>
      {saved.last_tested_at ? (
        <p className={ui.help}>
          {t("lastTest", { at: formatDateTime(saved.last_tested_at), result: saved.last_test_message ?? "" })}
        </p>
      ) : null}
      {saved.last_pull_at ? (
        <p className={ui.help}>
          {t("lastPull", { at: formatDateTime(saved.last_pull_at), result: saved.last_pull_message ?? "" })}
        </p>
      ) : null}
      {canManage ? (
        <div className={ui.formActions}>
          <button type="submit" className={ui.primary} disabled={busy}>
            {t("save")}
          </button>
          <button type="button" className={ui.secondary} disabled={busy || !saved.token_set} onClick={() => void action("config/test")}>
            {t("test")}
          </button>
          <button type="button" className={ui.secondary} disabled={busy || !saved.enabled} onClick={() => void action("pull")}>
            {t("pull")}
          </button>
        </div>
      ) : (
        <p className={ui.help}>{t("readOnly")}</p>
      )}
      {message ? (
        <p role="status" className={ui.success}>
          {message}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </form>
  );
}
