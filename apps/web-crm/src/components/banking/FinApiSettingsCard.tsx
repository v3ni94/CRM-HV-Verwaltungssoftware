"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type FinApiConfig = {
  configured: boolean;
  base_url: string | null;
  mandator_id: string | null;
  sandbox: boolean | null;
};

/** finAPI-Zugangsdaten (Einstellungen, /einstellungen/bank, M11-finapi). Client-ID und
 *  -Secret werden nie zurückgeliefert (nur `configured`); ein erneutes Speichern ersetzt
 *  beide vollständig. Read only Anbindung, keine Zahlungen. */
export function FinApiSettingsCard({ initial }: { initial: FinApiConfig }) {
  const t = useTranslations("BankSettings");
  const [config, setConfig] = useState(initial);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [mandatorId, setMandatorId] = useState(initial.mandator_id ?? "");
  const [baseUrl, setBaseUrl] = useState(initial.base_url ?? "");
  const [sandbox, setSandbox] = useState(initial.sandbox ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    setMessage(null);
    const result = await bff<FinApiConfig>("/api/v1/banking/finapi/config", {
      method: "PUT",
      body: JSON.stringify({
        client_id: clientId,
        client_secret: clientSecret,
        mandator_id: mandatorId || null,
        base_url: baseUrl,
        sandbox,
      }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setConfig(result.data);
    setClientId("");
    setClientSecret("");
    setMessage(t("saved"));
  }

  return (
    <section className={ui.card}>
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("description")}</p>
      <p className="mt-2 text-sm">
        {config.configured ? t("statusConfigured", { url: config.base_url ?? "" }) : t("statusMissing")}
      </p>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {message ? <p className={ui.notice}>{message}</p> : null}
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm">
          {t("baseUrl")}
          <input className={ui.input} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://sandbox.finapi.io" />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("mandatorId")}
          <input className={ui.input} value={mandatorId} onChange={(e) => setMandatorId(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("clientId")}
          <input className={ui.input} value={clientId} onChange={(e) => setClientId(e.target.value)} autoComplete="off" />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("clientSecret")}
          <input
            className={ui.input}
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            autoComplete="off"
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={sandbox} onChange={(e) => setSandbox(e.target.checked)} />
          {t("sandbox")}
        </label>
      </div>
      <button
        type="button"
        className={`${ui.primary} mt-3`}
        onClick={save}
        disabled={busy || !baseUrl || !clientId || !clientSecret}
      >
        {t("save")}
      </button>
    </section>
  );
}
