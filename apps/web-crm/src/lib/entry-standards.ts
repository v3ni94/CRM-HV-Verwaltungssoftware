/** Entry standards (Erfassungsstandards ES-01 to ES-10), mirror of
 *  `apps/api/src/mhvp/dataquality/rules.py` with the same rule ids. Only ES-01 (German postcode,
 *  five digits) is a hard error, also enforced by the API; every other finding is a non blocking
 *  hint. Texts live in the `EntryStandards` messages, keyed by `rule` and `field`. */

export type Severity = "error" | "warning" | "hint";
export type Finding = { rule: string; field: string; severity: Severity; params?: Record<string, string> };

const POSTCODE_DE = /^[0-9]{5}$/;
export const PROPERTY_NAME = /^\S.*\s[0-9]+\s?[A-Za-z]?(\s?[-/]\s?[0-9]+\s?[A-Za-z]?)?,\s[0-9]{5}\s\S.*$/;
const STREET_WITH_NUMBER = /\s[0-9]+\s?[A-Za-z]?$/;
const PARTICLES = new Set(["von", "van", "de", "der", "den", "zu", "zur", "vom", "di", "da", "del", "la", "le", "ten", "ter", "du", "dos", "af"]);
const COMPANY_MARKERS =
  /(^|[^\p{L}])(gmbh|mbh|ag|kg|ohg|gbr|ug|e\.\s?v\.|weg|hausverwaltung|verwaltung|stadtwerke|versicherung|bank|sparkasse|gesellschaft|stiftung|ltd|inc)(?=$|[^\p{L}])/iu;

const blank = (v: unknown) => v == null || (typeof v === "string" && v.trim() === "");
const str = (v: unknown) => (typeof v === "string" ? v.trim() : "");

/** ES-01: true when the postcode is set but not five digits for Germany. */
export function postcodeInvalid(country: string | null | undefined, postalCode: string | null | undefined): boolean {
  if ((country || "DE").toUpperCase() !== "DE" || blank(postalCode)) return false;
  return !POSTCODE_DE.test(str(postalCode));
}

export type PropertyDraft = {
  name?: string | null;
  street?: string | null;
  house_number?: string | null;
  postal_code?: string | null;
  city?: string | null;
  country?: string | null;
};

export function suggestPropertyName(d: PropertyDraft): string | null {
  const [street, number, postcode, city] = [d.street, d.house_number, d.postal_code, d.city].map(str);
  return street && number && postcode && city ? `${street} ${number}, ${postcode} ${city}` : null;
}

export function checkProperty(d: PropertyDraft): Finding[] {
  const out: Finding[] = [];
  if (postcodeInvalid(d.country, d.postal_code)) out.push({ rule: "ES-01", field: "postal_code", severity: "error" });
  for (const field of ["street", "house_number", "postal_code", "city"] as const) {
    if (blank(d[field])) out.push({ rule: "ES-02", field, severity: "warning" });
  }
  if (STREET_WITH_NUMBER.test(str(d.street)) && blank(d.house_number)) out.push({ rule: "ES-03", field: "street", severity: "warning" });
  const name = str(d.name);
  if (name && !PROPERTY_NAME.test(name)) {
    const suggestion = suggestPropertyName(d);
    out.push({ rule: "ES-04", field: "name", severity: "hint", params: suggestion ? { suggestion } : undefined });
  }
  return out;
}

export type ContactDraft = {
  kind?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  company_name?: string | null;
};

function looksLikeFullName(value: string): boolean {
  const words = value.split(/\s+/).filter(Boolean);
  return words.length >= 2 && !PARTICLES.has((words[0] ?? "").toLowerCase());
}

export function checkContact(d: ContactDraft): Finding[] {
  const out: Finding[] = [];
  if ((d.kind ?? "person") === "company") {
    if (blank(d.company_name)) out.push({ rule: "ES-08", field: "company_name", severity: "warning" });
    return out;
  }
  const first = str(d.first_name);
  const last = str(d.last_name);
  if (last.includes(",") || first.includes(",")) out.push({ rule: "ES-05", field: "last_name", severity: "warning" });
  else if (!first && looksLikeFullName(last)) out.push({ rule: "ES-06", field: "last_name", severity: "warning" });
  if (COMPANY_MARKERS.test(`${first} ${last}`)) out.push({ rule: "ES-07", field: "kind", severity: "warning" });
  if (!first && out.length === 0) out.push({ rule: "ES-08", field: "first_name", severity: "hint" });
  return out;
}

/** ES-09: ISO date before today (local calendar day). */
export function isPastDate(iso: string | null | undefined, today: Date = new Date()): boolean {
  if (!iso) return false;
  const pad = (n: number) => String(n).padStart(2, "0");
  const local = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
  return iso < local;
}

export function checkDeadline(d: { due_on?: string | null; assignee_user_id?: string | null }, today: Date = new Date()): Finding[] {
  const out: Finding[] = [];
  if (isPastDate(d.due_on, today)) out.push({ rule: "ES-09", field: "due_on", severity: "warning" });
  if (d.due_on && blank(d.assignee_user_id)) out.push({ rule: "ES-10", field: "assignee_user_id", severity: "warning" });
  return out;
}

/** Message key of a finding in the `EntryStandards` namespace. */
export function findingKey(f: Finding): string {
  if (f.rule === "ES-02" || f.rule === "ES-08") return `rules.${f.rule}.${f.field}`;
  if (f.rule === "ES-04") return `rules.ES-04.${f.params?.suggestion ? "suggest" : "plain"}`;
  return `rules.${f.rule}`;
}
