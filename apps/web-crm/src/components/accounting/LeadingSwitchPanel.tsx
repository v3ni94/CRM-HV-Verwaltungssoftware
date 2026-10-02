"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

const KINDS = ["receivable_posting", "dunning", "direct_debit", "payment_order"] as const;
type Kind = (typeof KINDS)[number];
type Effective = { kind: Kind; leading_system: string; source: "switch" | "ledger" };
type SwitchRow = {
  id: string;
  kind: Kind;
  leading_system: string;
  valid_from: string;
  property_id: string | null;
  status: "requested" | "approved" | "rejected";
  comment: string | null;
};
type State = { items: SwitchRow[]; effective: Effective[]; ledger_leading_system: string };
type PropertyOption = { id: string; label: string };

/** Leading system per process kind (13.1 Ergänzung, GAC-05): read view with effective system
 *  and source, request of a switch and decision by a second person (G1 for the platform). */
export function LeadingSwitchPanel({
  ledgerId,
  canApprove,
  properties,
  today,
}: {
  ledgerId: string;
  canApprove: boolean;
  properties: PropertyOption[];
  today: string;
}) {
  const t = useTranslations("Bookkeeping.leadingSwitch");
  const url = `/api/bff/accounting/ledgers/${ledgerId}/leading-switches`;
  const [state, setState] = useState<State | null>(null);
  const [form, setForm] = useState({ kind: "dunning" as Kind, leading_system: "mhvp", valid_from: today, property_id: "", comment: "" });
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const res = await bff<State>(url);
    if (res.ok) setState(res.data);
  }, [url]);

  useEffect(() => {
    void load();
  }, [load]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const body = {
      kind: form.kind,
      leading_system: form.leading_system,
      valid_from: form.valid_from,
      property_id: form.property_id || null,
      comment: form.comment || null,
    };
    setBusy(true);
    const res = await bff<SwitchRow>(url, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    setMessage(res.ok ? { ok: true, text: t("requested") } : { ok: false, text: res.message });
    if (res.ok) await load();
  };

  const decide = async (id: string, approve: boolean) => {
    if (busy) return;
    setBusy(true);
    const res = await bff<SwitchRow>(`${url}/${id}/decide`, { method: "POST", body: JSON.stringify({ approve }) });
    setBusy(false);
    setMessage(res.ok ? { ok: true, text: t("decided") } : { ok: false, text: res.message });
    if (res.ok) await load();
  };

  const propertyLabel = (id: string | null) => (id ? (properties.find((p) => p.id === id)?.label ?? id) : t("allProperties"));

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("title")}>
      <h3 className="text-sm font-semibold">{t("title")}</h3>
      <p className={ui.help}>{t("help")}</p>
      <div className={ui.tableScroll}>
      <table className={ui.table}>
        <thead>
          <tr>
            <th>{t("kind")}</th>
            <th>{t("leading")}</th>
            <th>{t("source")}</th>
          </tr>
        </thead>
        <tbody>
          {(state?.effective ?? []).map((e) => (
            <tr key={e.kind}>
              <td>{t(`kinds.${e.kind}`)}</td>
              <td>{t(`systems.${e.leading_system}`)}</td>
              <td>{e.source === "switch" ? t("sourceSwitch") : t("sourceLedger")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <h4 className="text-sm font-semibold">{t("history")}</h4>
      {state && state.items.length === 0 ? <p className={ui.help}>{t("empty")}</p> : null}
      {state && state.items.length > 0 ? (
        <div className={ui.tableScroll}>
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("kind")}</th>
              <th>{t("leading")}</th>
              <th>{t("validFrom")}</th>
              <th>{t("property")}</th>
              <th>{t("status")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {state.items.map((row) => (
              <tr key={row.id}>
                <td>{t(`kinds.${row.kind}`)}</td>
                <td>{t(`systems.${row.leading_system}`)}</td>
                <td>{formatDate(row.valid_from)}</td>
                <td>{propertyLabel(row.property_id)}</td>
                <td>{t(`statuses.${row.status}`)}</td>
                <td>
                  {canApprove && row.status === "requested" ? (
                    <span className="flex gap-2">
                      <button type="button" className={ui.secondary} disabled={busy} onClick={() => void decide(row.id, true)}>
                        {t("approve")}
                      </button>
                      <button type="button" className={ui.secondary} disabled={busy} onClick={() => void decide(row.id, false)}>
                        {t("reject")}
                      </button>
                    </span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      ) : null}
      {canApprove ? (
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3" aria-label={t("request")}>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("kind")}</span>
            <select className={ui.input} value={form.kind} onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value as Kind }))}>
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {t(`kinds.${k}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("leading")}</span>
            <select className={ui.input} value={form.leading_system} onChange={(e) => setForm((f) => ({ ...f, leading_system: e.target.value }))}>
              <option value="mhvp">{t("systems.mhvp")}</option>
              <option value="immoware24">{t("systems.immoware24")}</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("validFrom")}</span>
            <input type="date" required className={ui.input} value={form.valid_from} onChange={(e) => setForm((f) => ({ ...f, valid_from: e.target.value }))} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("property")}</span>
            <select className={ui.input} value={form.property_id} onChange={(e) => setForm((f) => ({ ...f, property_id: e.target.value }))}>
              <option value="">{t("allProperties")}</option>
              {properties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={ui.label}>{t("comment")}</span>
            <input className={ui.input} value={form.comment} maxLength={2000} onChange={(e) => setForm((f) => ({ ...f, comment: e.target.value }))} />
          </label>
          <div className={ui.formActions}>
            <button type="submit" className={ui.primary} disabled={busy}>
              {t("request")}
            </button>
          </div>
        </form>
      ) : null}
      {message ? (
        <p role={message.ok ? "status" : "alert"} className={message.ok ? ui.success : ui.error}>
          {message.text}
        </p>
      ) : null}
    </section>
  );
}
