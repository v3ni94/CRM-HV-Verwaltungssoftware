"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type BankAccountDraft = { kind: string; iban: string; holder: string; bank_name: string; is_default: boolean };
export type KeyDraft = { code: string; name: string; unit_of_measure: string; kind: string; values: string };
export type ExtrasState = {
  bankAccounts: BankAccountDraft[];
  keys: KeyDraft[];
  debtorAccounts: boolean;
  linkDocuments: boolean;
};

export const EMPTY_EXTRAS: ExtrasState = { bankAccounts: [], keys: [], debtorAccounts: false, linkDocuments: true };

const BANK_KINDS = ["hoa", "reserve", "hoa_fee", "rent", "deposit", "other"] as const;
const KEY_KINDS = ["static", "consumption", "fixed_amount", "fixed_share"] as const;

/** Lines "Einheit=Wert" (decimal comma allowed) -> map; lines that cannot be read are returned. */
export function parseKeyValues(text: string): { values: Record<string, string>; invalid: string[] } {
  const values: Record<string, string> = {};
  const invalid: string[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const match = /^([^=:;]+?)\s*[=:;]\s*(\d+(?:[.,]\d+)?)$/.exec(line);
    if (!match || match[1] === undefined || match[2] === undefined) invalid.push(line);
    else values[match[1].trim()] = match[2].replace(",", ".");
  }
  return { values, invalid };
}

const IBAN_SHAPE = /^[A-Za-z]{2}\d{2}[A-Za-z0-9 ]{11,30}$/;

/** Problems that block the confirmation (checked again by the API). */
export function extrasProblems(state: ExtrasState): string[] {
  const problems: string[] = [];
  for (const b of state.bankAccounts) {
    if (!IBAN_SHAPE.test(b.iban.trim()) || b.holder.trim().length < 2) problems.push("bank");
    if (b.is_default && b.kind === "deposit") problems.push("deposit");
  }
  for (const k of state.keys) {
    if (!/^[A-Z0-9_]{1,32}$/.test(k.code)) problems.push("keyCode");
    if (parseKeyValues(k.values).invalid.length) problems.push("keyValues");
    if (k.kind === "consumption" && k.values.trim()) problems.push("keyConsumption");
  }
  return [...new Set(problems)];
}

/** Request part of the confirmed onboarding extras; empty fields are left out. */
export function extrasPayload(state: ExtrasState): Record<string, unknown> {
  return {
    bank_accounts: state.bankAccounts.map((b) => ({
      kind: b.kind,
      iban: b.iban.replace(/\s+/g, "").toUpperCase(),
      holder: b.holder.trim(),
      bank_name: b.bank_name.trim() || null,
      is_default: b.is_default,
    })),
    allocation_keys: state.keys.map((k) => ({
      code: k.code,
      name: k.name.trim() || null,
      unit_of_measure: k.unit_of_measure.trim() || null,
      kind: k.kind || null,
      values: parseKeyValues(k.values).values,
    })),
    create_debtor_accounts: state.debtorAccounts,
    link_source_documents: state.linkDocuments,
  };
}

/** Bank accounts, allocation keys of every kind, debtor accounts and document links of the
 *  property onboarding (10.2 step 5). Every value is typed in or confirmed here, the AI proposal
 *  carries none of it. */
export function OnboardingExtras({ state, onChange }: { state: ExtrasState; onChange: (next: ExtrasState) => void }) {
  const t = useTranslations("OnboardingExtras");
  const setBank = (i: number, patch: Partial<BankAccountDraft>) =>
    onChange({ ...state, bankAccounts: state.bankAccounts.map((b, k) => (k === i ? { ...b, ...patch } : b)) });
  const setKey = (i: number, patch: Partial<KeyDraft>) =>
    onChange({ ...state, keys: state.keys.map((b, k) => (k === i ? { ...b, ...patch } : b)) });
  return (
    <fieldset className="flex flex-col gap-3" data-testid="onboarding-extras">
      <legend className="text-sm font-medium">{t("title")}</legend>
      <p className="text-xs text-muted">{t("hint")}</p>

      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-medium">{t("banksTitle")}</h4>
        {state.bankAccounts.map((b, i) => (
          <div key={i} className="grid gap-2 sm:grid-cols-2" data-testid={`bank-row-${i}`}>
            <div>
              <label htmlFor={`bank-kind-${i}`} className={ui.label}>
                {t("bankKind")}
              </label>
              <select id={`bank-kind-${i}`} className={ui.input} value={b.kind} onChange={(e) => setBank(i, { kind: e.target.value })}>
                {BANK_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {t(`bankKinds.${k}`)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor={`bank-iban-${i}`} className={ui.label}>
                {t("iban")}
              </label>
              <input id={`bank-iban-${i}`} className={ui.input} value={b.iban} onChange={(e) => setBank(i, { iban: e.target.value })} />
            </div>
            <div>
              <label htmlFor={`bank-holder-${i}`} className={ui.label}>
                {t("holder")}
              </label>
              <input id={`bank-holder-${i}`} className={ui.input} value={b.holder} onChange={(e) => setBank(i, { holder: e.target.value })} />
            </div>
            <div>
              <label htmlFor={`bank-name-${i}`} className={ui.label}>
                {t("bankName")}
              </label>
              <input id={`bank-name-${i}`} className={ui.input} value={b.bank_name} onChange={(e) => setBank(i, { bank_name: e.target.value })} />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={b.is_default} onChange={(e) => setBank(i, { is_default: e.target.checked })} />
              {t("bankDefault")}
            </label>
            <button type="button" className={ui.button} onClick={() => onChange({ ...state, bankAccounts: state.bankAccounts.filter((_, k) => k !== i) })}>
              {t("remove")}
            </button>
          </div>
        ))}
        <div>
          <button
            type="button"
            className={ui.button}
            data-testid="bank-add"
            onClick={() => onChange({ ...state, bankAccounts: [...state.bankAccounts, { kind: "hoa", iban: "", holder: "", bank_name: "", is_default: false }] })}
          >
            {t("bankAdd")}
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-medium">{t("keysTitle")}</h4>
        <p className="text-xs text-muted">{t("keysHint")}</p>
        {state.keys.map((k, i) => (
          <div key={i} className="grid gap-2 sm:grid-cols-2" data-testid={`key-row-${i}`}>
            <div>
              <label htmlFor={`key-code-${i}`} className={ui.label}>
                {t("keyCode")}
              </label>
              <input id={`key-code-${i}`} className={ui.input} value={k.code} onChange={(e) => setKey(i, { code: e.target.value.toUpperCase() })} />
            </div>
            <div>
              <label htmlFor={`key-kind-${i}`} className={ui.label}>
                {t("keyKind")}
              </label>
              <select id={`key-kind-${i}`} className={ui.input} value={k.kind} onChange={(e) => setKey(i, { kind: e.target.value })}>
                <option value="">{t("keyKindExisting")}</option>
                {KEY_KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {t(`keyKinds.${kind}`)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor={`key-name-${i}`} className={ui.label}>
                {t("keyName")}
              </label>
              <input id={`key-name-${i}`} className={ui.input} value={k.name} onChange={(e) => setKey(i, { name: e.target.value })} />
            </div>
            <div>
              <label htmlFor={`key-unit-${i}`} className={ui.label}>
                {t("keyUnit")}
              </label>
              <input id={`key-unit-${i}`} className={ui.input} value={k.unit_of_measure} onChange={(e) => setKey(i, { unit_of_measure: e.target.value })} />
            </div>
            <div className="sm:col-span-2">
              <label htmlFor={`key-values-${i}`} className={ui.label}>
                {t("keyValues")}
              </label>
              <textarea
                id={`key-values-${i}`}
                className={ui.input}
                rows={3}
                placeholder={t("keyValuesPlaceholder")}
                value={k.values}
                onChange={(e) => setKey(i, { values: e.target.value })}
              />
            </div>
            <button type="button" className={ui.button} onClick={() => onChange({ ...state, keys: state.keys.filter((_, n) => n !== i) })}>
              {t("remove")}
            </button>
          </div>
        ))}
        <div>
          <button
            type="button"
            className={ui.button}
            data-testid="key-add"
            onClick={() => onChange({ ...state, keys: [...state.keys, { code: "", name: "", unit_of_measure: "", kind: "", values: "" }] })}
          >
            {t("keyAdd")}
          </button>
        </div>
      </div>

      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" checked={state.debtorAccounts} onChange={(e) => onChange({ ...state, debtorAccounts: e.target.checked })} />
        <span>
          {t("debtor")}
          <span className="block text-xs text-muted">{t("debtorHint")}</span>
        </span>
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" checked={state.linkDocuments} onChange={(e) => onChange({ ...state, linkDocuments: e.target.checked })} />
        <span>
          {t("linkDocuments")}
          <span className="block text-xs text-muted">{t("linkDocumentsHint")}</span>
        </span>
      </label>
    </fieldset>
  );
}

export type EntityCandidate = { id: string; name: string; kind: string };
export type EntityDecision =
  | { kind: "bank_account"; index: number; holder: string; account_kind: string; candidates: EntityCandidate[] }
  | { kind: "debtor_accounts"; candidates: EntityCandidate[] };

/** Decision points of the apply (R03-02) from the import summary; empty when none are open. */
export function entityDecisions(summary: Record<string, unknown> | undefined): EntityDecision[] {
  const raw = summary?.entity_decisions;
  return Array.isArray(raw) ? (raw as EntityDecision[]) : [];
}

/** Request of the follow-up call: one legal entity per bank account, chosen debtor entities. */
export function resolvePayload(
  decisions: EntityDecision[],
  accounts: BankAccountDraft[],
  chosen: Record<string, string>,
  debtorIds: string[],
  asOf: string,
): Record<string, unknown> {
  const banks = decisions.flatMap((d) => {
    if (d.kind !== "bank_account") return [];
    const draft = accounts[d.index];
    const entity = chosen[String(d.index)];
    return draft && entity ? [{ index: d.index, account: { kind: draft.kind, iban: draft.iban.replace(/\s+/g, "").toUpperCase(), holder: draft.holder.trim(), bank_name: draft.bank_name.trim() || null, is_default: draft.is_default, legal_entity_id: entity } }] : [];
  });
  return {
    bank_accounts: banks.map((b) => b.account),
    resolved_indexes: banks.map((b) => b.index),
    debtor_legal_entity_ids: debtorIds,
    as_of: asOf,
  };
}

/** Choice of the legal entity per account (R03-02): shown after the apply when several legal
 *  entities match; the accounts are created by the follow-up call, never guessed. */
export function EntityDecisions({
  runId,
  decisions,
  accounts,
  asOf,
  onResolved,
}: {
  runId: string;
  decisions: EntityDecision[];
  accounts: BankAccountDraft[];
  asOf: string;
  onResolved: (message: string) => void;
}) {
  const t = useTranslations("OnboardingExtras");
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const [debtorIds, setDebtorIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (decisions.length === 0) return null;
  const complete = decisions.every((d) => d.kind !== "bank_account" || chosen[String(d.index)]);
  const submit = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ created_bank_accounts: number; debtor_entities: number }>(`/api/bff/ai/import-runs/${runId}/resolve-entities`, {
      method: "POST",
      body: JSON.stringify(resolvePayload(decisions, accounts, chosen, debtorIds, asOf)),
    });
    setBusy(false);
    if (res.ok) onResolved(t("decisionDone", { banks: res.data.created_bank_accounts, debtors: res.data.debtor_entities }));
    else setError(res.message);
  };
  return (
    <fieldset className="flex flex-col gap-3" data-testid="entity-decisions">
      <legend className="text-sm font-medium">{t("decisionTitle")}</legend>
      <p className="text-xs text-muted">{t("decisionHint")}</p>
      {decisions.map((d, i) =>
        d.kind === "bank_account" ? (
          <div key={`b${d.index}`}>
            <label htmlFor={`entity-${d.index}`} className={ui.label}>
              {t("decisionBank", { holder: d.holder, kind: t(`bankKinds.${d.account_kind as (typeof BANK_KINDS)[number]}`) })}
            </label>
            <select id={`entity-${d.index}`} className={ui.input} value={chosen[String(d.index)] ?? ""} onChange={(e) => setChosen({ ...chosen, [String(d.index)]: e.target.value })}>
              <option value="">{t("decisionChoose")}</option>
              {d.candidates.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <div key={`d${i}`}>
            <p className="text-sm">{t("decisionDebtor")}</p>
            {d.candidates.map((c) => (
              <label key={c.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={debtorIds.includes(c.id)}
                  onChange={(e) => setDebtorIds(e.target.checked ? [...debtorIds, c.id] : debtorIds.filter((x) => x !== c.id))}
                />
                {c.name}
              </label>
            ))}
          </div>
        ),
      )}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div>
        <button type="button" className={ui.button} disabled={busy || !complete || !asOf} data-testid="entity-apply" onClick={() => void submit()}>
          {t("decisionApply")}
        </button>
      </div>
    </fieldset>
  );
}
