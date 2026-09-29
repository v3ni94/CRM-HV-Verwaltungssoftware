"use client";
/** Reiter Dienstleister/Handwerker der Objektseite (Regel M11-08): alle Kreditoren des Objekts
 *  mit Gewerk, Kontaktdaten (Anruf, E-Mail), letzter Rechnung, noch nicht gebuchten Rechnungen
 *  und Anzahl Aufträge. Verknüpfen über die Kontaktsuche, Gewerk ändern, Verknüpfung lösen
 *  (der Kontakt bleibt), Filter nach Gewerk, Nachziehen aus vorhandenen Buchungen. Schreibrecht
 *  `properties:update`. Keine Zahlung, kein Geldbezug. */
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { ContactPicker, type ContactHit } from "./ContactPersonsPicker";

export type CreditorRow = {
  id: string;
  property_id: string;
  contact_id: string;
  contact_name: string;
  contact_roles: string[];
  trade: string | null;
  since: string | null;
  source: "proposal" | "manual" | "backfill";
  source_transaction_id: string | null;
  phone: string | null;
  email: string | null;
  last_invoice_date: string | null;
  last_invoice_amount: string | null;
  open_invoice_amount: string | null;
  work_orders_count: number;
};

export function PropertyCreditorsPanel({ propertyId, canEdit }: { propertyId: string; canEdit: boolean }) {
  const t = useTranslations("Properties.creditors");
  const [rows, setRows] = useState<CreditorRow[] | null>(null);
  const [filter, setFilter] = useState("");
  const [adding, setAdding] = useState(false);
  const [contact, setContact] = useState<ContactHit | null>(null);
  const [trade, setTrade] = useState("");
  const [editing, setEditing] = useState<{ id: string; trade: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<CreditorRow[]>(`/api/bff/properties/${propertyId}/creditors`);
    if (res.ok) setRows(res.data);
    else {
      setRows([]);
      setError(res.message);
    }
  }, [propertyId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(path: string, init: RequestInit, okMessage?: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<unknown>(path, init);
    setBusy(false);
    if (!res.ok) {
      setError(res.status === 403 ? t("noPermission") : res.message);
      return null;
    }
    if (okMessage) setMessage(okMessage);
    await load();
    return res.data;
  }

  async function add() {
    if (!contact) return;
    const ok = await act(`/api/bff/properties/${propertyId}/creditors`, {
      method: "POST",
      body: JSON.stringify({ contact_id: contact.id, trade: trade.trim() || null }),
    }, t("linked"));
    if (ok !== null) {
      setAdding(false);
      setContact(null);
      setTrade("");
    }
  }

  async function saveTrade() {
    if (!editing) return;
    const ok = await act(`/api/bff/properties/${propertyId}/creditors/${editing.id}`, {
      method: "PATCH",
      body: JSON.stringify({ trade: editing.trade.trim() || null }),
    }, t("saved"));
    if (ok !== null) setEditing(null);
  }

  async function unlink(row: CreditorRow) {
    if (!window.confirm(t("unlinkConfirm", { name: row.contact_name }))) return;
    await act(`/api/bff/properties/${propertyId}/creditors/${row.id}`, { method: "DELETE" }, t("unlinked"));
  }

  async function backfill() {
    const data = (await act("/api/bff/properties/creditors/backfill", {
      method: "POST",
      body: JSON.stringify({ property_id: propertyId }),
    })) as { created: number } | null;
    if (data) setMessage(t("backfilled", { count: data.created }));
  }

  const trades = useMemo(() => [...new Set((rows ?? []).map((r) => r.trade).filter((x): x is string => Boolean(x)))].sort((a, b) => a.localeCompare(b, "de")), [rows]);
  const visible = (rows ?? []).filter((r) => !filter || (r.trade ?? "").toLowerCase() === filter.toLowerCase());

  return (
    <section id="dienstleister" className={ui.card} data-testid="property-creditors" aria-label={t("title")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={ui.h2}>{t("title")}</h2>
        {canEdit ? (
          <div className="flex flex-wrap gap-2">
            <button type="button" className={ui.buttonSm} disabled={busy} onClick={backfill}>{t("backfill")}</button>
            <button type="button" className={ui.primary} onClick={() => setAdding((v) => !v)}>{adding ? t("cancel") : t("add")}</button>
          </div>
        ) : null}
      </div>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      {error ? <p role="alert" className={`${ui.alert} mt-2`}>{error}</p> : null}
      {message ? <p className={`${ui.success} mt-2`}>{message}</p> : null}
      {adding ? (
        <div className="mt-3 grid gap-3 sm:grid-cols-3" data-testid="creditor-add">
          <ContactPicker label={t("contact")} value={contact} onChange={setContact} testId="creditor-contact" />
          <label className={ui.label}>
            {t("trade")}
            <input className={ui.input} value={trade} onChange={(e) => setTrade(e.target.value)} placeholder={t("tradePlaceholder")} />
          </label>
          <div className={ui.formActions}>
            <button type="button" className={ui.primary} disabled={busy || !contact} onClick={add}>{t("link")}</button>
          </div>
        </div>
      ) : null}
      {trades.length > 0 ? (
        <label className={`${ui.label} mt-3 max-w-xs`}>
          {t("filterTrade")}
          <select className={ui.input} value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">{t("allTrades")}</option>
            {trades.map((x) => (
              <option key={x} value={x}>{x}</option>
            ))}
          </select>
        </label>
      ) : null}
      {rows === null ? <p className="mt-2 text-sm text-muted">{t("loading")}</p> : null}
      {rows && rows.length === 0 ? <p className="mt-2 text-sm text-muted">{t("empty")}</p> : null}
      {visible.length > 0 ? (
        <div className={`${ui.tableScroll} mt-3`}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("contact")}</th>
                <th>{t("trade")}</th>
                <th>{t("contactData")}</th>
                <th>{t("lastInvoice")}</th>
                <th>{t("openInvoices")}</th>
                <th>{t("workOrders")}</th>
                <th>{t("since")}</th>
                {canEdit ? <th>{t("actions")}</th> : null}
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link href={`/kontakte/${r.contact_id}`} className="hover:underline">{r.contact_name}</Link>
                    <span className="block text-xs text-muted">{t(`source.${r.source}`)}</span>
                  </td>
                  <td>
                    {editing?.id === r.id ? (
                      <span className="flex gap-1">
                        <input className={ui.input} value={editing.trade} aria-label={t("trade")} onChange={(e) => setEditing({ id: r.id, trade: e.target.value })} />
                        <button type="button" className={ui.buttonSm} disabled={busy} onClick={saveTrade}>{t("save")}</button>
                        <button type="button" className={ui.buttonSm} onClick={() => setEditing(null)}>{t("cancel")}</button>
                      </span>
                    ) : (
                      r.trade ?? <span className="text-muted">{t("noTrade")}</span>
                    )}
                  </td>
                  <td>
                    {r.phone ? <a href={`tel:${r.phone}`} className="block hover:underline">{r.phone}</a> : null}
                    {r.email ? <a href={`mailto:${r.email}`} className="block hover:underline">{r.email}</a> : null}
                    {!r.phone && !r.email ? <span className="text-muted">{t("noContactData")}</span> : null}
                  </td>
                  <td>{r.last_invoice_date ? `${formatDate(r.last_invoice_date)}, ${formatEur(r.last_invoice_amount)}` : t("none")}</td>
                  <td className="num">{r.open_invoice_amount ? formatEur(r.open_invoice_amount) : t("none")}</td>
                  <td className="num">{r.work_orders_count}</td>
                  <td>{r.since ? formatDate(r.since) : ""}</td>
                  {canEdit ? (
                    <td>
                      <span className="flex flex-wrap gap-1">
                        <button type="button" className={ui.buttonSm} onClick={() => setEditing({ id: r.id, trade: r.trade ?? "" })}>{t("editTrade")}</button>
                        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => unlink(r)}>{t("unlink")}</button>
                      </span>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {rows && rows.length > 0 && visible.length === 0 ? <p className="mt-2 text-sm text-muted">{t("noneForTrade")}</p> : null}
    </section>
  );
}
