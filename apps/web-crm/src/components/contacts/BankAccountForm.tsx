"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { bff } from "@/lib/bff";
import { CONTACT_BANK_ACCOUNT_KINDS, isValidIban } from "@/lib/contact-schema";
import { ui } from "@/lib/ui";
import { today as businessToday } from "@/lib/today";

type BankAccount =
  components["schemas"]["mhvp__contacts__schemas__BankAccountOut"];
type BankAccountIn = Pick<
  components["schemas"]["mhvp__contacts__schemas__BankAccountIn"],
  "label" | "kind" | "is_default" | "iban" | "bic" | "bank_name" | "holder" | "valid_from" | "valid_to"
>;

const BIC = /^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$/;

type Values = {
  label: string;
  kind: string;
  is_default: boolean;
  iban: string;
  bic: string;
  bank_name: string;
  holder: string;
  valid_from: string;
  valid_to: string;
};


/** Add a bank account to an existing contact, or change one as a new version (M5-01
 * addendum 28.09.2026). The IBAN is checked client side (ISO 13616 mod 97, same rule as the
 * API) and stored encrypted by the API; the account starts as pending for a second person. In
 * replace mode the old account keeps its IBAN and ends on release the day before the new
 * Gültig ab; the default flag is handed over then. */
export function BankAccountForm({
  contactId,
  mode,
  account,
  onClose,
}: {
  contactId: string;
  mode: "add" | "replace";
  account?: BankAccount;
  onClose: () => void;
}) {
  const t = useTranslations("Contacts.bankAccounts");
  const tf = useTranslations("ContactForm");
  const router = useRouter();
  const id = useId();
  const [values, setValues] = useState<Values>({
    label: account?.label ?? "",
    kind: account?.kind ?? "",
    is_default: false,
    iban: "",
    bic: account?.bic ?? "",
    bank_name: account?.bank_name ?? "",
    holder: account?.holder ?? "",
    valid_from: businessToday(),
    valid_to: "",
  });
  const [errors, setErrors] = useState<Partial<Record<keyof Values, string>>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<BankAccount | null>(null);

  function set<K extends keyof Values>(key: K, value: Values[K]) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  function validate(): boolean {
    const next: Partial<Record<keyof Values, string>> = {};
    if (!isValidIban(values.iban)) next.iban = t("ibanInvalid");
    if (values.bic.trim() && !BIC.test(values.bic.trim().toUpperCase())) next.bic = t("bicInvalid");
    if (!values.valid_from) next.valid_from = t("validFromRequired");
    if (values.valid_to && values.valid_from && values.valid_to < values.valid_from) {
      next.valid_to = t("validToBeforeFrom");
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!validate()) return;
    const body: BankAccountIn = {
      label: values.label.trim() || null,
      kind: (values.kind || null) as BankAccountIn["kind"],
      is_default: mode === "add" ? values.is_default : false,
      iban: values.iban.replace(/\s+/g, "").toUpperCase(),
      bic: values.bic.trim() ? values.bic.trim().toUpperCase() : null,
      bank_name: values.bank_name.trim() || null,
      holder: values.holder.trim() || null,
      valid_from: values.valid_from,
      valid_to: values.valid_to || null,
    };
    const path =
      mode === "add"
        ? `/api/bff/contacts/${contactId}/bank-accounts`
        : `/api/bff/contacts/${contactId}/bank-accounts/${account?.id}/replace`;
    setBusy(true);
    const result = await bff<BankAccount>(path, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setSaved(result.data);
    router.refresh();
  }

  const field = (key: keyof Values) => `${id}-${key}`;
  const title =
    mode === "add" ? t("addTitle") : t("replaceTitle", { iban: account?.iban_masked ?? "" });

  if (saved) {
    return (
      <div className={`${ui.card} flex flex-col gap-2`} data-testid="bank-account-form">
        <p role="status" className="text-sm text-success-fg">
          {t("saved", { iban: saved.iban_masked })}
        </p>
        <div>
          <button type="button" className={ui.buttonSm} onClick={onClose}>
            {t("close")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <form
      className={`${ui.card} flex flex-col gap-3`}
      aria-label={title}
      data-testid="bank-account-form"
      onSubmit={(event) => void submit(event)}
    >
      <h3 className="text-sm font-semibold">{title}</h3>
      {mode === "replace" ? <p className={ui.notice}>{t("replaceHint")}</p> : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label htmlFor={field("iban")} className={ui.label}>
            {tf("iban")}
          </label>
          <input
            id={field("iban")}
            className={ui.input}
            required
            autoComplete="off"
            value={values.iban}
            onChange={(event) => set("iban", event.target.value)}
            aria-invalid={errors.iban ? true : undefined}
          />
          {errors.iban ? <p className={ui.error}>{errors.iban}</p> : null}
        </div>
        <div>
          <label htmlFor={field("bic")} className={ui.label}>
            {tf("bic")}
          </label>
          <input
            id={field("bic")}
            className={ui.input}
            value={values.bic}
            onChange={(event) => set("bic", event.target.value)}
          />
          {errors.bic ? <p className={ui.error}>{errors.bic}</p> : null}
        </div>
        <div>
          <label htmlFor={field("bank_name")} className={ui.label}>
            {tf("bankName")}
          </label>
          <input
            id={field("bank_name")}
            className={ui.input}
            maxLength={200}
            value={values.bank_name}
            onChange={(event) => set("bank_name", event.target.value)}
          />
        </div>
        <div>
          <label htmlFor={field("holder")} className={ui.label}>
            {tf("holder")}
          </label>
          <input
            id={field("holder")}
            className={ui.input}
            maxLength={200}
            value={values.holder}
            onChange={(event) => set("holder", event.target.value)}
          />
        </div>
        <div>
          <label htmlFor={field("label")} className={ui.label}>
            {tf("label")}
          </label>
          <input
            id={field("label")}
            className={ui.input}
            maxLength={100}
            value={values.label}
            onChange={(event) => set("label", event.target.value)}
          />
        </div>
        <div>
          <label htmlFor={field("kind")} className={ui.label}>
            {tf("accountKindLabel")}
          </label>
          <select
            id={field("kind")}
            className={ui.input}
            value={values.kind}
            onChange={(event) => set("kind", event.target.value)}
          >
            <option value="">{tf("noAccountKind")}</option>
            {CONTACT_BANK_ACCOUNT_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {tf(`accountKind.${kind}`)}
              </option>
            ))}
          </select>
        </div>
        {mode === "add" ? (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={values.is_default}
              onChange={(event) => set("is_default", event.target.checked)}
            />
            {tf("defaultAccount")}
          </label>
        ) : null}
        <div>
          <label htmlFor={field("valid_from")} className={ui.label}>
            {tf("validFrom")}
          </label>
          <input
            id={field("valid_from")}
            type="date"
            className={ui.input}
            required
            value={values.valid_from}
            onChange={(event) => set("valid_from", event.target.value)}
          />
          {errors.valid_from ? <p className={ui.error}>{errors.valid_from}</p> : null}
        </div>
        <div>
          <label htmlFor={field("valid_to")} className={ui.label}>
            {tf("validTo")}
          </label>
          <input
            id={field("valid_to")}
            type="date"
            className={ui.input}
            value={values.valid_to}
            onChange={(event) => set("valid_to", event.target.value)}
          />
          {errors.valid_to ? <p className={ui.error}>{errors.valid_to}</p> : null}
        </div>
      </div>
      <p className={ui.help}>{t("pendingHint")}</p>
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
      <div className={ui.formActions}>
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("save")}
        </button>
        <button type="button" className={ui.button} disabled={busy} onClick={onClose}>
          {t("cancel")}
        </button>
      </div>
    </form>
  );
}
