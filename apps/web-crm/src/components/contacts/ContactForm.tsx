"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import {
  useFieldArray,
  useForm,
  type FieldPath,
  type UseFormRegister,
  type FieldErrors,
} from "react-hook-form";

import { bff } from "@/lib/bff";
import {
  ADDRESS_LABELS,
  CHANNELS,
  CONTACT_ROLES,
  CONTACT_TYPES,
  MANDATE_GRANTED_VIA,
  MANDATE_SCHEMES,
  PHONE_LABELS,
  buildContactSchema,
  duplicateQuery,
  emptyContact,
  fromContact,
  toContactIn,
  type ContactFormValues,
  type ContactOut,
} from "@/lib/contact-schema";
import { fieldPath } from "@/lib/problem";
import { ui } from "@/lib/ui";

import { DuplicateWarning, type DuplicateCandidate } from "./DuplicateWarning";

type Props = { mode: "create" } | { mode: "edit"; contact: ContactOut };

function errorAt(errors: FieldErrors<ContactFormValues>, path: string): string | undefined {
  let node: unknown = errors;
  for (const part of path.split(".")) {
    if (node && typeof node === "object") node = (node as Record<string, unknown>)[part];
    else return undefined;
  }
  const message = (node as { message?: unknown } | undefined)?.message;
  return typeof message === "string" ? message : undefined;
}

function Text({
  name,
  label,
  register,
  errors,
  type = "text",
  className = "",
}: {
  name: FieldPath<ContactFormValues>;
  label: string;
  register: UseFormRegister<ContactFormValues>;
  errors: FieldErrors<ContactFormValues>;
  type?: string;
  className?: string;
}) {
  const id = `f-${name.replaceAll(".", "-")}`;
  const error = errorAt(errors, name);
  return (
    <div className={className}>
      <label htmlFor={id} className={ui.label}>
        {label}
      </label>
      <input
        id={id}
        type={type}
        className={ui.input}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : undefined}
        {...register(name)}
      />
      {error ? (
        <p id={`${id}-error`} className={ui.error}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function ContactForm(props: Props) {
  const t = useTranslations("ContactForm");
  const tl = useTranslations("Labels");
  const router = useRouter();
  const existing = props.mode === "edit" ? props.contact : undefined;
  const schema = useMemo(() => buildContactSchema((key) => t(`errors.${key}`)), [t]);
  const {
    register,
    control,
    handleSubmit,
    watch,
    setError,
    setValue,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm<ContactFormValues>({
    resolver: zodResolver(schema),
    defaultValues: existing ? fromContact(existing) : emptyContact(),
  });
  const addresses = useFieldArray({ control, name: "addresses" });
  const phones = useFieldArray({ control, name: "phones" });
  const emails = useFieldArray({ control, name: "emails" });
  const banks = useFieldArray({ control, name: "bank_accounts" });
  const [formError, setFormError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<DuplicateCandidate[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploadingMandate, setUploadingMandate] = useState<number | null>(null);
  const kind = watch("kind");
  const bankAccounts = watch("bank_accounts");
  // PUT without bank_accounts keeps them; they are shown masked and edited separately.
  const bankKept = !!existing && existing.bank_accounts.length > 0;

  async function save(values: ContactFormValues) {
    setSaving(true);
    setFormError(null);
    const body = JSON.stringify(toContactIn(values, existing));
    const result = existing
      ? await bff<ContactOut>(`/api/bff/contacts/${existing.id}`, {
          method: "PUT",
          body,
          headers: { "if-match": `"${existing.version}"` },
        })
      : await bff<ContactOut>("/api/bff/contacts", { method: "POST", body });
    setSaving(false);
    if (result.ok) {
      router.push(`/kontakte/${result.data.id}`);
      router.refresh();
      return;
    }
    setCandidates(null);
    const unmapped: string[] = [];
    for (const item of result.problem?.errors ?? []) {
      const path = fieldPath(item.location);
      if (path && path in flatPaths(values)) {
        setError(path as FieldPath<ContactFormValues>, { type: "server", message: item.message });
      } else {
        unmapped.push(item.message);
      }
    }
    setFormError([result.message, ...unmapped].join(" "));
  }

  async function uploadMandateDocument(i: number, file: File) {
    setUploadingMandate(i);
    const form = new FormData();
    form.set("file", file);
    form.set("title", file.name);
    const result = await bff<{ id: string }>("/api/bff/documents", { method: "POST", body: form });
    setUploadingMandate(null);
    if (result.ok) setValue(`bank_accounts.${i}.mandate_document_id`, result.data.id, { shouldValidate: true });
  }

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    if (!existing) {
      const query = duplicateQuery(values);
      if ([...query.keys()].length) {
        const found = await bff<DuplicateCandidate[]>(`/api/bff/contacts/duplicates?${query}`);
        if (found.ok && found.data.length) {
          setCandidates(found.data);
          return;
        }
        if (!found.ok) {
          setFormError(found.message);
          return;
        }
      }
    }
    await save(values);
  });

  const busy = isSubmitting || saving;
  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5" aria-label={existing ? t("titleEdit") : t("titleNew")}>
      {formError ? (
        <p role="alert" className={ui.alert}>
          {formError}
        </p>
      ) : null}
      {bankKept ? <p className={ui.notice}>{t("bankEditLocked")}</p> : null}

      <fieldset className="flex gap-4">
        <legend className={ui.label}>{t("kind")}</legend>
        {(["person", "company"] as const).map((value) => (
          <label key={value} className="flex items-center gap-1 text-sm">
            <input type="radio" value={value} {...register("kind")} />
            {t(value)}
          </label>
        ))}
      </fieldset>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        {kind === "person" ? (
          <>
            <Text name="salutation" label={t("salutation")} register={register} errors={errors} />
            <Text name="title" label={t("title")} register={register} errors={errors} />
            <Text name="first_name" label={t("firstName")} register={register} errors={errors} />
            <Text name="last_name" label={t("lastName")} register={register} errors={errors} />
            <Text name="date_of_birth" label={t("dateOfBirth")} type="date" register={register} errors={errors} />
          </>
        ) : (
          <>
            <Text name="company_name" label={t("companyName")} register={register} errors={errors} className="sm:col-span-2" />
            <Text name="legal_form" label={t("legalForm")} register={register} errors={errors} />
          </>
        )}
        <Text name="position" label={t("position")} register={register} errors={errors} />
        <Text name="language" label={t("language")} register={register} errors={errors} />
        <div>
          <label htmlFor="f-preferred_channel" className={ui.label}>
            {t("preferredChannel")}
          </label>
          <select id="f-preferred_channel" className={ui.input} {...register("preferred_channel")}>
            <option value="">{t("noChannel")}</option>
            {CHANNELS.map((c) => (
              <option key={c} value={c}>
                {tl(`channel.${c}`)}
              </option>
            ))}
          </select>
        </div>
        <Text name="tags" label={t("tags")} register={register} errors={errors} className="sm:col-span-2" />
        <label className="flex items-center gap-2 self-end text-sm">
          <input type="checkbox" {...register("blocked")} />
          {t("blocked")}
        </label>
      </section>

      <fieldset className="flex flex-wrap gap-3">
        <legend className={ui.label}>{t("types")}</legend>
        {CONTACT_TYPES.map((type) => (
          <label key={type} className="flex items-center gap-1 text-sm">
            <input type="checkbox" value={type} {...register("types")} />
            {tl(`type.${type}`)}
          </label>
        ))}
      </fieldset>

      <fieldset className="flex flex-wrap gap-3">
        <legend className={ui.label}>{t("roles")}</legend>
        {CONTACT_ROLES.map((role) => (
          <label key={role} className="flex items-center gap-1 text-sm">
            <input type="checkbox" value={role} {...register("roles")} />
            {tl(`role.${role}`)}
          </label>
        ))}
      </fieldset>

      <Group title={t("addresses")} onAdd={() => addresses.append({ label: "postal", street: "", house_number: "", postal_code: "", city: "", country: "DE", addition: "", is_primary: addresses.fields.length === 0 })} addLabel={t("add")}>
        {addresses.fields.map((field, i) => (
          <Row key={field.id} onRemove={() => addresses.remove(i)} removeLabel={t("remove")}>
            <Select name={`addresses.${i}.label`} label={t("label")} register={register} options={ADDRESS_LABELS.map((v) => [v, tl(`address.${v}`)])} />
            <Text name={`addresses.${i}.street`} label={t("street")} register={register} errors={errors} className="sm:col-span-2" />
            <Text name={`addresses.${i}.house_number`} label={t("houseNumber")} register={register} errors={errors} />
            <Text name={`addresses.${i}.postal_code`} label={t("postalCode")} register={register} errors={errors} />
            <Text name={`addresses.${i}.city`} label={t("city")} register={register} errors={errors} />
            <Text name={`addresses.${i}.country`} label={t("country")} register={register} errors={errors} />
            <Text name={`addresses.${i}.addition`} label={t("addition")} register={register} errors={errors} />
            <Check name={`addresses.${i}.is_primary`} label={t("primary")} register={register} />
          </Row>
        ))}
      </Group>

      <Group title={t("phones")} onAdd={() => phones.append({ label: "work", number: "", is_primary: phones.fields.length === 0 })} addLabel={t("add")}>
        {phones.fields.map((field, i) => (
          <Row key={field.id} onRemove={() => phones.remove(i)} removeLabel={t("remove")}>
            <Select name={`phones.${i}.label`} label={t("label")} register={register} options={PHONE_LABELS.map((v) => [v, tl(`phone.${v}`)])} />
            <Text name={`phones.${i}.number`} label={t("number")} type="tel" register={register} errors={errors} className="sm:col-span-2" />
            <Check name={`phones.${i}.is_primary`} label={t("primary")} register={register} />
          </Row>
        ))}
      </Group>

      <Group title={t("emails")} onAdd={() => emails.append({ label: "work", email: "", is_primary: emails.fields.length === 0, is_portal_login: false })} addLabel={t("add")}>
        {emails.fields.map((field, i) => (
          <Row key={field.id} onRemove={() => emails.remove(i)} removeLabel={t("remove")}>
            <Text name={`emails.${i}.label`} label={t("label")} register={register} errors={errors} />
            <Text name={`emails.${i}.email`} label={t("email")} type="email" register={register} errors={errors} className="sm:col-span-2" />
            <Check name={`emails.${i}.is_primary`} label={t("primary")} register={register} />
            <Check name={`emails.${i}.is_portal_login`} label={t("portalLogin")} register={register} />
          </Row>
        ))}
      </Group>

      {existing ? (
        existing.bank_accounts.length ? (
          <section>
            <h2 className="mb-1 text-sm font-semibold">{t("existingBank")}</h2>
            <ul className="text-sm">
              {existing.bank_accounts.map((b) => (
                <li key={b.id} className="font-mono">
                  {b.iban_masked}
                </li>
              ))}
            </ul>
          </section>
        ) : null
      ) : (
        <Group
          title={t("bankAccounts")}
          onAdd={() =>
            banks.append({
              label: "",
              iban: "",
              bic: "",
              bank_name: "",
              holder: "",
              valid_from: new Date().toISOString().slice(0, 10),
              valid_to: "",
              sepa_enabled: false,
              mandate_reference: "",
              mandate_signed_on: "",
              mandate_granted_via: "",
              mandate_note: "",
              mandate_document_id: "",
              mandate_scheme: "core",
            })
          }
          addLabel={t("add")}
        >
          {banks.fields.map((field, i) => {
            const sepaEnabled = bankAccounts?.[i]?.sepa_enabled;
            const documentId = bankAccounts?.[i]?.mandate_document_id;
            return (
              <Row key={field.id} onRemove={() => banks.remove(i)} removeLabel={t("remove")}>
                <Text name={`bank_accounts.${i}.iban`} label={t("iban")} register={register} errors={errors} className="sm:col-span-2" />
                <Text name={`bank_accounts.${i}.bic`} label={t("bic")} register={register} errors={errors} />
                <Text name={`bank_accounts.${i}.bank_name`} label={t("bankName")} register={register} errors={errors} />
                <Text name={`bank_accounts.${i}.holder`} label={t("holder")} register={register} errors={errors} />
                <Text name={`bank_accounts.${i}.label`} label={t("label")} register={register} errors={errors} />
                <Text name={`bank_accounts.${i}.valid_from`} label={t("validFrom")} type="date" register={register} errors={errors} />
                <Text name={`bank_accounts.${i}.valid_to`} label={t("validTo")} type="date" register={register} errors={errors} />

                <div className="sm:col-span-4 mt-2 flex flex-col gap-2 rounded border border-border p-2">
                  <label className="flex items-center gap-2 text-sm font-medium">
                    <input type="checkbox" {...register(`bank_accounts.${i}.sepa_enabled`)} />
                    {t("sepa.enabled")}
                  </label>
                  {sepaEnabled ? (
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
                      <Text name={`bank_accounts.${i}.mandate_reference`} label={t("sepa.reference")} register={register} errors={errors} />
                      <Text
                        name={`bank_accounts.${i}.mandate_signed_on`}
                        label={t("sepa.signedOn")}
                        type="date"
                        register={register}
                        errors={errors}
                      />
                      <Select
                        name={`bank_accounts.${i}.mandate_granted_via`}
                        label={t("sepa.grantedVia")}
                        register={register}
                        errors={errors}
                        options={[["", t("sepa.grantedViaNone")], ...MANDATE_GRANTED_VIA.map((v) => [v, tl(`grantedVia.${v}`)] as [string, string])]}
                      />
                      <Select
                        name={`bank_accounts.${i}.mandate_scheme`}
                        label={t("sepa.scheme")}
                        register={register}
                        options={MANDATE_SCHEMES.map((v) => [v, tl(`mandateScheme.${v}`)])}
                      />
                      <Text
                        name={`bank_accounts.${i}.mandate_note`}
                        label={t("sepa.note")}
                        register={register}
                        errors={errors}
                        className="sm:col-span-2"
                      />
                      <div className="sm:col-span-2">
                        <label htmlFor={`f-mandate-file-${i}`} className={ui.label}>
                          {t("sepa.document")}
                        </label>
                        <input
                          id={`f-mandate-file-${i}`}
                          type="file"
                          accept="application/pdf"
                          className={ui.input}
                          disabled={uploadingMandate === i}
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) void uploadMandateDocument(i, file);
                          }}
                        />
                        {uploadingMandate === i ? (
                          <p className="text-xs text-muted">{t("sepa.uploading")}</p>
                        ) : documentId ? (
                          <p className="text-xs text-muted">{t("sepa.documentStored")}</p>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                </div>
              </Row>
            );
          })}
        </Group>
      )}

      <div>
        <label htmlFor="f-notes" className={ui.label}>
          {t("notes")}
        </label>
        <textarea id="f-notes" rows={3} className={ui.input} {...register("notes")} />
      </div>

      {candidates ? (
        <DuplicateWarning
          candidates={candidates}
          busy={busy}
          onSaveAnyway={() => void save(getValues())}
          onCancel={() => setCandidates(null)}
        />
      ) : null}

      <div className="flex gap-2">
        <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy || !!candidates}>
          {busy ? t("saving") : t("save")}
        </button>
        <button type="button" className={ui.button} onClick={() => router.back()}>
          {t("cancel")}
        </button>
      </div>
    </form>
  );
}

/** All leaf paths of the current form values, used to decide which API errors map to fields. */
function flatPaths(value: unknown, prefix = "", out: Record<string, true> = {}): Record<string, true> {
  if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) flatPaths(child, prefix ? `${prefix}.${key}` : key, out);
  } else if (prefix) {
    out[prefix] = true;
  }
  return out;
}

function Group({ title, onAdd, addLabel, children }: { title: string; onAdd: () => void; addLabel: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">{title}</h2>
        <button type="button" className={ui.button} onClick={onAdd} aria-label={`${title}: ${addLabel}`}>
          + {addLabel}
        </button>
      </div>
      {children}
    </section>
  );
}

function Row({ children, onRemove, removeLabel }: { children: React.ReactNode; onRemove: () => void; removeLabel: string }) {
  return (
    <div className="grid grid-cols-1 items-end gap-2 rounded border border-border p-2 sm:grid-cols-4">
      {children}
      <button type="button" className={`${ui.button} justify-self-start`} onClick={onRemove}>
        {removeLabel}
      </button>
    </div>
  );
}

function Select({
  name,
  label,
  register,
  options,
  errors,
}: {
  name: FieldPath<ContactFormValues>;
  label: string;
  register: UseFormRegister<ContactFormValues>;
  options: [string, string][];
  errors?: FieldErrors<ContactFormValues>;
}) {
  const id = `f-${name.replaceAll(".", "-")}`;
  const error = errors ? errorAt(errors, name) : undefined;
  return (
    <div>
      <label htmlFor={id} className={ui.label}>
        {label}
      </label>
      <select id={id} className={ui.input} aria-invalid={!!error} {...register(name)}>
        {options.map(([value, text]) => (
          <option key={value} value={value}>
            {text}
          </option>
        ))}
      </select>
      {error ? (
        <p id={`${id}-error`} className={ui.error}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

function Check({ name, label, register }: { name: FieldPath<ContactFormValues>; label: string; register: UseFormRegister<ContactFormValues> }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" {...register(name)} />
      {label}
    </label>
  );
}
