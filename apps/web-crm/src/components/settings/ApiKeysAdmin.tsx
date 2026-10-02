"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { SecretOnceNotice } from "@/components/settings/SecretOnceNotice";
import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** API keys of the tenant (AF19): only the prefix is listed, the key itself is shown once after
 *  creation; revoke with confirmation. Scopes are limited to the own permissions by the API. */
export type ApiKeyRow = {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
};
type Created = ApiKeyRow & { key: string };

export function ApiKeysAdmin({ initial, loadFailed = false, canCreate, canDelete, ownPermissions }: {
  initial: ApiKeyRow[]; loadFailed?: boolean; canCreate: boolean; canDelete: boolean; ownPermissions: string[];
}) {
  const t = useTranslations("AF19");
  const [keys, setKeys] = useState(initial);
  const [secret, setSecret] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>([]);
  const [expires, setExpires] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const readable = ownPermissions.filter((p) => p.endsWith(":read"));

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (name.trim().length < 2) return setError(t("keys.nameInvalid"));
    if (scopes.length === 0) return setError(t("keys.scopesRequired"));
    setBusy(true);
    const res = await bff<Created>("/api/bff/tenant/api-keys", {
      method: "POST",
      body: JSON.stringify({ name: name.trim(), scopes, expires_at: expires ? new Date(`${expires}T23:59:59`).toISOString() : null }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    const { key, ...rest } = res.data;
    setSecret(key);
    setKeys((prev) => [...prev, rest]);
    setName("");
    setScopes([]);
    setExpires("");
  }

  async function revoke(row: ApiKeyRow) {
    if (!window.confirm(t("keys.revokeConfirm"))) return;
    setBusy(true);
    setError(null);
    const res = await bff<null>(`/api/bff/tenant/api-keys/${row.id}`, { method: "DELETE" });
    setBusy(false);
    if (res.ok) setKeys((prev) => prev.map((k) => (k.id === row.id ? { ...k, revoked_at: new Date().toISOString() } : k)));
    else setError(res.message);
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      {secret ? <SecretOnceNotice title={t("keys.secretTitle")} secret={secret} onDismiss={() => setSecret(null)} /> : null}
      {canCreate ? (
        <form onSubmit={create} className={`${ui.card} flex flex-col gap-3`} aria-label={t("keys.new")}>
          <h2 className={ui.h2}>{t("keys.new")}</h2>
          <div>
            <label htmlFor="api-key-name" className={ui.label}>{t("keys.name")}</label>
            <input id="api-key-name" className={ui.input} value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
          </div>
          <fieldset>
            <legend className={ui.label}>{t("keys.scopes")}</legend>
            <div className="flex max-h-40 flex-wrap gap-x-4 gap-y-1 overflow-y-auto">
              {readable.map((p) => (
                <label key={p} className="flex items-center gap-1 text-xs">
                  <input type="checkbox" checked={scopes.includes(p)} onChange={() => setScopes((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]))} />
                  {p}
                </label>
              ))}
            </div>
            <p className={ui.help}>{t("keys.scopesHint")}</p>
          </fieldset>
          <div>
            <label htmlFor="api-key-expires" className={ui.label}>{t("keys.expires")}</label>
            <input id="api-key-expires" type="date" className={ui.input} value={expires} onChange={(e) => setExpires(e.target.value)} />
          </div>
          <button type="submit" className={`${ui.primary} w-fit`} disabled={busy}>{t("keys.create")}</button>
        </form>
      ) : null}
      {loadFailed ? <p role="alert" className={ui.alert}>{t("keys.loadError")}</p> : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {keys.length === 0 && !loadFailed ? <p className="text-sm text-muted">{t("keys.empty")}</p> : (
        <div className="overflow-x-auto">
          <table className={ui.table}>
            <thead>
              <tr><th>{t("keys.name")}</th><th>{t("keys.prefix")}</th><th>{t("keys.scopes")}</th><th>{t("keys.lastUsed")}</th><th>{t("keys.status")}</th><th /></tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id} data-testid={`api-key-${k.id}`}>
                  <td className="font-medium">{k.name}</td>
                  <td><code className="text-xs">{k.prefix}</code></td>
                  <td className="max-w-[18rem] text-xs text-muted">{k.scopes.join(", ")}</td>
                  <td>{k.last_used_at ? formatDateTime(k.last_used_at) : t("keys.never")}</td>
                  <td>
                    <StatusPill label={k.revoked_at ? t("keys.revoked") : t("keys.active")} variant={k.revoked_at ? "neutral" : "success"} />
                    {k.expires_at ? <p className="text-xs text-muted">{t("keys.expiresOn", { date: formatDateTime(k.expires_at) })}</p> : null}
                  </td>
                  <td>
                    {canDelete && !k.revoked_at ? (
                      <button type="button" className={`${ui.buttonSm} text-danger-fg`} disabled={busy} onClick={() => void revoke(k)}>{t("keys.revoke")}</button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
