/**
 * Client-side validation of the contact form. Mirrors the API rules of ContactIn
 * (apps/api/src/mhvp/contacts/schemas.py and validation.py). The API stays authoritative:
 * phone numbers are only checked for plausibility here, the API validates them fully (E.164).
 */
import type { components } from "@mhvp/api-client";
import { z } from "zod";

export type ContactIn = components["schemas"]["ContactIn"];
export type ContactOut = components["schemas"]["ContactOut"];

export const CONTACT_TYPES = [
  "tenant",
  "prospect",
  "owner",
  "service_provider",
  "broker",
  "manager",
  "bank",
  "board_member",
  "authority",
  "other",
] as const;
export const ADDRESS_LABELS = ["postal", "private", "work", "public"] as const;
export const PHONE_LABELS = ["work", "mobile", "private", "fax", "other"] as const;
export const CHANNELS = ["post", "email", "portal"] as const;

const IBAN_LENGTHS: Record<string, number> = {
  DE: 22, AT: 20, CH: 21, NL: 18, BE: 16, FR: 27, LU: 20, IT: 27, ES: 24,
};

/** ISO 13616 check (shape, known country lengths, mod 97), same rules as the API. */
export function isValidIban(value: string): boolean {
  const iban = value.replace(/\s+/g, "").toUpperCase();
  if (!/^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$/.test(iban)) return false;
  const expected = IBAN_LENGTHS[iban.slice(0, 2)];
  if (expected !== undefined && iban.length !== expected) return false;
  const rearranged = iban.slice(4) + iban.slice(0, 4);
  let remainder = 0;
  for (const ch of rearranged) {
    const digits = /[0-9]/.test(ch) ? ch : String(ch.charCodeAt(0) - 55);
    for (const d of digits) remainder = (remainder * 10 + Number(d)) % 97;
  }
  return remainder === 1;
}

export type Messages = (key: string) => string;

const optional = (max: number, t: Messages) => z.string().trim().max(max, t("tooLong"));

export function buildContactSchema(t: Messages) {
  const address = z.object({
    label: z.enum(ADDRESS_LABELS),
    street: optional(200, t),
    house_number: optional(20, t),
    postal_code: optional(20, t),
    city: optional(100, t),
    country: z.string().trim().regex(/^[A-Z]{2}$/, t("countryInvalid")),
    addition: optional(200, t),
    is_primary: z.boolean(),
  });
  const phone = z.object({
    label: z.enum(PHONE_LABELS),
    number: z
      .string()
      .trim()
      .max(40, t("tooLong"))
      .regex(/^\+?[0-9][0-9 ()/.-]{3,}$/, t("phoneInvalid")),
    is_primary: z.boolean(),
  });
  const email = z.object({
    label: z.string().trim().max(32, t("tooLong")),
    email: z.email(t("emailInvalid")),
    is_primary: z.boolean(),
    is_portal_login: z.boolean(),
  });
  const bank = z
    .object({
      label: optional(100, t),
      iban: z.string().max(50, t("tooLong")).refine(isValidIban, t("ibanInvalid")),
      bic: z
        .string()
        .trim()
        .refine((v) => v === "" || /^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$/.test(v.toUpperCase()), t("bicInvalid")),
      bank_name: optional(200, t),
      holder: optional(200, t),
      valid_from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, t("dateRequired")),
      valid_to: z.string(),
    })
    .refine((b) => !b.valid_to || b.valid_to >= b.valid_from, {
      message: t("periodInvalid"),
      path: ["valid_to"],
    });

  return z
    .object({
      kind: z.enum(["person", "company"]),
      salutation: optional(50, t),
      title: optional(50, t),
      first_name: optional(100, t),
      last_name: optional(100, t),
      company_name: optional(200, t),
      legal_form: optional(50, t),
      position: optional(100, t),
      date_of_birth: z.string(),
      language: z.string().regex(/^[a-z]{2}$/, t("languageInvalid")),
      preferred_channel: z.union([z.enum(CHANNELS), z.literal("")]),
      notes: optional(10_000, t),
      blocked: z.boolean(),
      types: z.array(z.enum(CONTACT_TYPES)),
      tags: z.string(),
      addresses: z.array(address).max(20),
      phones: z.array(phone).max(20),
      emails: z.array(email).max(20),
      bank_accounts: z.array(bank).max(20),
    })
    .superRefine((v, ctx) => {
      if (v.kind === "person" && !v.first_name && !v.last_name) {
        ctx.addIssue({ code: "custom", message: t("nameRequired"), path: ["last_name"] });
      }
      if (v.kind === "company" && !v.company_name) {
        ctx.addIssue({ code: "custom", message: t("companyRequired"), path: ["company_name"] });
      }
    });
}

export type ContactFormValues = z.infer<ReturnType<typeof buildContactSchema>>;

export function emptyContact(): ContactFormValues {
  return {
    kind: "person",
    salutation: "",
    title: "",
    first_name: "",
    last_name: "",
    company_name: "",
    legal_form: "",
    position: "",
    date_of_birth: "",
    language: "de",
    preferred_channel: "",
    notes: "",
    blocked: false,
    types: [],
    tags: "",
    addresses: [],
    phones: [],
    emails: [],
    bank_accounts: [],
  };
}

const s = (v: string | null | undefined) => v ?? "";
const n = (v: string) => (v.trim() === "" ? null : v.trim());

export function fromContact(c: ContactOut): ContactFormValues {
  return {
    kind: c.kind,
    salutation: s(c.salutation),
    title: s(c.title),
    first_name: s(c.first_name),
    last_name: s(c.last_name),
    company_name: s(c.company_name),
    legal_form: s(c.legal_form),
    position: s(c.position),
    date_of_birth: s(c.date_of_birth),
    language: c.language,
    preferred_channel: c.preferred_channel ?? "",
    notes: s(c.notes),
    blocked: c.blocked,
    types: c.types,
    tags: c.tags.join(", "),
    addresses: c.addresses.map((a) => ({
      label: a.label ?? "postal",
      street: s(a.street),
      house_number: s(a.house_number),
      postal_code: s(a.postal_code),
      city: s(a.city),
      country: a.country ?? "DE",
      addition: s(a.addition),
      is_primary: !!a.is_primary,
    })),
    phones: c.phones.map((p) => ({ label: p.label, number: p.number, is_primary: p.is_primary })),
    emails: c.emails.map((e) => ({
      label: e.label,
      email: e.email,
      is_primary: e.is_primary,
      is_portal_login: e.is_portal_login,
    })),
    // Only masked IBANs are delivered; bank accounts cannot be edited through this form.
    bank_accounts: [],
  };
}

/** Converts form values to the API body. Fields the form does not edit are carried over. */
export function toContactIn(v: ContactFormValues, existing?: ContactOut): ContactIn {
  const person = v.kind === "person";
  return {
    kind: v.kind,
    salutation: person ? n(v.salutation) : null,
    title: person ? n(v.title) : null,
    first_name: person ? n(v.first_name) : null,
    last_name: person ? n(v.last_name) : null,
    company_name: person ? null : n(v.company_name),
    legal_form: person ? null : n(v.legal_form),
    position: n(v.position),
    date_of_birth: person ? n(v.date_of_birth) : null,
    language: v.language,
    notes: n(v.notes),
    preferred_channel: v.preferred_channel === "" ? null : v.preferred_channel,
    blocked: v.blocked,
    external_ids: existing?.external_ids ?? {},
    completeness: existing?.completeness ?? "complete",
    identifiers: existing?.identifiers.map(({ kind, value }) => ({ kind, value })) ?? [],
    types: v.types,
    tags: v.tags
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean),
    addresses: v.addresses.map((a) => ({
      label: a.label,
      street: n(a.street),
      house_number: n(a.house_number),
      postal_code: n(a.postal_code),
      city: n(a.city),
      country: a.country,
      addition: n(a.addition),
      is_primary: a.is_primary,
    })),
    phones: v.phones.map((p) => ({ label: p.label, number: p.number.trim(), is_primary: p.is_primary })),
    emails: v.emails.map((e) => ({
      label: e.label || "work",
      email: e.email.trim(),
      is_primary: e.is_primary,
      is_portal_login: e.is_portal_login,
    })),
    // On edit the field is omitted: the API keeps existing bank accounts (mandate references).
    bank_accounts: existing ? undefined : v.bank_accounts.map((b) => ({
      label: n(b.label),
      iban: b.iban.replace(/\s+/g, "").toUpperCase(),
      bic: b.bic.trim() ? b.bic.trim().toUpperCase() : null,
      bank_name: n(b.bank_name),
      holder: n(b.holder),
      valid_from: b.valid_from,
      valid_to: b.valid_to || null,
    })),
  };
}

/** Query for GET /contacts/duplicates from the first entries of the form. */
export function duplicateQuery(v: ContactFormValues): URLSearchParams {
  const q = new URLSearchParams();
  const put = (key: string, value: string | undefined) => {
    if (value && value.trim()) q.set(key, value.trim());
  };
  if (v.kind === "person") {
    put("first_name", v.first_name);
    put("last_name", v.last_name);
  } else {
    put("company_name", v.company_name);
  }
  put("email", v.emails[0]?.email);
  put("phone", v.phones[0]?.number);
  put("iban", v.bank_accounts[0]?.iban.replace(/\s+/g, ""));
  return q;
}
