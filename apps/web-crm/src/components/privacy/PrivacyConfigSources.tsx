"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type ConfigSource = {
  key: string;
  name: string;
  service: string;
  active: boolean;
  scope: "tenant" | "platform";
  detail: string;
  entry_id: string | null;
};
type SyncResult = { created: unknown[]; updated: unknown[]; skipped_inactive: number };

/**
 * Dienstleister laut Konfiguration (S711-10, AE32): zeigt, welche externen Dienste Einstellungen
 * und Konnektoren tatsächlich nutzen, und übernimmt fehlende als Registereinträge. Übernommene
 * Einträge starten mit AVV "kein Nachweis", Drittland "offen" und rechtlicher Prüfung "offen";
 * bereits gepflegte Angaben bleiben unverändert (Backend).
 */
export function PrivacyConfigSources({ canManage, onSynced }: { canManage: boolean; onSynced: () => void | Promise<void> }) {
  const t = useTranslations("PrivacyRegister");
  const [sources, setSources] = useState<ConfigSource[] | null>(null);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<ConfigSource[]>("/api/bff/privacy/register/config-sources");
    if (res.ok) setSources(res.data ?? []);
    else setError(res.message);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function sync() {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<SyncResult>("/api/bff/privacy/register/config-sources/sync", {
      method: "POST",
      body: JSON.stringify({ include_inactive: includeInactive }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setMessage(t("sources.syncResult", { created: res.data.created.length, skipped: res.data.skipped_inactive }));
    await load();
    await onSynced();
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="privacy-sources-title" data-testid="privacy-config-sources">
      <h2 id="privacy-sources-title" className={ui.h2}>
        {t("sources.title")}
      </h2>
      <p className={ui.help}>{t("sources.intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className={ui.success}>
          {message}
        </p>
      ) : null}
      {sources === null ? (
        <p className="text-sm text-muted">{t("sources.loading")}</p>
      ) : sources.length === 0 ? (
        <p className="text-sm text-muted">{t("sources.empty")}</p>
      ) : (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("sources.name")}</th>
                <th>{t("sources.service")}</th>
                <th>{t("sources.state")}</th>
                <th>{t("sources.scope")}</th>
                <th>{t("sources.register")}</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.key} data-testid="privacy-source-row">
                  <td>
                    <span className="font-medium">{s.name}</span>
                    <span className={`${ui.help} block`}>{s.detail}</span>
                  </td>
                  <td>{s.service}</td>
                  <td>{s.active ? t("sources.active") : t("sources.inactive")}</td>
                  <td>{s.scope === "platform" ? t("sources.scopePlatform") : t("sources.scopeTenant")}</td>
                  <td>{s.entry_id ? t("sources.inRegister") : <span className={ui.badge}>{t("sources.missing")}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {canManage && sources && sources.length > 0 ? (
        <div className="flex flex-col gap-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={includeInactive} onChange={(e) => setIncludeInactive(e.target.checked)} />
            {t("sources.includeInactive")}
          </label>
          <div>
            <button type="button" className={ui.primary} disabled={busy} onClick={() => void sync()}>
              {t("sources.sync")}
            </button>
            <p className={`${ui.help} mt-1`}>{t("sources.syncHint")}</p>
          </div>
        </div>
      ) : null}
    </section>
  );
}
