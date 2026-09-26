"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Telefonie (13.5, A70): provider neutral inbound webhook per tenant. The HMAC secret is
 *  write only: it is sent once and never shown again (`has_webhook_secret`). */
export type TelephonySettingsOut = {
  enabled: boolean;
  provider_label: string | null;
  has_webhook_secret: boolean;
  webhook_path: string;
};

export function TelephonySettings({ initial, canManage }: { initial: TelephonySettingsOut; canManage: boolean }) {
  const t = useTranslations("TelephonySettings");
  const [saved, setSaved] = useState(initial);
  const [enabled, setEnabled] = useState(initial.enabled);
  const [providerLabel, setProviderLabel] = useState(initial.provider_label ?? "");
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<TelephonySettingsOut>("/api/bff/communication/telephony/settings", {
      method: "PUT",
      body: JSON.stringify({
        enabled,
        provider_label: providerLabel.trim() || null,
        ...(secret ? { webhook_secret: secret } : {}),
      }),
    });
    setBusy(false);
    if (res.ok) {
      setSaved(res.data);
      setEnabled(res.data.enabled);
      setSecret("");
      setMessage(t("saved"));
    } else setError(res.message);
  }

  return (
    <form onSubmit={submit} className={`${ui.card} flex flex-col gap-3`}>
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.help}>{t("intro")}</p>
      <p className="text-sm">
        <span className="text-muted">{t("endpoint")}</span>{" "}
        <code className="rounded bg-surface px-1 py-0.5 text-xs">{saved.webhook_path}</code>
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={enabled} disabled={busy || !canManage} onChange={(e) => setEnabled(e.target.checked)} />
        {t("enabled")}
      </label>
      <div>
        <label htmlFor="telephony-provider" className={ui.label}>
          {t("providerLabel")}
        </label>
        <input
          id="telephony-provider"
          className={ui.input}
          value={providerLabel}
          maxLength={100}
          disabled={busy || !canManage}
          onChange={(e) => setProviderLabel(e.target.value)}
        />
        <p className={ui.help}>{t("providerHint")}</p>
      </div>
      <div>
        <label htmlFor="telephony-secret" className={ui.label}>
          {t("secret")}
        </label>
        <input
          id="telephony-secret"
          type="password"
          autoComplete="new-password"
          className={ui.input}
          value={secret}
          minLength={16}
          maxLength={200}
          disabled={busy || !canManage}
          placeholder={saved.has_webhook_secret ? t("secretStored") : t("secretMissing")}
          onChange={(e) => setSecret(e.target.value)}
        />
        <p className={ui.help}>{t("secretHint")}</p>
      </div>
      <p className={ui.help}>{t("privacyHint")}</p>
      {canManage ? (
        <div className={ui.formActions}>
          <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
            {t("save")}
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
