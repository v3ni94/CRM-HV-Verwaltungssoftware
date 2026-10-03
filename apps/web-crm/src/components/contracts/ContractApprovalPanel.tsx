"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { centsToDecimal, sumCents } from "@/lib/money";
import { ui } from "@/lib/ui";

export type PendingContract = {
  id: string;
  number: string;
  kind: "tenancy" | "ownership";
  property_id: string;
  property_number: string;
  property_name: string;
  unit_id: string;
  unit_number: string;
  party_id: string;
  party_name: string;
  start_date: string;
  monthly_amount: string;
  source: string | null;
  notes: string | null;
};

type ApproveOut = { approved: number; ids: string[] };

/** Freigabe der Importverträge (Betreiberauftrag 26.09.2026): Verträge mit ausstehender Freigabe
 *  erzeugen im Sollstellungslauf keine Forderungen. Freigabe nur mit contracts:approve. */
export function ContractApprovalPanel({ initial, canApprove }: { initial: PendingContract[]; canApprove: boolean }) {
  const t = useTranslations("ContractApproval");
  const [rows, setRows] = useState(initial);
  const [source, setSource] = useState("");
  const [property, setProperty] = useState("");
  const [kind, setKind] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const sources = useMemo(() => [...new Set(rows.map((r) => r.source ?? ""))].sort(), [rows]);
  const properties = useMemo(
    () => [...new Map(rows.map((r) => [r.property_id, `${r.property_number} ${r.property_name}`])).entries()],
    [rows],
  );
  const visible = rows.filter(
    (r) =>
      (!source || (r.source ?? "") === source) &&
      (!property || r.property_id === property) &&
      (!kind || r.kind === kind),
  );
  const sums = (["ownership", "tenancy"] as const).map((k) => {
    const chosen = visible.filter((r) => r.kind === k);
    const cents = sumCents(chosen.map((r) => r.monthly_amount ?? "0")) ?? 0n;
    return { kind: k, count: chosen.length, amount: centsToDecimal(cents) };
  });
  const chosenIds = visible.filter((r) => selected.has(r.id)).map((r) => r.id);

  const drop = (ids: string[]) => {
    const gone = new Set(ids);
    setRows((prev) => prev.filter((r) => !gone.has(r.id)));
    setSelected((prev) => new Set([...prev].filter((id) => !gone.has(id))));
  };
  const approve = async (body: { ids: string[] } | { all: true; source?: string }, count: number) => {
    if (!window.confirm(t("confirmApprove", { count }))) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<ApproveOut>("/api/bff/contracts/approve", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) {
      drop(res.data.ids);
      setMessage(t("approved", { count: res.data.approved }));
    } else setError(res.message);
  };
  const reject = async (row: PendingContract) => {
    if (!window.confirm(t("confirmReject", { number: row.number, date: formatDate(row.start_date) }))) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff(`/api/bff/contracts/${row.id}/reject-import`, { method: "POST", body: JSON.stringify({}) });
    setBusy(false);
    if (res.ok) {
      drop([row.id]);
      setMessage(t("rejected", { number: row.number }));
    } else setError(res.message);
  };
  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const allChecked = visible.length > 0 && chosenIds.length === visible.length;

  return (
    <section className="flex flex-col gap-3">
      <p className={ui.notice}>{t("assumption")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("filters.source")}</span>
          <select className={ui.input} value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">{t("filters.all")}</option>
            {sources.map((s) => (
              <option key={s} value={s}>
                {s || t("noSource")}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("filters.property")}</span>
          <select className={ui.input} value={property} onChange={(e) => setProperty(e.target.value)}>
            <option value="">{t("filters.all")}</option>
            {properties.map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("filters.kind")}</span>
          <select className={ui.input} value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">{t("filters.all")}</option>
            <option value="ownership">{t("kinds.ownership")}</option>
            <option value="tenancy">{t("kinds.tenancy")}</option>
          </select>
        </label>
        {canApprove ? (
          <>
            <button
              type="button"
              className={ui.button}
              disabled={busy || chosenIds.length === 0}
              onClick={() => approve({ ids: chosenIds }, chosenIds.length)}
            >
              {t("approveSelected", { count: chosenIds.length })}
            </button>
            <button
              type="button"
              className={ui.primary}
              disabled={busy || rows.length === 0}
              onClick={() =>
                approve(source ? { all: true, source } : { all: true }, source ? rows.filter((r) => (r.source ?? "") === source).length : rows.length)
              }
            >
              {t("approveAll")}
            </button>
          </>
        ) : null}
      </div>
      <p className="text-sm" data-testid="approval-sums">
        {t("sumCount", { count: visible.length })}
        {sums.map((s) => ` · ${t(`kinds.${s.kind}`)}: ${s.count} (${formatEur(s.amount)} ${t("perMonth")})`).join("")}
      </p>
      {!canApprove ? <p className={ui.help}>{t("noPermission")}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className={ui.notice}>
          {message}
        </p>
      ) : null}
      {visible.length === 0 ? (
        <p className={ui.help}>{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                {canApprove ? (
                  <th>
                    <input
                      type="checkbox"
                      aria-label={t("selectAll")}
                      checked={allChecked}
                      onChange={() => setSelected(allChecked ? new Set() : new Set(visible.map((r) => r.id)))}
                    />
                  </th>
                ) : null}
                <th>{t("columns.property")}</th>
                <th>{t("columns.unit")}</th>
                <th>{t("columns.party")}</th>
                <th>{t("columns.kind")}</th>
                <th>{t("columns.start")}</th>
                <th className="num">{t("columns.monthly")}</th>
                <th>{t("columns.source")}</th>
                {canApprove ? <th /> : null}
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.id}>
                  {canApprove ? (
                    <td>
                      <input
                        type="checkbox"
                        aria-label={t("select", { number: r.number })}
                        checked={selected.has(r.id)}
                        onChange={() => toggle(r.id)}
                      />
                    </td>
                  ) : null}
                  <td>
                    {r.property_number} {r.property_name}
                  </td>
                  <td>{r.unit_number}</td>
                  <td>{r.party_name}</td>
                  <td>{t(`kinds.${r.kind}`)}</td>
                  <td>{formatDate(r.start_date)}</td>
                  <td className="num">{formatEur(r.monthly_amount)}</td>
                  <td className="text-muted">{r.source ?? t("noSource")}</td>
                  {canApprove ? (
                    <td>
                      <button type="button" className={ui.button} disabled={busy} onClick={() => reject(r)}>
                        {t("reject")}
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
