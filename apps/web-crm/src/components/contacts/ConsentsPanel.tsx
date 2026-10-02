"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

// AE34: `record_type` "objection" marks an objection to a processing on legitimate interest;
// it is listed with the consents but never counts as one. The field is optional until the
// generated client carries it.
type Consent = components["schemas"]["ConsentOut"] & { record_type?: string };
const KINDS = ["data_sharing", "portal_terms", "email_delivery", "marketing"] as const;
// AF19 (GAE-27): objection is possible for the purposes on legitimate interest only (API: OBJECTION_KINDS).
const OBJECTION_KINDS = ["email_delivery", "data_sharing", "marketing"] as const;

export function ConsentsPanel({ contactId, consents }: { contactId: string; consents: Consent[] }) {
  const t = useTranslations("Contacts");
  const ta = useTranslations("AF19");
  const tl = useTranslations("Labels");
  const router = useRouter();
  const [kind, setKind] = useState<(typeof KINDS)[number]>("email_delivery");
  const [grantedAt, setGrantedAt] = useState(() => new Date().toISOString().slice(0, 10));
  const [source, setSource] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [oKind, setOKind] = useState<(typeof OBJECTION_KINDS)[number]>("marketing");
  const [oDate, setODate] = useState(() => new Date().toISOString().slice(0, 10));
  const [oSource, setOSource] = useState("");

  async function submitObjection(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const src = oSource.trim();
    if (src.length < 2 || src.length > 200) return setError(ta("objection.sourceInvalid"));
    if (!/^\d{4}-\d{2}-\d{2}$/.test(oDate) || oDate > new Date().toISOString().slice(0, 10)) return setError(ta("objection.dateInvalid"));
    setBusy(true);
    const result = await bff(`/api/bff/contacts/${contactId}/objections`, {
      method: "POST",
      body: JSON.stringify({ kind: oKind, received_at: new Date(Math.min(Date.now(), new Date(`${oDate}T12:00:00`).getTime())).toISOString(), source: src }),
    });
    setBusy(false);
    if (!result.ok) return setError(result.message);
    setOSource("");
    router.refresh();
  }

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
        <div className="overflow-x-auto">
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
                <td className="py-1 pr-3">
                  {tl(`consent.${c.kind}`)}
                  {c.record_type === "objection" ? <span className="ml-1 font-medium">({t("consents.objection")})</span> : null}
                </td>
                <td className="py-1 pr-3">{formatDate(c.granted_at)}</td>
                <td className="py-1 pr-3">{c.source}</td>
                <td className="py-1 pr-3">{c.revoked_at ? formatDate(c.revoked_at) : t("consents.active")}</td>
                <td className="py-1 text-right">
                  {!c.revoked_at ? (
                    <button type="button" className={ui.button} onClick={() => void revoke(c.id)}>
                      {c.record_type === "objection" ? t("consents.withdrawObjection") : t("consents.revoke")}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      ) : (
        <p className="text-sm text-muted">{t("none")}</p>
      )}
      <p className="text-sm text-muted">{t("consents.effectHint")}</p>
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
      <form onSubmit={submitObjection} className="flex flex-wrap items-end gap-3" aria-label={ta("objection.add")}>
        <h2 className="w-full text-sm font-semibold">{ta("objection.add")}</h2>
        <div>
          <label htmlFor="objection-kind" className={ui.label}>{ta("objection.kind")}</label>
          <select id="objection-kind" className={ui.input} value={oKind} onChange={(e) => setOKind(e.target.value as (typeof OBJECTION_KINDS)[number])}>
            {OBJECTION_KINDS.map((k) => (
              <option key={k} value={k}>{tl(`consent.${k}`)}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="objection-date" className={ui.label}>{ta("objection.receivedAt")}</label>
          <input id="objection-date" type="date" className={ui.input} value={oDate} onChange={(e) => setODate(e.target.value)} />
        </div>
        <div className="min-w-64 flex-1">
          <label htmlFor="objection-source" className={ui.label}>{ta("objection.source")}</label>
          <input id="objection-source" className={ui.input} placeholder={ta("objection.sourceHint")} value={oSource} onChange={(e) => setOSource(e.target.value)} />
        </div>
        <button type="submit" className={ui.primary} disabled={busy}>{ta("objection.save")}</button>
        <p className="w-full text-sm text-muted">{ta("objection.hint")}</p>
      </form>
    </div>
  );
}
