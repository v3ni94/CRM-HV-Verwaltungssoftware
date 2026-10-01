"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { ContactPicker } from "../hoa/ContactPicker";
import { AdminFeeRun } from "./AdminFeeRun";

export type PropertyOption = { id: string; label: string };
type Fee = {
  id: string;
  property_id: string;
  start_date: string;
  end_date: string | null;
  interval: string;
  vat_percent: string;
  amounts_per_unit_type: Record<string, string>;
  invoice_count: number;
  // GA03-06 (Migration 0312)
  manager_contact_id?: string | null;
  termination_date?: string | null;
  due_day_rule?: string | null;
  due_day?: number | null;
  account_id?: string | null;
  sev_fee_amount?: string | null;
};
type PeriodRow = {
  fee_setting_id: string;
  period_start: string;
  period_end: string;
  status: "due" | "issued";
  number: string | null;
  draft: { net: string; vat: string; gross: string };
};
type Invoice = {
  id: string;
  number: string;
  kind: string;
  invoice_date: string;
  period_start: string | null;
  period_end: string | null;
  status: string;
  gross: string;
  cancelled_at: string | null;
  released_at?: string | null;
  payer_entry_id?: string | null;
  xrechnung_url: string | null;
};
type Check = { structure_ok: boolean; findings: { code: string; message: string }[] };

const base = "/api/bff/accounting";
const UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
const MONEY = /^\d+([.,]\d{1,2})?$/;

/** Verwalterhonorar (18 M13): set up, change or end a fee, preview the due service periods,
 *  issue once per period (gapless number), release, cancel by credit note, XRechnung download,
 *  structural check and filing. Nothing is sent; revenue posting drafts only for released invoices, behind G1. */
export function AdminFeePanel({ properties, today }: { properties: PropertyOption[]; today: string }) {
  const t = useTranslations("AdminFees");
  const [fees, setFees] = useState<Fee[]>([]);
  const [periods, setPeriods] = useState<PeriodRow[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [periodDate, setPeriodDate] = useState(today);
  // M13-05: Filter der Rechnungsliste nach Status (issued, released, cancelled).
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Q15: abgelegte PDF-Rechnungen je Rechnung (Dokument-ID), Download über den Dateipfad der Sitzung.
  const [pdfs, setPdfs] = useState<Record<string, string>>({});
  const [form, setForm] = useState({
    property_id: properties[0]?.id ?? "",
    start_date: today,
    interval: "monthly",
    vat_percent: "19",
    apartment: "",
    commercial: "",
    parking: "",
    termination_date: "",
    due_day_rule: "",
    due_day: "",
    account_id: "",
    sev_fee_amount: "",
  });
  const [manager, setManager] = useState<{ id: string; name: string } | null>(null);
  const dueDayNeeded = form.due_day_rule === "day" || form.due_day_rule === "day_next_month";
  const dueDayNumber = Number(form.due_day);
  const extraValid =
    (form.termination_date === "" || form.termination_date >= form.start_date) &&
    (!dueDayNeeded || (Number.isInteger(dueDayNumber) && dueDayNumber >= 1 && dueDayNumber <= 31)) &&
    (form.account_id.trim() === "" || UUID.test(form.account_id.trim())) &&
    (form.sev_fee_amount.trim() === "" || MONEY.test(form.sev_fee_amount.trim()));
  const label = (id: string) => properties.find((p) => p.id === id)?.label ?? id;

  const load = useCallback(async () => {
    const [f, p, i] = await Promise.all([
      bff<Fee[]>(`${base}/admin-fees`),
      bff<{ rows: PeriodRow[] }>(`${base}/admin-fees-periods?period_date=${periodDate}`),
      bff<Invoice[]>(`${base}/admin-fee-invoices${statusFilter ? `?status=${statusFilter}` : ""}`),
    ]);
    if (f.ok) setFees(f.data ?? []);
    if (p.ok) setPeriods(p.data?.rows ?? []);
    if (i.ok) setInvoices(i.data ?? []);
    const failed = [f, p, i].find((r) => !r.ok);
    setError(failed && !failed.ok ? failed.message : null);
  }, [periodDate, statusFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async (call: () => Promise<{ ok: boolean; message?: string }>, done?: string) => {
    setBusy(true);
    setError(null);
    setInfo(null);
    const res = await call();
    setBusy(false);
    if (!res.ok) setError(res.message ?? null);
    else {
      if (done) setInfo(done);
      await load();
    }
  };

  const create = () => {
    const amounts: Record<string, string> = {};
    for (const key of ["apartment", "commercial", "parking"] as const) if (form[key]) amounts[key] = form[key];
    return run(
      () =>
        bff(`${base}/admin-fees`, {
          method: "POST",
          body: JSON.stringify({
            property_id: form.property_id,
            start_date: form.start_date,
            vat_percent: form.vat_percent || "0",
            amounts_per_unit_type: amounts,
            ...(manager ? { manager_contact_id: manager.id } : {}),
            ...(form.termination_date ? { termination_date: form.termination_date } : {}),
            ...(form.due_day_rule ? { due_day_rule: form.due_day_rule } : {}),
            ...(dueDayNeeded ? { due_day: dueDayNumber } : {}),
            ...(form.account_id.trim() ? { account_id: form.account_id.trim() } : {}),
            ...(form.sev_fee_amount.trim() ? { sev_fee_amount: form.sev_fee_amount.trim().replace(",", ".") } : {}),
          }),
        }).then(async (res) => {
          if (res.ok && form.interval !== "monthly") {
            const id = (res.data as { id: string }).id;
            return bff(`${base}/admin-fees/${id}`, { method: "PATCH", body: JSON.stringify({ interval: form.interval }) });
          }
          return res;
        }),
      t("created"),
    );
  };
  const endFee = (fee: Fee) => {
    const value = window.prompt(t("endPrompt"), today);
    if (!value) return;
    void run(() => bff(`${base}/admin-fees/${fee.id}`, { method: "PATCH", body: JSON.stringify({ end_date: value }) }));
  };
  const issue = (row: PeriodRow) => {
    if (!window.confirm(t("confirmIssue"))) return;
    void run(
      () =>
        bff(`${base}/admin-fees/${row.fee_setting_id}/invoice-issue?period_start=${row.period_start}`, { method: "POST" }),
      t("issued"),
    );
  };
  const release = (inv: Invoice) =>
    run(() => bff(`${base}/admin-fee-invoices/${inv.id}/release`, { method: "POST" }), t("released"));
  // M13-07: Buchungsentwürfe (Zahler und Verwalter) nur für freigegebene Rechnungen, serverseitig hinter G1.
  const postingDrafts = (inv: Invoice) =>
    run(() => bff(`${base}/admin-fee-invoices/${inv.id}/posting-drafts`, { method: "POST" }), t("postingDraftsDone"));
  const cancel = (inv: Invoice) => {
    const reason = window.prompt(t("cancelPrompt"));
    if (!reason) return;
    void run(
      () => bff(`${base}/admin-fee-invoices/${inv.id}/cancel`, { method: "POST", body: JSON.stringify({ reason }) }),
      t("cancelled"),
    );
  };
  const check = async (inv: Invoice) => {
    setError(null);
    const res = await bff<Check>(`${base}/invoices/${inv.id}/xrechnung/check`);
    if (!res.ok) setError(res.message);
    else setInfo(res.data.structure_ok ? t("checkOk") : res.data.findings.map((f) => `${f.code}: ${f.message}`).join(" · "));
  };
  const store = (inv: Invoice) =>
    run(() => bff(`${base}/invoices/${inv.id}/xrechnung/document`, { method: "POST" }), t("stored"));

  const makePdf = async (inv: Invoice) => {
    setBusy(true);
    setError(null);
    const res = await bff<{ document_id: string }>(`${base}/admin-fee-invoices/${inv.id}/document`, { method: "POST" });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setPdfs((p) => ({ ...p, [inv.id]: res.data.document_id }));
  };

  return (
    <section className="flex flex-col gap-4">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {info ? (
        <p role="status" className={ui.success}>
          {info}
        </p>
      ) : null}

      <div className={ui.card}>
        <h2 className="mb-2 text-sm font-semibold">{t("newFee")}</h2>
        <div className="grid gap-2 sm:grid-cols-4">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("property")}</span>
            <select className={ui.input} value={form.property_id} onChange={(e) => setForm({ ...form, property_id: e.target.value })}>
              {properties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("start")}</span>
            <input type="date" className={ui.input} value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("interval")}</span>
            <select className={ui.input} value={form.interval} onChange={(e) => setForm({ ...form, interval: e.target.value })}>
              {["monthly", "quarterly", "semiannual", "yearly"].map((v) => (
                <option key={v} value={v}>
                  {t(`intervals.${v}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("vat")}</span>
            <input className={ui.input} inputMode="decimal" value={form.vat_percent} onChange={(e) => setForm({ ...form, vat_percent: e.target.value })} />
          </label>
          {(["apartment", "commercial", "parking"] as const).map((key) => (
            <label key={key} className="flex flex-col gap-1">
              <span className={ui.label}>{t(`unitTypes.${key}`)}</span>
              <input className={ui.input} inputMode="decimal" value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
            </label>
          ))}
        </div>
        <h3 className="mb-1 mt-3 text-sm font-semibold">{t("extra.title")}</h3>
        <div className="grid gap-2 sm:grid-cols-4" data-testid="fee-extra-fields">
          <div className="sm:col-span-2">
            <ContactPicker label={t("extra.manager")} onPick={(c) => setManager({ id: c.id, name: c.display_name })} />
            {manager ? (
              <p className={ui.small}>
                {t("extra.managerPicked", { name: manager.name })}{" "}
                <button type="button" className="underline" onClick={() => setManager(null)}>
                  {t("extra.managerClear")}
                </button>
              </p>
            ) : null}
          </div>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("extra.termination")}</span>
            <input type="date" className={ui.input} value={form.termination_date} onChange={(e) => setForm({ ...form, termination_date: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("extra.sevFee")}</span>
            <input className={ui.input} inputMode="decimal" value={form.sev_fee_amount} onChange={(e) => setForm({ ...form, sev_fee_amount: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("extra.dueRule")}</span>
            <select className={ui.input} value={form.due_day_rule} onChange={(e) => setForm({ ...form, due_day_rule: e.target.value })}>
              <option value="">{t("extra.dueRules.none")}</option>
              {["day", "last_day", "day_next_month"].map((v) => (
                <option key={v} value={v}>
                  {t(`extra.dueRules.${v}`)}
                </option>
              ))}
            </select>
          </label>
          {dueDayNeeded ? (
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("extra.dueDay")}</span>
              <input className={ui.input} inputMode="numeric" value={form.due_day} onChange={(e) => setForm({ ...form, due_day: e.target.value })} />
            </label>
          ) : null}
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={ui.label}>{t("extra.account")}</span>
            <input className={ui.input} value={form.account_id} onChange={(e) => setForm({ ...form, account_id: e.target.value })} />
          </label>
        </div>
        <p className={ui.help}>{t("extra.hint")}</p>
        <button type="button" className={`${ui.primary} mt-3`} onClick={create} disabled={busy || !form.property_id || !extraValid}>
          {t("create")}
        </button>
      </div>

      <AdminFeeRun today={today} propertyLabel={label} onIssued={load} />

      <h2 className="text-sm font-semibold">{t("fees")}</h2>
      <div className={ui.tableCard}>
        <table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("property")}</th>
              <th>{t("start")}</th>
              <th>{t("end")}</th>
              <th>{t("interval")}</th>
              <th>{t("rates")}</th>
              <th>{t("extra.columnTerms")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {fees.map((f) => (
              <tr key={f.id}>
                <td>{label(f.property_id)}</td>
                <td>{formatDate(f.start_date)}</td>
                <td>{formatDate(f.end_date)}</td>
                <td>{t(`intervals.${f.interval}`)}</td>
                <td>
                  {Object.entries(f.amounts_per_unit_type)
                    .map(([k, v]) => `${k}: ${formatEur(v)}`)
                    .join(", ")}
                </td>
                <td className="text-xs">
                  {f.termination_date ? <span className="block">{t("extra.terminatedOn", { date: formatDate(f.termination_date) })}</span> : null}
                  {f.due_day_rule ? (
                    <span className="block">
                      {t(`extra.dueRules.${f.due_day_rule}`)}
                      {f.due_day ? ` (${f.due_day})` : ""}
                    </span>
                  ) : null}
                  {f.sev_fee_amount ? <span className="block">{t("extra.sevFeeShort", { amount: formatEur(f.sev_fee_amount) })}</span> : null}
                </td>
                <td>
                  <button type="button" className={ui.buttonSm} onClick={() => endFee(f)} disabled={busy}>
                    {t("endFee")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("periodDate")}</span>
          <input type="date" className={ui.input} value={periodDate} onChange={(e) => setPeriodDate(e.target.value)} />
        </label>
      </div>
      <div className={ui.tableCard}>
        <table className="mhvp-table" data-testid="fee-periods">
          <thead>
            <tr>
              <th>{t("period")}</th>
              <th className="num">{t("gross")}</th>
              <th>{t("status")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {periods.map((row) => (
              <tr key={`${row.fee_setting_id}-${row.period_start}`}>
                <td>
                  {formatDate(row.period_start)} bis {formatDate(row.period_end)}
                </td>
                <td className="num">{formatEur(row.draft.gross)}</td>
                <td>{row.status === "issued" ? t("periodIssued", { number: row.number ?? "" }) : t("periodDue")}</td>
                <td>
                  {row.status === "due" ? (
                    <button type="button" className={ui.buttonSm} onClick={() => issue(row)} disabled={busy}>
                      {t("issue")}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className="text-sm font-semibold">{t("invoices")}</h2>
      <label className="flex items-center gap-2 text-sm">
        <span className={ui.label}>{t("statusFilter")}</span>
        <select className={ui.input} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} data-testid="fee-status-filter">
          <option value="">{t("allStatuses")}</option>
          {(["issued", "released", "cancelled"] as const).map((s) => (
            <option key={s} value={s}>
              {t(`statuses.${s}`)}
            </option>
          ))}
        </select>
      </label>
      <div className={ui.tableCard}>
        <table className="mhvp-table" data-testid="fee-invoices">
          <thead>
            <tr>
              <th>{t("number")}</th>
              <th>{t("date")}</th>
              <th>{t("period")}</th>
              <th className="num">{t("gross")}</th>
              <th>{t("status")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {invoices.map((inv) => (
              <tr key={inv.id}>
                <td>
                  {inv.number}
                  {inv.kind === "credit_note" ? ` (${t("creditNote")})` : ""}
                </td>
                <td>{formatDate(inv.invoice_date)}</td>
                <td>{inv.period_start ? `${formatDate(inv.period_start)} bis ${formatDate(inv.period_end)}` : ""}</td>
                <td className="num">{formatEur(inv.gross)}</td>
                <td>{inv.cancelled_at ? t("statusCancelled") : t(`statuses.${inv.status}`)}</td>
                <td className="flex flex-wrap gap-1">
                  {pdfs[inv.id] ? (
                    <a className={ui.buttonSm} href={`/api/handover-files/documents/${pdfs[inv.id]}/content`} download={`${inv.number}.pdf`}>
                      {t("pdfDownload")}
                    </a>
                  ) : (
                    <button type="button" className={ui.buttonSm} onClick={() => void makePdf(inv)} disabled={busy}>
                      {t("pdf")}
                    </button>
                  )}
                  {inv.payer_entry_id ? (
                    <span className="text-xs">{t("postingDraftsExist")}</span>
                  ) : inv.released_at ? (
                    <button type="button" className={ui.buttonSm} onClick={() => postingDrafts(inv)} disabled={busy}>
                      {t("postingDrafts")}
                    </button>
                  ) : null}
                  {inv.kind === "credit_note" && inv.status === "issued" ? (
                    <button type="button" className={ui.buttonSm} onClick={() => release(inv)} disabled={busy}>
                      {t("release")}
                    </button>
                  ) : null}
                  {inv.kind === "invoice" && !inv.cancelled_at ? (
                    <>
                      {inv.status === "issued" ? (
                        <button type="button" className={ui.buttonSm} onClick={() => release(inv)} disabled={busy}>
                          {t("release")}
                        </button>
                      ) : null}
                      <a className={ui.buttonSm} href={`${base}/invoices/${inv.id}/xrechnung.xml`}>
                        {t("xml")}
                      </a>
                      <button type="button" className={ui.buttonSm} onClick={() => check(inv)}>
                        {t("check")}
                      </button>
                      <button type="button" className={ui.buttonSm} onClick={() => store(inv)} disabled={busy}>
                        {t("store")}
                      </button>
                      <button type="button" className={ui.buttonSm} onClick={() => cancel(inv)} disabled={busy}>
                        {t("cancel")}
                      </button>
                    </>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
