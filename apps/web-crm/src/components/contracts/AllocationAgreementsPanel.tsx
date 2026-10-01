"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Agreement = {
  id: string;
  operating_cost_type: string;
  operating_cost_label: string | null;
  status: "agreed" | "excluded";
  clause_reference: string | null;
  valid_from: string;
  valid_to: string | null;
};
type CatalogueEntry = { code: string; label: string };

/** Allocation agreements of a tenancy per cost position (M17-01, AE17): clause reference and
 *  validity. The bulk entry applies one clause to all tenancies of the property; it previews
 *  first and never overwrites an existing agreement. */
export function AllocationAgreementsPanel({
  contractId,
  propertyId,
  canUpdate,
}: {
  contractId: string;
  propertyId: string;
  canUpdate: boolean;
}) {
  const t = useTranslations("Billing.allocationBasis");
  const base = `/api/bff/contracts/${contractId}/allocation-agreements`;
  const [rows, setRows] = useState<Agreement[]>([]);
  const [catalogue, setCatalogue] = useState<CatalogueEntry[]>([]);
  const [code, setCode] = useState("");
  const [status, setStatus] = useState<"agreed" | "excluded">("agreed");
  const [clause, setClause] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [bulk, setBulk] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<{ items: Agreement[] }>(base);
    if (res.ok) setRows(res.data.items);
    else setError(res.message);
  }, [base]);

  useEffect(() => {
    void load();
    void bff<CatalogueEntry[] | { items: CatalogueEntry[] }>("/api/bff/billing/operating-cost-types").then((res) => {
      if (res.ok) setCatalogue(Array.isArray(res.data) ? res.data : res.data.items);
    });
  }, [load]);

  async function submit(dryRun: boolean) {
    setError(null);
    setMessage(null);
    const common = { status, clause_reference: clause || null, valid_from: from, valid_to: to || null };
    if (bulk) {
      const res = await bff<{ created: number; skipped: number; dry_run: boolean }>(
        `/api/bff/properties/${propertyId}/allocation-agreements/bulk`,
        {
          method: "POST",
          body: JSON.stringify({
            items: [{ operating_cost_type: code, status, clause_reference: clause || null }],
            valid_from: from,
            valid_to: to || null,
            dry_run: dryRun,
          }),
        },
      );
      if (!res.ok) return setError(res.message);
      setMessage(t(dryRun ? "bulkPreview" : "bulkDone", { created: res.data.created, skipped: res.data.skipped }));
      if (!dryRun) await load();
      return;
    }
    const res = await bff(base, { method: "POST", body: JSON.stringify({ operating_cost_type: code, ...common }) });
    if (!res.ok) return setError(res.message);
    setClause("");
    await load();
  }

  async function remove(id: string) {
    const res = await bff(`${base}/${id}`, { method: "DELETE" });
    if (!res.ok) return setError(res.message);
    await load();
  }

  return (
    <section className={ui.card} aria-label={t("agreementsTitle")}>
      <h2 className={ui.h2}>{t("agreementsTitle")}</h2>
      <p className={ui.help}>{t("agreementsNotice")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {rows.length === 0 ? <p className={`${ui.help} mt-2`}>{t("agreementsNone")}</p> : null}
      <ul className="mt-2 flex flex-col gap-1">
        {rows.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-2 text-sm">
            <span className={r.status === "agreed" ? ui.badge : ui.badgeWarning}>{t(`status.${r.status}`)}</span>
            <span>
              {r.operating_cost_label ?? r.operating_cost_type}, {r.clause_reference ?? "-"}, {formatDate(r.valid_from)}
              {r.valid_to ? ` bis ${formatDate(r.valid_to)}` : ""}
            </span>
            {canUpdate ? (
              <button type="button" className={ui.button} onClick={() => void remove(r.id)}>
                {t("remove")}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      {canUpdate ? (
        <form
          className="mt-3 grid gap-2 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            void submit(bulk);
          }}
        >
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("type")}</span>
            <select className={ui.input} value={code} onChange={(e) => setCode(e.target.value)} required>
              <option value="" />
              {catalogue.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("statusLabel")}</span>
            <select className={ui.input} value={status} onChange={(e) => setStatus(e.target.value as "agreed" | "excluded")}>
              <option value="agreed">{t("status.agreed")}</option>
              <option value="excluded">{t("status.excluded")}</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={ui.label}>{t("clause")}</span>
            <input className={ui.input} value={clause} onChange={(e) => setClause(e.target.value)} required={status === "agreed"} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("validFrom")}</span>
            <input type="date" className={ui.input} value={from} onChange={(e) => setFrom(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("validTo")}</span>
            <input type="date" className={ui.input} value={to} onChange={(e) => setTo(e.target.value)} />
          </label>
          <label className="flex items-center gap-2 text-sm sm:col-span-2">
            <input type="checkbox" checked={bulk} onChange={(e) => setBulk(e.target.checked)} />
            {t("bulk")}
          </label>
          <div className="flex gap-2 sm:col-span-2">
            <button type="submit" className={ui.button}>
              {bulk ? t("bulkPreviewButton") : t("add")}
            </button>
            {bulk ? (
              <button type="button" className={ui.button} onClick={() => void submit(false)}>
                {t("bulkApply")}
              </button>
            ) : null}
          </div>
          {message ? <p className={ui.help}>{message}</p> : null}
        </form>
      ) : null}
    </section>
  );
}
