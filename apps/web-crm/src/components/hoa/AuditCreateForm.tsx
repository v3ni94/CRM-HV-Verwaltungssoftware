"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ContactPicker, type PickedContact } from "@/components/hoa/ContactPicker";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type AuditStatementOption = { id: string; label: string };
export type AuditAccountOption = { id: string; number: string; name: string };

/** Prüfauftrag anlegen (PÜ06, A72) on the WEG page: period, purpose, sampling, optional
 *  statement reference, population accounts and the auditors (board contacts). Creates the
 *  engagement through POST /hoa/audits and opens it; the positions are then selected on the
 *  engagement page with the filters of PÜ08. */
export function AuditCreateForm({
  legalEntityId,
  statements,
  accounts,
  basePath,
}: {
  legalEntityId: string;
  statements: AuditStatementOption[];
  accounts: AuditAccountOption[];
  basePath: string;
}) {
  const t = useTranslations("HoaWork");
  const router = useRouter();
  const year = new Date().getFullYear() - 1;
  const [open, setOpen] = useState(false);
  const [periodFrom, setPeriodFrom] = useState(`${year}-01-01`);
  const [periodTo, setPeriodTo] = useState(`${year}-12-31`);
  const [purpose, setPurpose] = useState("");
  const [sampling, setSampling] = useState<"sample" | "full">("sample");
  const [statementId, setStatementId] = useState("");
  const [accountNumbers, setAccountNumbers] = useState<string[]>([]);
  const [auditors, setAuditors] = useState<PickedContact[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (auditors.length === 0) {
      setError(t("audit.create.needAuditor"));
      return;
    }
    setBusy(true);
    setError(null);
    const body = {
      legal_entity_id: legalEntityId,
      period_from: periodFrom,
      period_to: periodTo,
      purpose: purpose.trim(),
      sampling,
      statement_id: statementId || null,
      accounts: accountNumbers,
      auditor_contact_ids: auditors.map((a) => a.id),
    };
    const res = await bff<{ id: string }>("/api/bff/hoa/audits", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    router.push(`${basePath}/pruefung/${res.data.id}`);
  }

  if (!open) {
    return (
      <div>
        <button type="button" className={ui.button} onClick={() => setOpen(true)}>
          {t("audit.create.open")}
        </button>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className={`${ui.card} flex flex-col gap-3`} data-testid="audit-create">
      <p className={ui.help}>{t("audit.create.hint")}</p>
      <div className="flex flex-wrap gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("audit.create.periodFrom")}</span>
          <input className={ui.input} type="date" required value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("audit.create.periodTo")}</span>
          <input className={ui.input} type="date" required value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("audit.create.sampling")}</span>
          <select className={ui.input} value={sampling} onChange={(e) => setSampling(e.target.value as "sample" | "full")}>
            <option value="sample">{t("audit.sampling.sample")}</option>
            <option value="full">{t("audit.sampling.full")}</option>
          </select>
        </label>
      </div>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("audit.create.purpose")}</span>
        <input className={ui.input} required minLength={3} value={purpose} onChange={(e) => setPurpose(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("audit.create.statement")}</span>
        <select className={ui.input} value={statementId} onChange={(e) => setStatementId(e.target.value)}>
          <option value="">{t("audit.create.noStatement")}</option>
          {statements.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      {accounts.length > 0 ? (
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("audit.create.accounts")}</span>
          <select
            className={ui.input}
            multiple
            size={Math.min(8, accounts.length)}
            value={accountNumbers}
            onChange={(e) => setAccountNumbers(Array.from(e.target.selectedOptions).map((o) => o.value))}
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.number}>
                {a.number} {a.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {accounts.length > 0 ? <p className={ui.help}>{t("audit.create.accountsHint")}</p> : null}
      <ContactPicker label={t("audit.create.auditor")} onPick={(c) => setAuditors((prev) => (prev.some((a) => a.id === c.id) ? prev : [...prev, c]))} />
      {auditors.length > 0 ? (
        <ul className="flex flex-wrap gap-1 text-sm" aria-label={t("audit.create.auditors")}>
          {auditors.map((a) => (
            <li key={a.id} className={ui.badge}>
              {a.display_name}
              <button type="button" className="text-xs" aria-label={t("audit.create.removeAuditor", { name: a.display_name })} onClick={() => setAuditors((prev) => prev.filter((x) => x.id !== a.id))}>
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="flex gap-2">
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("audit.create.submit")}
        </button>
        <button type="button" className={ui.button} onClick={() => setOpen(false)}>
          {t("audit.create.cancel")}
        </button>
      </div>
    </form>
  );
}
