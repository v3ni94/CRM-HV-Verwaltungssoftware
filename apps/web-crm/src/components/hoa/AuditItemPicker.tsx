"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ContactPicker, type PickedContact } from "@/components/hoa/ContactPicker";
import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type AuditCandidate = {
  journal_entry_id: string;
  booking_date: string;
  number: number | null;
  text: string;
  amount: string;
  document_id: string | null;
  accounts: { id: string; number: string; name: string }[];
  vendor_contact_id: string | null;
  invoice_number: string | null;
  selected: boolean;
};

export type AuditCandidates = {
  period_from: string;
  period_to: string;
  total: number;
  truncated: boolean;
  items: AuditCandidate[];
};

/** Prüfpositionen auswählen (PÜ07, PÜ08; A72): posted bookings of the community in the
 *  engagement period, filtered by account, vendor, date and text; a row becomes a position
 *  through the existing POST /hoa/audits/{id}/items. Read only apart from that selection. */
export function AuditItemPicker({
  auditId,
  accounts,
  periodFrom,
  periodTo,
}: {
  auditId: string;
  accounts: { id: string; number: string; name: string }[];
  periodFrom: string;
  periodTo: string;
}) {
  const t = useTranslations("HoaWork");
  const router = useRouter();
  const [accountId, setAccountId] = useState("");
  const [vendor, setVendor] = useState<PickedContact | null>(null);
  const [dateFrom, setDateFrom] = useState(periodFrom);
  const [dateTo, setDateTo] = useState(periodTo);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<AuditCandidates | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setBusy(true);
    setError(null);
    const params = new URLSearchParams();
    if (accountId) params.set("account_id", accountId);
    if (vendor) params.set("vendor_contact_id", vendor.id);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    if (query.trim()) params.set("q", query.trim());
    const res = await bff<AuditCandidates>(`/api/bff/hoa/audits/${auditId}/candidates?${params.toString()}`);
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setResult(res.data);
  }

  async function add(candidate: AuditCandidate) {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/hoa/audits/${auditId}/items`, {
      method: "POST",
      body: JSON.stringify({
        journal_entry_id: candidate.journal_entry_id,
        document_id: candidate.document_id,
        amount: candidate.amount,
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setResult((prev) =>
      prev ? { ...prev, items: prev.items.map((c) => (c.journal_entry_id === candidate.journal_entry_id ? { ...c, selected: true } : c)) } : prev,
    );
    router.refresh();
  }

  return (
    <section className="flex flex-col gap-3" data-testid="audit-item-picker">
      <h2 className={ui.h2}>{t("audit.picker.title")}</h2>
      <p className={ui.help}>{t("audit.picker.hint")}</p>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void load();
        }}
      >
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("audit.picker.account")}</span>
          <select className={ui.input} value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">{t("audit.picker.allAccounts")}</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.number} {a.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("audit.picker.dateFrom")}</span>
          <input className={ui.input} type="date" value={dateFrom} min={periodFrom} max={periodTo} onChange={(e) => setDateFrom(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("audit.picker.dateTo")}</span>
          <input className={ui.input} type="date" value={dateTo} min={periodFrom} max={periodTo} onChange={(e) => setDateTo(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("audit.picker.text")}</span>
          <input className={ui.input} value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <button type="submit" className={ui.button} disabled={busy}>
          {t("audit.picker.load")}
        </button>
      </form>
      <div className="flex flex-wrap items-end gap-2">
        <ContactPicker label={t("audit.picker.vendor")} kind="company" onPick={setVendor} />
        {vendor ? (
          <span className={ui.badge}>
            {vendor.display_name}
            <button type="button" className="text-xs" aria-label={t("audit.picker.clearVendor")} onClick={() => setVendor(null)}>
              ×
            </button>
          </span>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {result ? (
        <>
          <p className="text-sm text-muted">
            {t("audit.picker.count", { n: result.total, from: formatDate(result.period_from), to: formatDate(result.period_to) })}
            {result.truncated ? ` ${t("audit.picker.truncated")}` : ""}
          </p>
          {result.items.length === 0 ? <p className="text-sm text-muted">{t("audit.picker.empty")}</p> : null}
          {result.items.length > 0 ? (
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("audit.picker.date")}</th>
                  <th>{t("audit.picker.number")}</th>
                  <th>{t("audit.picker.booking")}</th>
                  <th>{t("audit.picker.accounts")}</th>
                  <th className="text-right">{t("amount")}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {result.items.map((c) => (
                  <tr key={c.journal_entry_id}>
                    <td>{formatDate(c.booking_date)}</td>
                    <td>{c.number ?? ""}</td>
                    <td>
                      {c.text}
                      {c.invoice_number ? <span className="text-xs text-muted"> · {t("audit.picker.invoice", { number: c.invoice_number })}</span> : null}
                    </td>
                    <td>{c.accounts.map((a) => a.number).join(", ")}</td>
                    <td className="text-right">{formatEur(c.amount)}</td>
                    <td>
                      {c.selected ? (
                        <span className={ui.badge}>{t("audit.picker.selected")}</span>
                      ) : (
                        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void add(c)}>
                          {t("audit.picker.add")}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
