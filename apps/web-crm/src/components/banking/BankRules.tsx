"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { accountLabel, parseAmount, type BankAccountOption, type Ledger, type LedgerAccount } from "./bankTypes";

export type BankRule = {
  id: string;
  name: string;
  legal_entity_id: string;
  match: Record<string, unknown>;
  action: Record<string, unknown>;
  priority: number;
  hit_count: number;
  learned_from_ai: boolean;
  learned_from_transaction_id: string | null;
  approval_state: "proposed" | "approved" | "active" | "disabled" | string;
  approved_by: string | null;
  max_amount: string | null;
  test_evidence_document_id: string | null;
  created_by: string | null;
};

const STATE_VARIANT: Record<string, StatusPillVariant> = {
  proposed: "gold",
  approved: "warning",
  active: "success",
  disabled: "neutral",
};

export type BankRulesProps = {
  canCreate: boolean;
  canApprove: boolean;
  canUpdate: boolean;
  userId: string | null;
};

type Form = {
  name: string;
  legal_entity_id: string;
  counterpart_iban: string;
  name_contains: string;
  purpose_regex: string;
  amount_min: string;
  amount_max: string;
  account_id: string;
  priority: string;
};

const EMPTY: Form = {
  name: "",
  legal_entity_id: "",
  counterpart_iban: "",
  name_contains: "",
  purpose_regex: "",
  amount_min: "",
  amount_max: "",
  account_id: "",
  priority: "100",
};

/** Priority as the API expects it (`RuleIn.priority`, 0 to 10000): an empty field takes the
 *  API default 100, anything else must be a whole number in range. 0 is a valid value and
 *  is never replaced (the runner takes the first hit ordered by priority). */
export function parsePriority(input: string): number | null {
  const s = input.trim();
  if (s === "") return 100;
  if (!/^\d{1,5}$/.test(s)) return null;
  const n = Number(s);
  return n <= 10000 ? n : null;
}

/** Bank rules with the four eyes life cycle of the existing API (6.9.4, 7.4 Nr. 4, D51):
 *  create (`proposed`), approve by a second person (`approved`), activate with an amount cap
 *  and a test evidence document (`active`), disable. A rule never books anything here; the
 *  automation runner is a later step (plan M12 S6) and stays off. */
export function BankRules({ canCreate, canApprove, canUpdate, userId }: BankRulesProps) {
  const t = useTranslations("Bank.rules");
  const [rules, setRules] = useState<BankRule[] | null>(null);
  const [accounts, setAccounts] = useState<BankAccountOption[]>([]);
  const [ledgers, setLedgers] = useState<Ledger[]>([]);
  const [ledgerAccounts, setLedgerAccounts] = useState<LedgerAccount[]>([]);
  const [form, setForm] = useState<Form>(EMPTY);
  const [showForm, setShowForm] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [activating, setActivating] = useState<string | null>(null);
  const [maxAmount, setMaxAmount] = useState("");
  const [evidence, setEvidence] = useState<File | null>(null);

  const load = async () => {
    const res = await bff<BankRule[]>("/api/bff/banking/rules");
    if (res.ok) setRules(res.data);
    else {
      setRules([]);
      setError(res.message);
    }
  };
  useEffect(() => {
    load();
    (async () => {
      const [a, l] = await Promise.all([bff<BankAccountOption[]>("/api/bff/banking/accounts"), bff<Ledger[]>("/api/bff/accounting/ledgers")]);
      if (a.ok) setAccounts(a.data);
      if (l.ok) setLedgers(l.data);
    })();
  }, []);

  const legalEntities = useMemo(() => {
    const map = new Map<string, string>();
    for (const a of accounts) map.set(a.legal_entity_id, a.legal_entity_name ?? a.legal_entity_id);
    return [...map.entries()];
  }, [accounts]);
  const entityName = (id: string) => legalEntities.find(([eid]) => eid === id)?.[1] ?? id;

  useEffect(() => {
    const ledger = ledgers.find((l) => l.legal_entity_id === form.legal_entity_id);
    if (!ledger) {
      setLedgerAccounts([]);
      return;
    }
    (async () => {
      const res = await bff<LedgerAccount[]>(`/api/bff/accounting/ledgers/${ledger.id}/accounts`);
      if (res.ok) setLedgerAccounts(res.data.filter((a) => a.active && !a.is_system && a.property_bank_account_id === null));
    })();
  }, [form.legal_entity_id, ledgers]);

  const set = (key: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm((prev) => ({ ...prev, [key]: e.target.value }));

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const priority = parsePriority(form.priority);
    if (priority === null) {
      setError(t("invalidPriority"));
      return;
    }
    const body: Record<string, unknown> = {
      name: form.name.trim(),
      legal_entity_id: form.legal_entity_id,
      priority,
    };
    if (form.counterpart_iban.trim()) body.counterpart_iban = form.counterpart_iban.trim();
    if (form.name_contains.trim()) body.name_contains = form.name_contains.trim();
    if (form.purpose_regex.trim()) body.purpose_regex = form.purpose_regex.trim();
    for (const key of ["amount_min", "amount_max"] as const) {
      if (!form[key].trim()) continue;
      const amount = parseAmount(form[key]);
      if (amount === null) {
        setError(t("invalidAmount", { value: form[key].trim() }));
        return;
      }
      body[key] = amount;
    }
    if (form.account_id) body.account_id = form.account_id;
    setBusyId("new");
    const res = await bff<BankRule>("/api/bff/banking/rules", { method: "POST", body: JSON.stringify(body) });
    setBusyId(null);
    if (res.ok) {
      setNotice(t("created", { name: res.data.name }));
      setForm(EMPTY);
      setShowForm(false);
      load();
    } else setError(res.message);
  };

  const act = async (rule: BankRule, action: "approve" | "disable") => {
    setBusyId(rule.id);
    setError(null);
    const res = await bff<BankRule>(`/api/bff/banking/rules/${rule.id}/${action}`, { method: "POST", body: "{}" });
    setBusyId(null);
    if (res.ok) load();
    else setError(res.message);
  };

  const activate = async (rule: BankRule) => {
    if (!evidence || !maxAmount.trim()) return;
    setError(null);
    const cap = parseAmount(maxAmount);
    if (cap === null) {
      setError(t("invalidAmount", { value: maxAmount.trim() }));
      return;
    }
    setBusyId(rule.id);
    const formData = new FormData();
    formData.append("file", evidence, evidence.name);
    formData.append("title", t("evidenceTitle", { name: rule.name }));
    const doc = await bff<{ id: string }>("/api/bff/documents", { method: "POST", body: formData });
    if (!doc.ok) {
      setBusyId(null);
      setError(doc.message);
      return;
    }
    const res = await bff<BankRule>(`/api/bff/banking/rules/${rule.id}/activate`, {
      method: "POST",
      body: JSON.stringify({ max_amount: cap, test_evidence_document_id: doc.data.id }),
    });
    setBusyId(null);
    if (res.ok) {
      setActivating(null);
      setMaxAmount("");
      setEvidence(null);
      load();
    } else setError(res.message);
  };

  const matchSummary = (rule: BankRule) => {
    const parts: string[] = [];
    if (rule.match.counterpart_iban_fingerprint) parts.push(t("matchIban"));
    if (rule.match.name_contains) parts.push(t("matchName", { value: String(rule.match.name_contains) }));
    if (rule.match.purpose_regex) parts.push(t("matchPurpose", { value: String(rule.match.purpose_regex) }));
    if (rule.match.amount_min || rule.match.amount_max)
      parts.push(t("matchAmount", { min: rule.match.amount_min ? formatEur(String(rule.match.amount_min)) : "", max: rule.match.amount_max ? formatEur(String(rule.match.amount_max)) : "" }));
    return parts.join(", ") || t("matchNone");
  };

  return (
    <section className="flex flex-col gap-3" data-testid="bank-rules">
      <p className={ui.notice}>{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {notice ? <p className={ui.success}>{notice}</p> : null}
      {canCreate ? (
        <div>
          <button type="button" className={ui.button} onClick={() => setShowForm((v) => !v)} aria-expanded={showForm}>
            {t("new")}
          </button>
        </div>
      ) : null}
      {showForm ? (
        <form onSubmit={create} className={`${ui.card} grid gap-3 sm:grid-cols-2`} data-testid="rule-form">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("name")}</span>
            <input className={ui.input} required maxLength={200} value={form.name} onChange={set("name")} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("legalEntity")}</span>
            <select className={ui.input} required value={form.legal_entity_id} onChange={set("legal_entity_id")}>
              <option value="">{t("chooseEntity")}</option>
              {legalEntities.map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("iban")}</span>
            <input className={ui.input} value={form.counterpart_iban} onChange={set("counterpart_iban")} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("nameContains")}</span>
            <input className={ui.input} maxLength={200} value={form.name_contains} onChange={set("name_contains")} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("purposeRegex")}</span>
            <input className={ui.input} maxLength={500} value={form.purpose_regex} onChange={set("purpose_regex")} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("priority")}</span>
            <input className={ui.input} type="number" min={0} max={10000} value={form.priority} onChange={set("priority")} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("amountMin")}</span>
            <input className={ui.input} inputMode="decimal" value={form.amount_min} onChange={set("amount_min")} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("amountMax")}</span>
            <input className={ui.input} inputMode="decimal" value={form.amount_max} onChange={set("amount_max")} />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={ui.label}>{t("account")}</span>
            <select className={ui.input} value={form.account_id} onChange={set("account_id")} aria-describedby="rule-account-hint">
              <option value="">{t("noAccount")}</option>
              {ledgerAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {accountLabel(a)}
                </option>
              ))}
            </select>
          </label>
          <span id="rule-account-hint" className={`${ui.help} sm:col-span-2`}>
            {t("accountHint")}
          </span>
          <p className={`${ui.help} sm:col-span-2`}>{t("matchHint")}</p>
          <div className={`${ui.formActions} sm:col-span-2`}>
            <button type="submit" className={ui.primary} disabled={busyId === "new"}>
              {t("propose")}
            </button>
            <button type="button" className={ui.secondary} onClick={() => setShowForm(false)}>
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : null}
      {rules === null ? <p className="text-sm text-muted">{t("loading")}</p> : null}
      {rules && rules.length === 0 ? <EmptyState title={t("empty")} /> : null}
      {rules && rules.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("name")}</th>
                <th>{t("legalEntity")}</th>
                <th>{t("match")}</th>
                <th>{t("state")}</th>
                <th className="num">{t("maxAmount")}</th>
                <th className="num">{t("hits")}</th>
                <th>{t("actions")}</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => {
                const own = userId !== null && rule.created_by === userId;
                return (
                  <tr key={rule.id} className="align-top" data-testid="rule-row">
                    <td>
                      {rule.name}
                      {rule.learned_from_transaction_id ? <span className={`ml-1 ${ui.badge}`}>{t("learned")}</span> : null}
                      {rule.learned_from_ai ? <span className={`ml-1 ${ui.badge}`}>{t("fromAi")}</span> : null}
                    </td>
                    <td>{entityName(rule.legal_entity_id)}</td>
                    <td className="text-xs">{matchSummary(rule)}</td>
                    <td>
                      <StatusPill variant={STATE_VARIANT[rule.approval_state] ?? "neutral"} label={t(`state_${rule.approval_state}`)} />
                    </td>
                    <td className="num">{rule.max_amount ? formatEur(rule.max_amount) : ""}</td>
                    <td className="num">{rule.hit_count}</td>
                    <td>
                      <div className="flex flex-wrap gap-1">
                        {rule.approval_state === "proposed" && canApprove ? (
                          <button type="button" className={ui.buttonSm} onClick={() => act(rule, "approve")} disabled={busyId === rule.id || own} title={own ? t("fourEyes") : undefined}>
                            {t("approve")}
                          </button>
                        ) : null}
                        {rule.approval_state === "approved" && canApprove ? (
                          <button type="button" className={ui.buttonSm} onClick={() => setActivating(activating === rule.id ? null : rule.id)} disabled={busyId === rule.id}>
                            {t("activate")}
                          </button>
                        ) : null}
                        {rule.approval_state !== "disabled" && canUpdate ? (
                          <button type="button" className={ui.buttonSm} onClick={() => act(rule, "disable")} disabled={busyId === rule.id}>
                            {t("disable")}
                          </button>
                        ) : null}
                      </div>
                      {own && rule.approval_state === "proposed" ? <p className={ui.help}>{t("fourEyes")}</p> : null}
                      {activating === rule.id ? (
                        <div className="mt-2 flex flex-col gap-2" data-testid="activate-form">
                          <label className="flex flex-col gap-1">
                            <span className={ui.label}>{t("maxAmount")}</span>
                            <input className={ui.input} inputMode="decimal" value={maxAmount} onChange={(e) => setMaxAmount(e.target.value)} />
                          </label>
                          <label className="flex flex-col gap-1">
                            <span className={ui.label}>{t("evidence")}</span>
                            <input type="file" onChange={(e) => setEvidence(e.target.files?.[0] ?? null)} aria-describedby="rule-evidence-hint" />
                          </label>
                          <span id="rule-evidence-hint" className={ui.help}>
                            {t("evidenceHint")}
                          </span>
                          <div className={ui.formActions}>
                            <button type="button" className={ui.primary} onClick={() => activate(rule)} disabled={busyId === rule.id || !evidence || !maxAmount.trim()}>
                              {t("activateConfirm")}
                            </button>
                            <button type="button" className={ui.secondary} onClick={() => setActivating(null)}>
                              {t("cancel")}
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
