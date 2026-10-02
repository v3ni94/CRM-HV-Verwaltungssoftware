"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

const API = "/api/bff/imports/immoware24/history";
const KINDS = ["receivable", "credit", "deposit", "reserve", "loan", "special_levy"] as const;

export type HistoryItem = {
  id: string;
  kind: string;
  source_item_id: string;
  original_due_date: string | null;
  original_amount: string;
  paid_amount: string;
  open_amount: string;
  description: string | null;
};
export type HistorySummary = { ledger_id: string; kinds: Record<string, { count: number; original: string; paid: string; open: string }> };
export type HistoryTicket = { id: string; source_ticket_id: string; title: string; status_text: string | null; created_on: string; closed_on: string | null };

/** Nur lesende Ansicht der übernommenen Altdaten: Einzelposten je Buchungskreis (Summe offen je Art)
 *  und historische Tickets. Es wird nichts gebucht oder verändert. */
export function MigrationHistory({ ledgers, canTickets }: { ledgers: { id: string; name: string }[]; canTickets: boolean }) {
  const t = useTranslations("MigrationHistory");
  const [ledgerId, setLedgerId] = useState("");
  const [kind, setKind] = useState("");
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [tickets, setTickets] = useState<HistoryTicket[] | null>(null);
  const [summary, setSummary] = useState<HistorySummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadItems = async () => {
    setError(null);
    const q = new URLSearchParams({ ledger_id: ledgerId, limit: "100" });
    if (kind) q.set("kind", kind);
    const res = await bff<HistoryItem[]>(`${API}/open-items?${q.toString()}`);
    if (res.ok) setItems(res.data);
    else setError(res.message);
  };
  const loadSummary = async () => {
    setError(null);
    setSummary(null);
    const res = await bff<HistorySummary>(`${API}/open-items/summary?ledger_id=${encodeURIComponent(ledgerId)}`);
    if (res.ok) setSummary(res.data);
    else setError(res.message);
  };
  const loadTickets = async () => {
    setError(null);
    const res = await bff<HistoryTicket[]>(`${API}/tickets?limit=100`);
    if (res.ok) setTickets(res.data);
    else setError(res.message);
  };
  const openSum = (items ?? []).reduce((sum, i) => sum + Math.round(Number(i.open_amount) * 100), 0) / 100;

  return (
    <section className={ui.card} aria-label={t("title")}>
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <p className={ui.help}>{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-end">
        <label className="flex flex-1 flex-col gap-1">
          <span className={ui.label}>{t("ledger")}</span>
          <select className={ui.input} value={ledgerId} onChange={(e) => setLedgerId(e.target.value)}>
            <option value="">{t("chooseLedger")}</option>
            {ledgers.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("kindLabel")}</span>
          <select className={ui.input} value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">{t("allKinds")}</option>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`kind.${k}`)}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className={ui.buttonSm} disabled={!ledgerId} onClick={() => void loadItems()}>
          {t("loadItems")}
        </button>
        <button type="button" className={ui.buttonSm} disabled={!ledgerId} onClick={() => void loadSummary()}>
          {t("loadSummary")}
        </button>
        {canTickets ? (
          <button type="button" className={ui.buttonSm} onClick={() => void loadTickets()}>
            {t("loadTickets")}
          </button>
        ) : null}
      </div>
      {items ? (
        <div className="mt-2" data-testid="history-items">
          {items.length === 0 ? <p className={ui.help}>{t("none")}</p> : <p className="text-sm">{t("openSum", { count: items.length, sum: formatEur(String(openSum)) })}</p>}
          <div className={ui.tableScroll}>
            <table className={ui.table}>
              <tbody>
                {items.map((i) => (
                  <tr key={i.id}>
                    <td>{t(`kind.${i.kind as (typeof KINDS)[number]}`)}</td>
                    <td>{i.source_item_id}</td>
                    <td>{i.original_due_date ? formatDate(i.original_due_date) : ""}</td>
                    <td className="text-right">{formatEur(i.original_amount)}</td>
                    <td className="text-right">{formatEur(i.paid_amount)}</td>
                    <td className="text-right">{formatEur(i.open_amount)}</td>
                    <td>{i.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      {summary ? (
        <div className={`mt-2 ${ui.tableScroll}`} data-testid="history-summary">
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("kindLabel")}</th>
                <th className="text-right">{t("summaryCount")}</th>
                <th className="text-right">{t("summaryOriginal")}</th>
                <th className="text-right">{t("summaryPaid")}</th>
                <th className="text-right">{t("summaryOpen")}</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(summary.kinds).map(([k, v]) => (
                <tr key={k}>
                  <td>{KINDS.includes(k as (typeof KINDS)[number]) ? t(`kind.${k as (typeof KINDS)[number]}`) : k}</td>
                  <td className="text-right">{v.count}</td>
                  <td className="text-right">{formatEur(v.original)}</td>
                  <td className="text-right">{formatEur(v.paid)}</td>
                  <td className="text-right">{formatEur(v.open)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {tickets ? (
        <div className="mt-2" data-testid="history-tickets">
          {tickets.length === 0 ? <p className={ui.help}>{t("none")}</p> : null}
          <ul className="flex flex-col gap-1 text-sm">
            {tickets.map((k) => (
              <li key={k.id}>
                {formatDate(k.created_on)} {k.source_ticket_id} {k.title} {k.status_text ? `(${k.status_text})` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
