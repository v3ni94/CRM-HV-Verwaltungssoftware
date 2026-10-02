"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

type OidcClient = { client_id: string; name: string; redirect_uris: string[]; public: boolean; active: boolean };
type WithSecret = OidcClient & { client_secret: string | null };

/** GA01-12: OIDC-Clients der Plattform anlegen, Secret erneuern, (de)aktivieren. */
export function OidcClientsAdmin() {
  const { busy, guard } = useBusy();
  const t = useTranslations("AA17.oidc");
  const [clients, setClients] = useState<OidcClient[]>([]);
  const [clientId, setClientId] = useState("");
  const [name, setName] = useState("");
  const [uris, setUris] = useState("");
  const [isPublic, setIsPublic] = useState(false);
  const [secret, setSecret] = useState<{ clientId: string; value: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<OidcClient[]>("/api/bff/platform/oidc-clients");
    if (res.ok) setClients(res.data);
    else setError(res.message);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSecret(null);
    const res = await bff<WithSecret>("/api/bff/platform/oidc-clients", {
      method: "POST",
      body: JSON.stringify({
        client_id: clientId.trim(),
        name: name.trim(),
        redirect_uris: uris.split("\n").map((u) => u.trim()).filter(Boolean),
        public: isPublic,
      }),
    });
    if (!res.ok) return setError(res.message);
    if (res.data.client_secret) setSecret({ clientId: res.data.client_id, value: res.data.client_secret });
    setClientId("");
    setName("");
    setUris("");
    await load();
  };

  const rotate = async (id: string) => {
    if (!window.confirm(t("confirmRotate"))) return;
    setError(null);
    const res = await bff<WithSecret>(`/api/bff/platform/oidc-clients/${id}/rotate-secret`, { method: "POST" });
    if (!res.ok) return setError(res.message);
    if (res.data.client_secret) setSecret({ clientId: id, value: res.data.client_secret });
  };

  const toggle = async (c: OidcClient) => {
    setError(null);
    const res = await bff(`/api/bff/platform/oidc-clients/${c.client_id}/${c.active ? "deactivate" : "activate"}`, { method: "POST" });
    if (!res.ok) return setError(res.message);
    await load();
  };

  return (
    <div className="flex flex-col gap-4">
      {secret ? (
        <div className={ui.notice} role="status">
          <p>
            {t("secretOnce")} <strong>{secret.clientId}</strong>
          </p>
          <code className={ui.mono}>{secret.value}</code>
        </div>
      ) : null}
      <div className={`${ui.card}`}>
        {clients.length === 0 ? (
          <p className={ui.help}>{t("none")}</p>
        ) : (
          <div className={ui.tableScroll}>
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("clientId")}</th>
                  <th>{t("name")}</th>
                  <th>{t("redirectUris")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {clients.map((c) => (
                  <tr key={c.client_id}>
                    <td className={ui.mono}>{c.client_id}</td>
                    <td>
                      {c.name} <span className={c.active ? ui.badgeSuccess : ui.badgeWarning}>{c.active ? t("active") : t("inactive")}</span>
                    </td>
                    <td className={ui.small}>{c.redirect_uris.join(", ")}</td>
                    <td className="flex gap-2">
                      {c.public ? null : (
                        <button disabled={busy} type="button" className={ui.secondary} onClick={guard(() => rotate(c.client_id))}>
                          {t("rotate")}
                        </button>
                      )}
                      <button disabled={busy} type="button" className={ui.secondary} onClick={guard(() => toggle(c))}>
                        {c.active ? t("deactivate") : t("activate")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <form onSubmit={guard(create)} className={`${ui.card} flex flex-col gap-3`} aria-label={t("create")}>
        <label htmlFor="aa17-oidc-id" className={ui.label}>
          {t("clientId")}
        </label>
        <input id="aa17-oidc-id" className={ui.input} value={clientId} onChange={(e) => setClientId(e.target.value)} required />
        <label htmlFor="aa17-oidc-name" className={ui.label}>
          {t("name")}
        </label>
        <input id="aa17-oidc-name" className={ui.input} value={name} onChange={(e) => setName(e.target.value)} required />
        <label htmlFor="aa17-oidc-uris" className={ui.label}>
          {t("redirectUris")}
        </label>
        <textarea id="aa17-oidc-uris" className={ui.input} rows={3} value={uris} onChange={(e) => setUris(e.target.value)} required />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} />
          {t("public")}
        </label>
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        <div className={ui.formActions}>
          <button type="submit" className={ui.primary}>
            {t("create")}
          </button>
        </div>
      </form>
    </div>
  );
}
