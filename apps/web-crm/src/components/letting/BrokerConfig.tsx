"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Config = { provider: string; enabled: boolean; api_key_set: boolean; base_url: string | null; last_test_ok: boolean | null; last_test_message: string | null };
const PROVIDERS = ["flowfact", "propstack", "onoffice"] as const;

/** Makler-Anbindung (GAF-17): Zugangsdaten nur schreibend, Aktivierung ist ein bewusster Schalter.
 *  Die Übergabe einer Anzeige bleibt eine ausdrückliche Handlung und läuft nie automatisch. */
export function BrokerConfig({ canManage }: { canManage: boolean }) {
  const t = useTranslations("Af20.broker");
  const [provider, setProvider] = useState<(typeof PROVIDERS)[number]>("flowfact");
  const [config, setConfig] = useState<Config | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setConfig(null);
    void bff<Config>(`/api/bff/letting/broker/${provider}/config`).then((res) => {
      if (cancelled) return;
      if (res.ok) {
        setConfig(res.data);
        setEnabled(res.data.enabled);
        setBaseUrl(res.data.base_url ?? "");
      } else setError(res.message);
    });
    return () => {
      cancelled = true;
    };
  }, [provider]);
  const save = async () => {
    setBusy(true);
    setError(null);
    setSaved(false);
    const body: Record<string, unknown> = { enabled, base_url: baseUrl.trim() || null };
    if (apiKey) body.api_key = apiKey;
    const res = await bff<Config>(`/api/bff/letting/broker/${provider}/config`, { method: "PUT", body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) {
      setConfig(res.data);
      setApiKey("");
      setSaved(true);
    } else setError(res.message);
  };
  return (
    <section className={ui.card} data-testid="broker-config">
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <p className="text-xs text-muted">{t("intro")}</p>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("provider")}</span>
          <select className={ui.input} value={provider} onChange={(e) => setProvider(e.target.value as (typeof PROVIDERS)[number])}>
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>{t(`providers.${p}`)}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("baseUrl")}</span>
          <input className={ui.input} value={baseUrl} disabled={!canManage} onChange={(e) => setBaseUrl(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{config?.api_key_set ? t("apiKeySet") : t("apiKey")}</span>
          <input type="password" autoComplete="off" className={ui.input} value={apiKey} disabled={!canManage} onChange={(e) => setApiKey(e.target.value)} />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} disabled={!canManage} onChange={(e) => setEnabled(e.target.checked)} />
          {t("enabled")}
        </label>
        <button type="button" className={ui.primary} disabled={busy || !canManage || !config} onClick={() => void save()}>
          {t("save")}
        </button>
      </div>
      {config?.last_test_message ? <p className="mt-1 text-xs text-muted">{config.last_test_message}</p> : null}
      {saved ? <p role="status" className={ui.notice}>{t("saved")}</p> : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
