"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { MigrationHistory } from "./MigrationHistory";
import { useBusy } from "@/lib/use-busy";

const API = "/api/bff/imports/migration";

type Ledger = { id: string; name: string };
type Property = { property_id: string; property_number: string; property_name: string; ledgers: Ledger[] };
type Person = { name: string; role: string };
export type Acceptance = {
  id: string;
  status: string;
  review_scope: string;
  responsible_persons: Person[];
  non_migratable_data: string;
  fallback_plan: string;
  archive_concept: string;
  created_at: string;
  signed_at?: string | null;
};
type Columns = { columns: Record<string, string>; customised: boolean; fields: { name: string; label: string; required: boolean }[] };
type YearExpenses = {
  year: number;
  prior_period_total: string;
  later_period_total: string;
  total: string;
  prior_year_complete: boolean;
  accounts: { account_number: string; account_name: string; prior_period: string; later_period: string; total: string }[];
};

/** Migrationsabnahme je Objekt (6.9.10, V19), Spaltenzuordnung des Journal-Exports (M8) und
 *  Jahresausgaben je Buchungskreis. Unterzeichnen verlangt eine zweite Person (Vier-Augen-Prinzip,
 *  serverseitig geprüft); hier wird nichts gebucht. */
export function MigrationExtras({ canUpdate, canApprove, canTickets = false }: { canUpdate: boolean; canApprove: boolean; canTickets?: boolean }) {
  const { busy, guard } = useBusy();
  const t = useTranslations("MigrationExtras");
  const [properties, setProperties] = useState<Property[]>([]);
  const [propertyId, setPropertyId] = useState("");
  const [acceptances, setAcceptances] = useState<Acceptance[]>([]);
  const [form, setForm] = useState({ review_scope: "", persons: "", non_migratable_data: "", fallback_plan: "", archive_concept: "" });
  const [editId, setEditId] = useState<string | null>(null);
  const [columns, setColumns] = useState<Columns | null>(null);
  const [ledgerId, setLedgerId] = useState("");
  const [year, setYear] = useState(String(new Date().getFullYear() - 1));
  const [expenses, setExpenses] = useState<YearExpenses | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void bff<Property[]>(`${API}/status`).then((r) => r.ok && setProperties(r.data));
    void bff<Columns>(`${API}/journal-columns`).then((r) => r.ok && setColumns(r.data));
  }, []);

  const loadAcceptances = useCallback(async (id: string) => {
    if (!id) return setAcceptances([]);
    const res = await bff<Acceptance[]>(`${API}/properties/${id}/acceptance`);
    if (res.ok) setAcceptances(res.data);
    else setError(res.message);
  }, []);
  useEffect(() => {
    void loadAcceptances(propertyId);
  }, [propertyId, loadAcceptances]);

  const run = async (path: string, method: string, body: unknown, after: () => Promise<void>) => {
    setError(null);
    const res = await bff(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
    if (!res.ok) return setError(res.message);
    await after();
  };
  const persons = (): Person[] =>
    form.persons
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => {
        const [name = "", ...role] = l.split(",");
        return { name: name.trim(), role: role.join(",").trim() || "-" };
      });
  const emptyForm = { review_scope: "", persons: "", non_migratable_data: "", fallback_plan: "", archive_concept: "" };
  const saveAcceptance = () =>
    run(
      editId ? `${API}/acceptance/${editId}` : `${API}/properties/${propertyId}/acceptance`,
      editId ? "PUT" : "POST",
      { ...form, responsible_persons: persons(), persons: undefined },
      async () => {
        setForm(emptyForm);
        setEditId(null);
        await loadAcceptances(propertyId);
      },
    );
  const startEdit = (a: Acceptance) => {
    setEditId(a.id);
    setForm({
      review_scope: a.review_scope,
      persons: a.responsible_persons.map((p) => `${p.name}, ${p.role}`).join("\n"),
      non_migratable_data: a.non_migratable_data,
      fallback_plan: a.fallback_plan,
      archive_concept: a.archive_concept,
    });
  };
  const loadExpenses = async () => {
    setError(null);
    const res = await bff<YearExpenses>(`${API}/ledgers/${ledgerId}/year-expenses?year=${encodeURIComponent(year)}`);
    if (res.ok) setExpenses(res.data);
    else setError(res.message);
  };
  const ledgers = properties.find((p) => p.property_id === propertyId)?.ledgers ?? [];

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <section className={ui.card} aria-label={t("acceptanceTitle")}>
        <h2 className="text-sm font-semibold">{t("acceptanceTitle")}</h2>
        <p className={ui.help}>{t("acceptanceIntro")}</p>
        <label className="mt-2 flex max-w-md flex-col gap-1">
          <span className={ui.label}>{t("property")}</span>
          <select className={ui.input} value={propertyId} onChange={(e) => { setPropertyId(e.target.value); setLedgerId(""); setExpenses(null); }}>
            <option value="">{t("chooseProperty")}</option>
            {properties.map((p) => (
              <option key={p.property_id} value={p.property_id}>
                {p.property_number} {p.property_name}
              </option>
            ))}
          </select>
        </label>
        <ul className="mt-2 flex flex-col gap-2">
          {acceptances.map((a) => (
            <li key={a.id} className="rounded-md border border-line p-2 text-sm" data-testid="acceptance">
              <div className="flex flex-wrap items-center gap-2">
                <span className={a.status === "signed" ? ui.badgeSuccess : ui.badgeWarning}>{t(`status.${a.status}`)}</span>
                <span className={ui.help}>{formatDateTime(a.created_at)}</span>
                {a.status === "draft" && canUpdate ? (
                  <button type="button" className={ui.buttonSm} onClick={() => startEdit(a)}>
                    {t("edit")}
                  </button>
                ) : null}
                {a.status === "draft" && canApprove ? (
                  <button disabled={busy} type="button" className={ui.buttonSm} onClick={guard(() => run(`${API}/acceptance/${a.id}/sign`, "POST", {}, () => loadAcceptances(propertyId)))}>
                    {t("sign")}
                  </button>
                ) : null}
              </div>
              <p>{a.review_scope}</p>
              <p className={ui.help}>{a.responsible_persons.map((p) => `${p.name} (${p.role})`).join(", ")}</p>
            </li>
          ))}
        </ul>
        {propertyId && canUpdate ? (
          <form
            className="mt-3 flex flex-col gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void saveAcceptance();
            }}
          >
            {(["review_scope", "persons", "non_migratable_data", "fallback_plan", "archive_concept"] as const).map((k) => (
              <label key={k} className="flex flex-col gap-1">
                <span className={ui.label}>{t(`field.${k}`)}</span>
                <textarea className={ui.input} rows={k === "persons" ? 3 : 2} value={form[k]} onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))} />
              </label>
            ))}
            <button type="submit" className={ui.buttonSm} disabled={!form.review_scope.trim()}>
              {editId ? t("saveEdit") : t("create")}
            </button>
            {editId ? (
              <button disabled={busy} type="button" className={ui.buttonSm} onClick={() => { setEditId(null); setForm(emptyForm); }}>
                {t("cancelEdit")}
              </button>
            ) : null}
          </form>
        ) : null}
      </section>

      {columns ? (
        <section className={ui.card} aria-label={t("columnsTitle")}>
          <h2 className="text-sm font-semibold">{t("columnsTitle")}</h2>
          <p className={ui.help}>{columns.customised ? t("columnsCustom") : t("columnsDefault")}</p>
          <form
            className="mt-2 grid gap-2 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              void run(`${API}/journal-columns`, "PUT", { columns: columns.columns }, async () => undefined);
            }}
          >
            {columns.fields.map((f) => (
              <label key={f.name} className="flex flex-col gap-1">
                <span className={ui.label}>
                  {f.label}
                  {f.required ? " *" : ""}
                </span>
                <input
                  className={ui.input}
                  value={columns.columns[f.name] ?? ""}
                  disabled={!canUpdate}
                  onChange={(e) => setColumns({ ...columns, columns: { ...columns.columns, [f.name]: e.target.value } })}
                />
              </label>
            ))}
            {canUpdate ? (
              <button type="submit" className={ui.buttonSm}>
                {t("saveColumns")}
              </button>
            ) : null}
          </form>
        </section>
      ) : null}

      <section className={ui.card} aria-label={t("expensesTitle")}>
        <h2 className="text-sm font-semibold">{t("expensesTitle")}</h2>
        <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="flex flex-1 flex-col gap-1">
            <span className={ui.label}>{t("ledger")}</span>
            <select className={ui.input} value={ledgerId} onChange={(e) => setLedgerId(e.target.value)}>
              <option value="">{propertyId ? t("chooseLedger") : t("chooseProperty")}</option>
              {ledgers.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("year")}</span>
            <input className={ui.input} inputMode="numeric" value={year} onChange={(e) => setYear(e.target.value)} />
          </label>
          <button type="button" className={ui.buttonSm} disabled={busy || (!ledgerId || !/^\d{4}$/.test(year))} onClick={guard(() => loadExpenses())}>
            {t("load")}
          </button>
        </div>
        {expenses ? (
          <div className="mt-2" data-testid="year-expenses">
            {!expenses.prior_year_complete ? <p className={ui.warning}>{t("priorIncomplete")}</p> : null}
            <p className="text-sm">
              {t("totals", { prior: formatEur(expenses.prior_period_total), later: formatEur(expenses.later_period_total), total: formatEur(expenses.total) })}
            </p>
            <div className={ui.tableScroll}>
              <table className={ui.table}>
                <tbody>
                  {expenses.accounts.map((a) => (
                    <tr key={a.account_number}>
                      <td>{a.account_number} {a.account_name}</td>
                      <td className="text-right">{formatEur(a.prior_period)}</td>
                      <td className="text-right">{formatEur(a.later_period)}</td>
                      <td className="text-right">{formatEur(a.total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </section>
      <MigrationHistory ledgers={ledgers} canTickets={canTickets} />
    </div>
  );
}
