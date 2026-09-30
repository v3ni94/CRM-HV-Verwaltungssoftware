"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type SepaMandateRow = {
  id: string;
  party_id: string;
  reference: string;
  iban_masked?: string | null;
  signed_at: string;
  type: string;
  sequence: string;
  valid_until: string | null;
  status: "active" | "revoked" | "expired";
  last_used_at?: string | null;
  revoked_at?: string | null;
};

/** Mandate overview across all contracts (M5-05): status, expiry, last use, filters.
 *  Recording only: collection stays locked until gate G2. */
export function SepaOverview({ rows, today }: { rows: SepaMandateRow[]; today: string }) {
  const t = useTranslations("SepaOverview");
  const [status, setStatus] = useState("");
  const [unused, setUnused] = useState(false);
  const [expiring, setExpiring] = useState(false);
  const [query, setQuery] = useState("");

  // Orientation only: mandates ending within 90 days of today (ISO dates compare as text).
  const horizon = useMemo(() => {
    const d = new Date(`${today}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() + 90);
    return d.toISOString().slice(0, 10);
  }, [today]);

  const visible = rows.filter((r) => {
    if (status && r.status !== status) return false;
    if (unused && r.last_used_at) return false;
    if (expiring && !(r.status === "active" && r.valid_until && r.valid_until <= horizon)) return false;
    const q = query.trim().toLowerCase();
    return !q || `${r.reference} ${r.iban_masked ?? ""}`.toLowerCase().includes(q);
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="sepa-status" className={ui.label}>
            {t("status")}
          </label>
          <select id="sepa-status" className={ui.input} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">{t("all")}</option>
            <option value="active">{t("statusValue.active")}</option>
            <option value="revoked">{t("statusValue.revoked")}</option>
            <option value="expired">{t("statusValue.expired")}</option>
          </select>
        </div>
        <div>
          <label htmlFor="sepa-query" className={ui.label}>
            {t("search")}
          </label>
          <input id="sepa-query" className={ui.input} value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={unused} onChange={(e) => setUnused(e.target.checked)} />
          {t("unused")}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={expiring} onChange={(e) => setExpiring(e.target.checked)} />
          {t("expiring")}
        </label>
      </div>
      <p className="text-sm text-muted" data-testid="sepa-count">
        {t("count", { shown: visible.length, total: rows.length })}
      </p>
      {visible.length ? (
        <div className={ui.tableCard}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("reference")}</th>
                <th>{t("iban")}</th>
                <th>{t("type")}</th>
                <th>{t("signedAt")}</th>
                <th>{t("validUntil")}</th>
                <th>{t("lastUsed")}</th>
                <th>{t("status")}</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.id}>
                  <td>{r.reference}</td>
                  <td>{r.iban_masked ?? ""}</td>
                  <td>{`${r.type} / ${r.sequence}`}</td>
                  <td>{formatDate(r.signed_at)}</td>
                  <td>{r.valid_until ? formatDate(r.valid_until) : t("unlimited")}</td>
                  <td>{r.last_used_at ? formatDateTime(r.last_used_at) : t("never")}</td>
                  <td>{t(`statusValue.${r.status}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-muted">{t("none")}</p>
      )}
    </div>
  );
}
