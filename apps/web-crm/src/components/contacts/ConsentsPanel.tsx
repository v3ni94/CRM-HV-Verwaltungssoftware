"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Consent = components["schemas"]["ConsentOut"];
const KINDS = ["data_sharing", "portal_terms", "email_delivery", "marketing"] as const;

export function ConsentsPanel({ contactId, consents }: { contactId: string; consents: Consent[] }) {
  const t = useTranslations("Contacts");
  const tl = useTranslations("Labels");
  const router = useRouter();
  const [kind, setKind] = useState<(typeof KINDS)[number]>("email_delivery");
  const [grantedAt, setGrantedAt] = useState(() => new Date().toISOString().slice(0, 10));
  const [source, setSource] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (source.trim().length < 2 || source.trim().length > 200) {
      setError(t("consents.sourceInvalid"));
      return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(grantedAt)) {
      setError(t("consents.dateInvalid"));
      return;
    }
    setBusy(true);
    // Local noon keeps the calendar day stable when converted to UTC.
    const granted = new Date(`${grantedAt}T12:00:00`).toISOString();
    const result = await bff(`/api/bff/contacts/${contactId}/consents`, {
      method: "POST",
      body: JSON.stringify({ kind, granted_at: granted, source: source.trim() }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setSource("");
    router.refresh();
  }

  async function revoke(id: string) {
    if (!window.confirm(t("consents.revokeConfirm"))) return;
    setError(null);
    const result = await bff(`/api/bff/consents/${id}/revoke`, { method: "POST" });
    if (!result.ok) {
      setError(result.message);
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {consents.length ? (
        <table className="w-full text-sm">
          <thead className="border-b border-border text-left text-xs text-muted">
            <tr>
              <th className="py-1 pr-3 font-medium">{t("consents.kind")}</th>
              <th className="py-1 pr-3 font-medium">{t("consents.grantedAt")}</th>
              <th className="py-1 pr-3 font-medium">{t("consents.source")}</th>
              <th className="py-1 pr-3 font-medium">{t("consents.revokedAt")}</th>
              <th className="py-1" />
            </tr>
          </thead>
          <tbody>
            {consents.map((c) => (
              <tr key={c.id} className="border-b border-border">
                <td className="py-1 pr-3">{tl(`consent.${c.kind}`)}</td>
                <td className="py-1 pr-3">{formatDate(c.granted_at)}</td>
                <td className="py-1 pr-3">{c.source}</td>
                <td className="py-1 pr-3">{c.revoked_at ? formatDate(c.revoked_at) : t("consents.active")}</td>
                <td className="py-1 text-right">
                  {!c.revoked_at ? (
                    <button type="button" className={ui.button} onClick={() => void revoke(c.id)}>
                      {t("consents.revoke")}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-sm text-muted">{t("none")}</p>
      )}
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3" aria-label={t("consents.add")}>
        <h2 className="w-full text-sm font-semibold">{t("consents.add")}</h2>
        <div>
          <label htmlFor="consent-kind" className={ui.label}>
            {t("consents.kind")}
          </label>
          <select id="consent-kind" className={ui.input} value={kind} onChange={(e) => setKind(e.target.value as (typeof KINDS)[number])}>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {tl(`consent.${k}`)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="consent-granted" className={ui.label}>
            {t("consents.grantedAt")}
          </label>
          <input id="consent-granted" type="date" className={ui.input} value={grantedAt} onChange={(e) => setGrantedAt(e.target.value)} />
        </div>
        <div className="min-w-64 flex-1">
          <label htmlFor="consent-source" className={ui.label}>
            {t("consents.source")}
          </label>
          <input id="consent-source" className={ui.input} placeholder={t("consents.sourceHint")} value={source} onChange={(e) => setSource(e.target.value)} />
        </div>
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("consents.save")}
        </button>
      </form>
    </div>
  );
}
