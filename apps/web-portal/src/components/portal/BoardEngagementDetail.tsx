"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { BoardEngagementDetail as Detail, BoardReport } from "@/components/portal/types";
import { filterQuery } from "@/lib/audit-filter";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const STATUS = new Set(["open", "checked", "query", "objection", "outdated"]);
const SAMPLING = new Set(["sample", "full"]);
const KINDS = new Set(["note", "question", "answered"]);

function amount(value: string | null): string {
  if (value === null) return "";
  return `${new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value))} EUR`;
}

/** Prüfungsraum eines Prüfauftrags (7.9.2 PÜ07, PÜ08, A52): Positionen mit Prüfstatus (A77:
 *  serverseitig gefiltert nach Konto, Lieferant, Datum und Text über die Adresse der Seite),
 *  Belege (nur die freigegebenen Belege des Prüfauftrags), Vermerke und Rückfragen des Beirats
 *  mit den Antworten der Verwaltung sowie die Prüfberichte mit der Stellungnahme des Beirats
 *  (A76, nur Text, keine Freigabewirkung). Der Beirat bucht nichts, gibt nichts frei und ändert
 *  keine Abrechnung. */
export function BoardEngagementDetail({ detail, reports = [] }: { detail: Detail; reports?: BoardReport[] }) {
  const t = useTranslations("Audit");
  const format = useFormatter();
  const router = useRouter();
  const filter = detail.filter ?? { account_id: null, vendor_contact_id: null, date_from: null, date_to: null, q: null };
  const options = detail.filter_options ?? { accounts: [], vendors: [] };
  const [accountId, setAccountId] = useState(filter.account_id ?? "");
  const [vendorId, setVendorId] = useState(filter.vendor_contact_id ?? "");
  const [dateFrom, setDateFrom] = useState(filter.date_from ?? "");
  const [dateTo, setDateTo] = useState(filter.date_to ?? "");
  const [query, setQuery] = useState(filter.q ?? "");
  const filterActive = Boolean(filter.account_id || filter.vendor_contact_id || filter.date_from || filter.date_to || filter.q);
  const total = detail.positions_total ?? detail.positions.length;
  const [kind, setKind] = useState<"note" | "question">("question");
  const [text, setText] = useState("");
  const [itemId, setItemId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const date = (value: string | null) =>
    value ? format.dateTime(new Date(value), { day: "2-digit", month: "2-digit", year: "numeric" }) : "";
  const positionLabel = (id: string | null) => {
    if (!id) return t("wholeEngagement");
    const index = detail.positions.findIndex((p) => p.id === id);
    return index >= 0 ? t("positionNumber", { n: index + 1 }) : t("wholeEngagement");
  };

  function applyFilter(event: React.FormEvent) {
    event.preventDefault();
    router.push(
      `/pruefung/${detail.id}${filterQuery({ account_id: accountId, vendor_contact_id: vendorId, date_from: dateFrom, date_to: dateTo, q: query })}`,
    );
  }

  function resetFilter() {
    setAccountId("");
    setVendorId("");
    setDateFrom("");
    setDateTo("");
    setQuery("");
    router.push(`/pruefung/${detail.id}`);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (text.trim().length === 0) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    const result = await bff(`/api/bff/portal/board/engagements/${detail.id}/notes`, {
      method: "POST",
      body: JSON.stringify({ kind, text: text.trim(), audit_item_id: itemId || null }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setText("");
    setNotice(kind === "question" ? t("questionSent") : t("noteSaved"));
    router.refresh();
  }

  return (
    <div className={ui.pageGap}>
      <div className={`${ui.card} flex flex-col gap-1`}>
        <h1 className={ui.title}>{detail.legal_entity_name ?? detail.legal_entity_id}</h1>
        <p className="text-sm text-muted">{detail.purpose}</p>
        <p className="text-xs text-subtle">
          {t("period")} {t("periodRange", { from: date(detail.period_from), to: date(detail.period_to) })} ·{" "}
          {SAMPLING.has(detail.sampling) ? t(`sampling.${detail.sampling}`) : detail.sampling}
        </p>
        <p className="text-sm">
          {t("overallStatus")}:{" "}
          <span className={ui.badge}>{STATUS.has(detail.overall_status) ? t(`status.${detail.overall_status}`) : detail.overall_status}</span>
        </p>
      </div>
      <p className={ui.notice}>{t("roleNotice")}</p>

      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("positions")}</h2>
        <form onSubmit={applyFilter} noValidate className={`${ui.card} flex flex-col gap-3`} aria-label={t("filter.label")}>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="filter-account" className={ui.label}>
                {t("filter.account")}
              </label>
              <select id="filter-account" className={ui.input} value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                <option value="">{t("filter.all")}</option>
                {options.accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.number} {a.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="filter-vendor" className={ui.label}>
                {t("filter.vendor")}
              </label>
              <select id="filter-vendor" className={ui.input} value={vendorId} onChange={(e) => setVendorId(e.target.value)}>
                <option value="">{t("filter.all")}</option>
                {options.vendors.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="filter-from" className={ui.label}>
                {t("filter.dateFrom")}
              </label>
              <input id="filter-from" type="date" className={ui.input} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </div>
            <div>
              <label htmlFor="filter-to" className={ui.label}>
                {t("filter.dateTo")}
              </label>
              <input id="filter-to" type="date" className={ui.input} value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </div>
            <div className="sm:col-span-2">
              <label htmlFor="filter-q" className={ui.label}>
                {t("filter.text")}
              </label>
              <input id="filter-q" type="search" className={ui.input} value={query} maxLength={200} onChange={(e) => setQuery(e.target.value)} />
            </div>
          </div>
          <div className={ui.formActions}>
            <button type="submit" className={`${ui.button} ${ui.actionFull}`}>
              {t("filter.apply")}
            </button>
            {filterActive ? (
              <button type="button" className={`${ui.secondary} ${ui.actionFull}`} onClick={resetFilter}>
                {t("filter.reset")}
              </button>
            ) : null}
          </div>
          <p className={ui.help} role="status">
            {filterActive ? t("filter.result", { shown: detail.positions.length, total }) : t("filter.unfiltered", { total })}
          </p>
        </form>
        {detail.positions.length === 0 ? <p className={ui.help}>{filterActive ? t("filter.noMatch") : t("noPositions")}</p> : null}
        <ul className="flex flex-col gap-2">
          {detail.positions.map((p, index) => (
            <li key={p.id} className={`${ui.card} flex flex-col gap-1`}>
              <span className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">
                  {t("positionNumber", { n: index + 1 })}
                  {p.booking_text ? `: ${p.booking_text}` : ""}
                </span>
                <span className={ui.badge}>{STATUS.has(p.status) ? t(`status.${p.status}`) : p.status}</span>
              </span>
              <span className="text-sm text-muted">
                {p.booking_date ? `${date(p.booking_date)} · ` : ""}
                <span className="whitespace-nowrap">{amount(p.amount)}</span>
                {p.booking_reference ? ` · ${p.booking_reference}` : ""}
              </span>
              {(p.accounts && p.accounts.length > 0) || p.vendor_name ? (
                <span className="text-xs text-subtle">
                  {p.accounts && p.accounts.length > 0 ? `${t("filter.account")}: ${p.accounts.map((a) => a.number).join(", ")}` : ""}
                  {p.accounts && p.accounts.length > 0 && p.vendor_name ? " · " : ""}
                  {p.vendor_name ? `${t("filter.vendor")}: ${p.vendor_name}` : ""}
                </span>
              ) : null}
              {p.outdated_reason ? <span className={ui.alert}>{p.outdated_reason}</span> : null}
              {p.note ? <span className="text-sm">{t("managementNote")}: {p.note}</span> : null}
              {p.question ? <span className="text-sm">{t("managementQuestion")}: {p.question}</span> : null}
              {p.answer ? <span className="text-sm">{t("managementAnswer")}: {p.answer}</span> : null}
            </li>
          ))}
        </ul>
      </section>

      {detail.cost_items.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h2 className={ui.h2}>{t("costItems")}</h2>
          <div className={ui.tableScroll}>
            <table className={ui.table}>
              <caption className="sr-only">{t("costTableCaption")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("costLabel")}</th>
                  <th scope="col">{t("costBasis")}</th>
                  <th scope="col" className="num">
                    {t("costAmount")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {detail.cost_items.map((c) => (
                  <tr key={c.id}>
                    <td>{c.label}</td>
                    <td>{c.basis}</td>
                    <td className="num whitespace-nowrap">{amount(c.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("documents")}</h2>
        {detail.documents.length === 0 ? <p className={ui.help}>{t("noDocuments")}</p> : null}
        <ul className="flex flex-col gap-2">
          {detail.documents.map((d) => (
            <li key={d.id} className={`${ui.card} flex flex-wrap items-center justify-between gap-2`}>
              <span className="flex flex-col gap-0.5">
                <span className="font-medium">{d.title}</span>
                <span className="text-xs text-subtle">{positionLabel(d.audit_item_id)}</span>
              </span>
              <a
                href={`/api/portal-files/portal/board/engagements/${detail.id}/documents/${d.id}`}
                className={ui.buttonSm}
                target="_blank"
                rel="noreferrer"
              >
                {t("open")}
              </a>
            </li>
          ))}
        </ul>
        <p className={ui.help}>{detail.read_receipt_note}</p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("notes")}</h2>
        {detail.notes.length === 0 ? <p className={ui.help}>{t("noNotes")}</p> : null}
        <ul className="flex flex-col gap-2">
          {detail.notes.map((n) => (
            <li key={n.id} className={`${ui.card} flex flex-col gap-1`}>
              <span className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs text-subtle">
                  {date(n.created_at)} · {positionLabel(n.audit_item_id)}
                </span>
                <span className={ui.badge}>{KINDS.has(n.kind) ? t(`kind.${n.kind}`) : n.kind}</span>
              </span>
              <span className="text-sm">{n.text}</span>
              {n.answer ? (
                <span className="text-sm text-muted">
                  {t("managementAnswer")} ({date(n.answered_at)}): {n.answer}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("reports.title")}</h2>
        <p className={ui.help}>{t("reports.notice")}</p>
        {reports.length === 0 ? <p className={ui.help}>{t("reports.empty")}</p> : null}
        <ul className="flex flex-col gap-2">
          {reports.map((r) => (
            <li key={r.id}>
              <ReportCard report={r} engagementId={detail.id} />
            </li>
          ))}
        </ul>
      </section>

      <form onSubmit={submit} noValidate aria-busy={busy} className={`${ui.card} flex flex-col gap-3`}>
        <h2 className={ui.h2}>{t("newNote")}</h2>
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {notice ? (
        <p role="status" className={ui.success}>
          {notice}
        </p>
      ) : null}
        <div>
          <label htmlFor="note-kind" className={ui.label}>
            {t("kindLabel")}
          </label>
          <select id="note-kind" className={ui.input} value={kind} onChange={(e) => setKind(e.target.value as "note" | "question")}>
            <option value="question">{t("kind.question")}</option>
            <option value="note">{t("kind.note")}</option>
          </select>
        </div>
        <div>
          <label htmlFor="note-position" className={ui.label}>
            {t("positionLabel")}
          </label>
          <select id="note-position" className={ui.input} value={itemId} onChange={(e) => setItemId(e.target.value)}>
            <option value="">{t("wholeEngagement")}</option>
            {detail.positions.map((p, index) => (
              <option key={p.id} value={p.id}>
                {t("positionNumber", { n: index + 1 })}
                {p.booking_text ? `: ${p.booking_text}` : ""}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="note-text" className={ui.label}>
            {t("textLabel")}
          </label>
          <textarea
            id="note-text"
            rows={4}
            className={ui.input}
            aria-required="true"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <button type="submit" className={`${ui.button} ${ui.actionFull}`} disabled={busy || text.trim().length === 0}>
          {t("submit")}
        </button>
      </form>
    </div>
  );
}

/** One report version with the board statement (A76): existing text with time, the history
 *  count, and the form to record or replace the statement. Text only, no release effect. */
function ReportCard({ report, engagementId }: { report: BoardReport; engagementId: string }) {
  const t = useTranslations("Audit");
  const format = useFormatter();
  const router = useRouter();
  const [text, setText] = useState(report.board_statement?.text ?? "");
  const [editing, setEditing] = useState(report.board_statement === null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dateTime = (value: string | null | undefined) =>
    value
      ? format.dateTime(new Date(value), { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
      : "";
  const day = (value: string | null | undefined) =>
    value ? format.dateTime(new Date(value), { day: "2-digit", month: "2-digit", year: "numeric" }) : "";
  const c = report.content;
  const textId = `statement-${report.id}`;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (text.trim().length === 0) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    const result = await bff(`/api/bff/portal/board/engagements/${engagementId}/reports/${report.id}/statement`, {
      method: "POST",
      body: JSON.stringify({ text: text.trim() }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setNotice(t("reports.statementSaved"));
    setEditing(false);
    router.refresh();
  }

  return (
    <article className={`${ui.card} flex flex-col gap-2`} aria-labelledby={`report-${report.id}`}>
      <span className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={`report-${report.id}`} className="font-medium">
          {t("reports.version", { n: report.version })}
        </h3>
        <span className="text-xs text-subtle">{day(c.date ?? report.created_at)}</span>
      </span>
      {c.overall_status ? (
        <span className="text-sm">
          {t("overallStatus")}: <span className={ui.badge}>{c.overall_status}</span>
        </span>
      ) : null}
      {c.scope_note ? <span className="text-xs text-subtle">{c.scope_note}</span> : null}
      {c.checked_count !== null && c.checked_count !== undefined ? (
        <span className="text-sm text-muted">
          {t("reports.figures", {
            checked: c.checked_count,
            unchecked: c.unchecked_count ?? 0,
            checkedValue: amount(c.checked_value ?? null),
            uncheckedValue: amount(c.unchecked_value ?? null),
          })}
        </span>
      ) : null}
      {c.findings ? (
        <span className="text-sm">
          {t("reports.findings")}: {c.findings}
        </span>
      ) : null}
      {c.recommendation ? (
        <span className="text-sm">
          {t("reports.recommendation")}: {c.recommendation}
        </span>
      ) : null}
      <div className="flex flex-col gap-1 border-t border-border pt-2">
        <span className="text-sm font-medium">{t("reports.statement")}</span>
        {report.board_statement ? (
          <blockquote className="whitespace-pre-line rounded-md bg-surface px-3 py-2 text-sm">{report.board_statement.text}</blockquote>
        ) : (
          <span className={ui.help}>{t("reports.noStatement")}</span>
        )}
        {report.board_statement ? (
          <span className="text-xs text-subtle">
            {t("reports.recordedAt", { at: dateTime(report.board_statement.recorded_at) })}
            {report.board_statement.source === "portal" ? ` · ${t("reports.sourcePortal")}` : ` · ${t("reports.sourceCrm")}`}
            {report.board_statement_history.length > 0
              ? ` · ${t("reports.history", { count: report.board_statement_history.length })}`
              : ""}
          </span>
        ) : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {notice ? (
          <p role="status" className={ui.success}>
            {notice}
          </p>
        ) : null}
        {editing ? (
          <form onSubmit={submit} noValidate aria-busy={busy} className="flex flex-col gap-2">
            <label htmlFor={textId} className={ui.label}>
              {t("reports.statementLabel")}
            </label>
            <textarea id={textId} rows={4} className={ui.input} maxLength={8000} aria-required="true" value={text} onChange={(e) => setText(e.target.value)} />
            <p className={ui.help}>{t("reports.statementHint")}</p>
            <div className={ui.formActions}>
              <button type="submit" className={`${ui.button} ${ui.actionFull}`} disabled={busy || text.trim().length === 0}>
                {t("reports.saveStatement")}
              </button>
              {report.board_statement ? (
                <button type="button" className={`${ui.secondary} ${ui.actionFull}`} onClick={() => setEditing(false)}>
                  {t("reports.cancel")}
                </button>
              ) : null}
            </div>
          </form>
        ) : (
          <div className={ui.formActions}>
            <button type="button" className={`${ui.buttonSm}`} onClick={() => setEditing(true)}>
              {t("reports.replaceStatement")}
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
