/**
 * Registry of the tenant switches for professionally open decisions (wave 16, package AE39).
 * One entry per switch with the read and write endpoint, the variants, the default and the
 * open question in docs/OPEN_QUESTIONS.md. The central page `/einstellungen/fachliche-regeln`
 * renders it; adding a switch means adding one entry here plus its texts in
 * `messages/{de,en}.json` under `BusinessRules` (business-rules.test.ts checks both).
 *
 * The defaults are the conservative variants of the API: nothing is booked, sent or deleted
 * unless the operator decides otherwise. The software decides no legal or tax question.
 * Paths are relative to `/api/v1` on the server and to `/api/bff` in the browser (the BFF
 * allow list already carries every write path used here).
 */

export type RuleGroup = "accounting" | "billing" | "hoa" | "portal" | "security" | "banking" | "platform";
export type RuleValue = string | boolean | number | null;
export type RuleKind = "enum" | "boolean" | "date" | "integer" | "count" | "link";

type Doc = Record<string, unknown>;

export type BusinessRule = {
  id: string;
  group: RuleGroup;
  /** Work package of wave 16 that introduced the switch. */
  pkg: string;
  kind: RuleKind;
  /** Allowed values of an enum, in the order shown. */
  options?: readonly string[];
  /** Message set of the option labels (`BusinessRules.options.<set>`), default the rule id. */
  optionSet?: string;
  /** Message key of title and description (`BusinessRules.rules.<textKey>`), default the id. */
  textKey?: string;
  /** Conservative default of the API, for display. */
  default: RuleValue;
  /** Entries of docs/OPEN_QUESTIONS.md that keep the decision open. */
  questions: readonly string[];
  /** Specialised mask (link "Fachmaske öffnen"). */
  href?: string;
  /** Any of these permissions shows the rule. */
  permission: readonly string[];
  read?: { path: string; pick: (doc: unknown) => RuleValue | undefined };
  write?: {
    method: "PUT" | "PATCH";
    /** Path below /api/bff, or a builder for rules that address one item (empty: not possible). */
    path: string | ((doc: unknown) => string);
    permission: string;
    /** The endpoint demands a reason (an input, at least `reasonMin` characters), always or
     *  only for some values. */
    needsReason?: boolean | ((value: RuleValue) => boolean);
    reasonMin?: number;
    body: (doc: unknown, value: RuleValue, reason: string) => unknown;
    /** Document after a successful write; default sets the rule's field. */
    apply?: (doc: unknown, value: RuleValue) => unknown;
  };
  /** Optional reset to the default (DELETE, AF19): removes the stored value on the server. */
  reset?: { path: string | ((doc: unknown) => string); permission: string };
  /** Field of the shared document (default for `pick` and `apply`). */
  field?: string;
  range?: readonly [number, number];
  /** The default of a link or count rule is a text (`rules.<id>.defaultText`). */
  defaultText?: boolean;
};

function rec(doc: unknown): Doc {
  return doc !== null && typeof doc === "object" && !Array.isArray(doc) ? (doc as Doc) : {};
}

function scalar(value: unknown): RuleValue | undefined {
  return typeof value === "string" || typeof value === "boolean" || typeof value === "number" || value === null
    ? value
    : undefined;
}

/** `pick` of a plain field of the shared document. */
function fieldPick(field: string): (doc: unknown) => RuleValue | undefined {
  return (doc) => scalar(rec(doc)[field]);
}

/** Partial update: only the changed field (PATCH and PUT bodies with optional fields). */
function fieldBody(field: string): (doc: unknown, value: RuleValue) => unknown {
  return (_doc, value) => ({ [field]: value });
}

/** AG03: thresholds of the onboarding person match are fractions (0,60) in the API, percent here. */
function ratio(value: RuleValue): string {
  return (Number(value) / 100).toFixed(2);
}
function percentOf(doc: unknown, field: string): RuleValue | undefined {
  const raw = Number(rec(doc)[field]);
  return Number.isFinite(raw) ? Math.round(raw * 100) : undefined;
}
function matchBody(doc: unknown, field: string, value: RuleValue): unknown {
  const other = field === "link_threshold" ? "suggest_threshold" : "link_threshold";
  return { [other]: Number(rec(doc)[other]).toFixed(2), [field]: ratio(value) };
}

function numberField(doc: unknown, field: string): RuleValue | undefined {
  const value = rec(doc)[field];
  return typeof value === "number" ? value : undefined;
}

/** Number of released text blocks in the answer of GET /document-text-blocks/codes. */
function releasedCount(doc: unknown): RuleValue | undefined {
  const items = rec(doc).items;
  return Array.isArray(items) ? items.filter((i) => rec(i).released === true).length : undefined;
}

const SETTINGS = ["tenant_settings:read"] as const;
const ACCOUNTING = ["accounting:read"] as const;

const TAX_FIELDS = [
  "input_tax_enabled",
  "input_tax_account_number",
  "construction_withholding_enabled",
  "construction_withholding_percent",
  "section_35a_enabled",
  "approval_limits_enabled",
  "subledger_exclude_written_off",
  "section_35a_basis",
] as const;

/** PUT /accounting/tax/settings replaces the whole document: send it back unchanged except for
 *  the one field (a missing field would fall back to the API default). */
function taxBody(doc: unknown, value: RuleValue): unknown {
  const d = rec(doc);
  const out: Doc = {};
  for (const key of TAX_FIELDS) if (key in d) out[key] = d[key];
  const limits = Array.isArray(d.approval_limits) ? d.approval_limits : [];
  out.approval_limits = limits.map((l) => ({ role_code: rec(l).role_code, limit_amount: rec(l).limit_amount }));
  out.subledger_exclude_written_off = value;
  return out;
}

/** Same full document as `taxBody`, setting the given field (AI18). */
function taxFieldBody(field: (typeof TAX_FIELDS)[number]): (doc: unknown, value: RuleValue) => unknown {
  return (doc, value) => {
    const out = rec(taxBody(doc, rec(doc).subledger_exclude_written_off as RuleValue));
    out[field] = value;
    return out;
  };
}

/** PUT /deposit-hint-settings needs the whole document (AI18, GAH-111). */
function depositHintBody(doc: unknown, value: RuleValue): unknown {
  const d = rec(doc);
  return {
    deposit_limit_hint_enabled: value,
    factor_months: d.factor_months ?? "3",
    max_installments: d.max_installments ?? 3,
    rent_payment_codes: Array.isArray(d.rent_payment_codes) ? d.rent_payment_codes : ["rent"],
  };
}

/** PUT /hoa/meeting-settings needs the invitation weeks and the virtual switch every time. */
function meetingBody(field: string): (doc: unknown, value: RuleValue) => unknown {
  return (doc, value) => {
    const d = rec(doc);
    return {
      invitation_weeks: d.invitation_weeks,
      virtual_meetings_enabled: d.virtual_meetings_enabled,
      virtual_basis_term_lock_enabled: d.virtual_basis_term_lock_enabled,
      virtual_basis_transition_date: d.virtual_basis_transition_date ?? null,
      [field]: value,
    };
  };
}

function onlineBody(field: string): (doc: unknown, value: RuleValue) => unknown {
  return (doc, value) => {
    const d = rec(doc);
    return { enabled: d.enabled, proxy_conflict_mode: d.proxy_conflict_mode, [field]: value };
  };
}

/** PUT bodies that carry a fixed set of fields (the API resets a missing field to its default). */
function mergeBody(keys: readonly string[], field: string): (doc: unknown, value: RuleValue) => unknown {
  return (doc, value) => {
    const d = rec(doc);
    const out: Doc = {};
    for (const key of keys) out[key] = d[key];
    out[field] = value;
    return out;
  };
}

/** PUT /auth/mfa-policy needs all three fields; the role list is kept as it is. */
function mfaBody(field: string): (doc: unknown, value: RuleValue) => unknown {
  return (doc, value) => {
    const d = rec(doc);
    return {
      crm_mode: d.crm_mode,
      crm_role_codes: Array.isArray(d.crm_role_codes) ? d.crm_role_codes : [],
      portal_required: d.portal_required,
      [field]: value,
    };
  };
}

/** Newest chart version of the list GET /accounting/templates (highest version number). */
function newestTemplate(doc: unknown): Doc | null {
  if (!Array.isArray(doc) || doc.length === 0) return null;
  return rec([...doc].sort((x, y) => Number(rec(y).version ?? 0) - Number(rec(x).version ?? 0))[0]);
}

const LEGAL_BASIS_PURPOSES = [
  { slug: "email-delivery", purpose: "email_delivery", options: ["consent", "contract", "legitimate_interest"], questions: ["AE34-01", "AC06-01"] },
  { slug: "data-sharing", purpose: "data_sharing", options: ["consent", "contract", "legitimate_interest"], questions: ["AE34-01", "AC06-01"] },
  { slug: "marketing", purpose: "marketing", options: ["consent", "legitimate_interest"], questions: ["AE34-02", "AC06-01"] },
  { slug: "portal-terms", purpose: "portal_terms", options: ["consent", "contract"], questions: ["AE34-01", "AC06-03"] },
] as const;

function legalBasisItem(doc: unknown, purpose: string): Doc {
  const items = rec(doc).items;
  return Array.isArray(items) ? rec(items.find((i) => rec(i).purpose === purpose)) : {};
}

/** Legal basis per processing purpose (AE34): a basis other than consent needs a justification. */
const legalBasisRules: BusinessRule[] = LEGAL_BASIS_PURPOSES.map(({ slug, purpose, options, questions }) => ({
  id: `legal-basis-${slug}`,
  group: "security",
  pkg: "AE34",
  kind: "enum",
  options,
  optionSet: "legal-basis",
  textKey: `legal-basis-${slug}`,
  default: "consent",
  questions,
  permission: ["contacts:read"],
  read: { path: "consent-legal-basis", pick: (doc) => scalar(legalBasisItem(doc, purpose).basis) },
  reset: { path: `consent-legal-basis/${purpose}`, permission: "contacts:approve" },
  write: {
    method: "PUT",
    path: `consent-legal-basis/${purpose}`,
    permission: "contacts:approve",
    needsReason: (value) => value !== "consent",
    reasonMin: 10,
    body: (_doc, value, reason) => ({ basis: value, note: reason.trim() || null }),
    apply: (doc, value) => {
      const d = rec(doc);
      const items = Array.isArray(d.items) ? d.items : [];
      return { ...d, items: items.map((i) => (rec(i).purpose === purpose ? { ...rec(i), basis: value } : i)) };
    },
  },
}));

const ACQUISITION_KINDS = ["purchase", "first_acquisition", "inheritance", "foreclosure", "gift", "other"] as const;

function acquisitionItem(doc: unknown, kind: string): Doc {
  const items = rec(doc).items;
  return Array.isArray(items) ? rec(items.find((i) => rec(i).acquisition_kind === kind)) : {};
}

const acquisitionRules: BusinessRule[] = ACQUISITION_KINDS.map((kind) => ({
  id: `acquisition-${kind.replace("_", "-")}`,
  group: "hoa",
  pkg: "AE10",
  kind: "enum",
  options: ["manual_release", "by_due_date", "by_resolution_date"],
  optionSet: "acquisition",
  textKey: "acquisition",
  default: "manual_release",
  questions: ["AA07-01", "P01"],
  href: "/weg",
  permission: ACCOUNTING,
  read: { path: "hoa/acquisition-rules", pick: (doc) => scalar(acquisitionItem(doc, kind).variant) },
  write: {
    method: "PUT",
    path: `hoa/acquisition-rules/${kind}`,
    permission: "accounting:approve",
    body: (doc, value) => ({ variant: value, source_note: acquisitionItem(doc, kind).source_note ?? null }),
    apply: (doc, value) => {
      const d = rec(doc);
      const items = Array.isArray(d.items) ? d.items : [];
      return { ...d, items: items.map((i) => (rec(i).acquisition_kind === kind ? { ...rec(i), variant: value } : i)) };
    },
  },
}));

export const BUSINESS_RULES: readonly BusinessRule[] = [
  // --- Buchhaltung ---------------------------------------------------------------------------
  {
    id: "rent-invoice-numbering",
    group: "accounting",
    pkg: "AE04",
    kind: "enum",
    options: ["draft_numbers", "regular_numbers", "reject_when_g1_closed"],
    default: "draft_numbers",
    questions: ["AC03-01"],
    href: "/vertraege",
    permission: ["contracts:read"],
    read: { path: "accounting/rent-invoices/numbering-mode", pick: fieldPick("mode") },
    write: {
      method: "PUT",
      path: "accounting/rent-invoices/numbering-mode",
      permission: "tenant_settings:update",
      body: fieldBody("mode"),
    },
    field: "mode",
  },
  {
    id: "subledger-exclude-written-off",
    group: "accounting",
    pkg: "AE06",
    kind: "boolean",
    default: true,
    questions: ["AC01-02"],
    href: "/buchhaltung",
    permission: SETTINGS,
    read: { path: "accounting/tax/settings", pick: fieldPick("subledger_exclude_written_off") },
    write: {
      method: "PUT",
      path: "accounting/tax/settings",
      permission: "tenant_settings:update",
      body: taxBody,
    },
    field: "subledger_exclude_written_off",
  },
  {
    id: "tax-35a-basis",
    group: "accounting",
    pkg: "AI18",
    kind: "enum",
    options: ["invoice_date", "payment_date"],
    default: "invoice_date",
    questions: ["AI17-01"],
    href: "/buchhaltung",
    permission: SETTINGS,
    read: { path: "accounting/tax/settings", pick: fieldPick("section_35a_basis") },
    write: {
      method: "PUT",
      path: "accounting/tax/settings",
      permission: "tenant_settings:update",
      body: taxFieldBody("section_35a_basis"),
    },
    field: "section_35a_basis",
  },
  {
    id: "deposit-limit-hint",
    group: "billing",
    pkg: "AI18",
    kind: "boolean",
    default: false,
    questions: ["AI17-04"],
    href: "/vertraege",
    permission: SETTINGS,
    read: { path: "deposit-hint-settings", pick: fieldPick("deposit_limit_hint_enabled") },
    write: {
      method: "PUT",
      path: "deposit-hint-settings",
      permission: "tenant_settings:update",
      body: depositHintBody,
    },
    field: "deposit_limit_hint_enabled",
  },
  {
    id: "period-lock-mode",
    group: "accounting",
    pkg: "AE20",
    kind: "enum",
    options: ["ledger_only", "object_period"],
    default: "ledger_only",
    questions: ["P06-02", "AA08-01"],
    href: "/einstellungen/buchhaltung/periodensperren",
    permission: ACCOUNTING,
    read: { path: "accounting/period-locks/settings", pick: fieldPick("lock_mode") },
    write: {
      method: "PUT",
      path: "accounting/period-locks/settings",
      permission: "tenant_settings:update",
      body: fieldBody("lock_mode"),
    },
    field: "lock_mode",
  },
  {
    id: "period-lock-auto",
    group: "accounting",
    pkg: "AE20",
    kind: "boolean",
    default: false,
    questions: ["P06-02", "AA08-01"],
    href: "/einstellungen/buchhaltung/periodensperren",
    permission: ACCOUNTING,
    read: { path: "accounting/period-locks/settings", pick: fieldPick("auto_lock_on_close") },
    write: {
      method: "PUT",
      path: "accounting/period-locks/settings",
      permission: "tenant_settings:update",
      body: fieldBody("auto_lock_on_close"),
    },
    field: "auto_lock_on_close",
  },
  {
    id: "period-lock-reopen",
    group: "accounting",
    pkg: "AE20",
    kind: "boolean",
    default: false,
    questions: ["P06-02", "AA08-01"],
    href: "/einstellungen/buchhaltung/periodensperren",
    permission: ACCOUNTING,
    read: { path: "accounting/period-locks/settings", pick: fieldPick("reopen_enabled") },
    write: {
      method: "PUT",
      path: "accounting/period-locks/settings",
      permission: "tenant_settings:update",
      body: fieldBody("reopen_enabled"),
    },
    field: "reopen_enabled",
  },
  {
    // PUT /accounting/templates/{id}/four-eyes addresses one chart version and demands a
    // reason; the newest version is shown and changed (a released version answers 409).
    id: "chart-four-eyes",
    group: "accounting",
    pkg: "AE02",
    kind: "boolean",
    default: true,
    questions: ["M10-01"],
    href: "/einstellungen/buchhaltung/kontenrahmen",
    permission: ACCOUNTING,
    read: {
      path: "accounting/templates",
      pick: (doc) => {
        const newest = newestTemplate(doc);
        if (!newest) return undefined;
        return typeof newest.four_eyes_required === "boolean" ? newest.four_eyes_required : true;
      },
    },
    write: {
      method: "PUT",
      path: (doc) => {
        const id = newestTemplate(doc)?.id;
        return typeof id === "string" ? `accounting/templates/${id}/four-eyes` : "";
      },
      permission: "accounting:approve",
      needsReason: true,
      body: (_doc, value, reason) => ({ required: value, reason: reason.trim() }),
      apply: (doc, value) => {
        const newest = newestTemplate(doc);
        return Array.isArray(doc) ? doc.map((t) => (t === newest ? { ...rec(t), four_eyes_required: value } : t)) : doc;
      },
    },
  },
  {
    id: "chart-coverage",
    group: "accounting",
    pkg: "AE02",
    kind: "link",
    default: null,
    defaultText: true,
    questions: ["P07-04", "P07-05"],
    href: "/einstellungen/buchhaltung/kontenrahmen",
    permission: ACCOUNTING,
  },
  {
    id: "interest-tax",
    group: "accounting",
    pkg: "AE05",
    kind: "count",
    default: 0,
    defaultText: true,
    questions: ["P01-01"],
    href: "/buchhaltung",
    permission: ACCOUNTING,
    // Buchungskreise mit mindestens einem Steuerkonto (GAE-38, tenantweite Zusammenfassung).
    read: { path: "accounting/interest-tax-config", pick: (doc) => numberField(doc, "ledgers_configured") },
  },
  {
    // AI03 (GAH-110): day count of the default interest; default as before (days/365).
    id: "dunning-day-count",
    group: "accounting",
    pkg: "AI03",
    kind: "enum",
    options: ["act_365_fixed", "act_act"],
    default: "act_365_fixed",
    questions: ["AI03-01"],
    href: "/buchhaltung/mahnwesen",
    permission: ACCOUNTING,
    read: { path: "accounting/dunning-interest", pick: fieldPick("day_count") },
    write: {
      method: "PUT",
      path: "accounting/dunning-interest",
      permission: "accounting:approve",
      body: fieldBody("day_count"),
    },
    field: "day_count",
  },
  {
    id: "rule-checkpoints",
    group: "accounting",
    pkg: "AE19",
    kind: "count",
    default: 0,
    defaultText: true,
    questions: ["AB10-01"],
    href: "/buchhaltung",
    permission: ACCOUNTING,
    read: { path: "accounting/rule-versions/checkpoints", pick: (doc) => (Array.isArray(doc) ? doc.length : undefined) },
  },
  // --- Abrechnung Miete -----------------------------------------------------------------------
  {
    id: "advance-open-mode",
    group: "billing",
    pkg: "AE15",
    kind: "enum",
    options: ["info_only", "offset_reversal", "balance_against_due"],
    default: "info_only",
    questions: ["AC10-01", "M17-03", "P06-01"],
    href: "/abrechnung",
    permission: ACCOUNTING,
    read: { path: "billing/advance-rule", pick: fieldPick("open_advance_mode") },
    write: {
      method: "PUT",
      path: "billing/advance-rule",
      permission: "accounting:update",
      body: fieldBody("open_advance_mode"),
    },
    field: "open_advance_mode",
  },
  {
    id: "allocation-basis-block",
    group: "billing",
    pkg: "AE17",
    kind: "boolean",
    default: true,
    questions: ["M17-01"],
    href: "/abrechnung",
    permission: ACCOUNTING,
    read: { path: "billing/allocation-basis-setting", pick: fieldPick("block_output") },
    write: {
      method: "PUT",
      path: "billing/allocation-basis-setting",
      permission: "accounting:update",
      body: fieldBody("block_output"),
    },
    field: "block_output",
  },
  {
    id: "deadline-policy",
    group: "billing",
    pkg: "AE18",
    kind: "enum",
    options: ["block_claims", "notice"],
    default: "block_claims",
    questions: ["M17-04"],
    href: "/abrechnung",
    permission: ACCOUNTING,
    read: { path: "billing/deadline-settings", pick: fieldPick("policy") },
    write: {
      method: "PUT",
      path: "billing/deadline-settings",
      permission: "accounting:approve",
      body: fieldBody("policy"),
    },
    field: "policy",
  },
  {
    id: "deadline-watch",
    group: "billing",
    pkg: "AE18",
    kind: "boolean",
    default: false,
    questions: ["M17-04"],
    href: "/abrechnung",
    permission: ACCOUNTING,
    read: { path: "billing/deadline-settings", pick: fieldPick("watch_enabled") },
    write: {
      method: "PUT",
      path: "billing/deadline-settings",
      permission: "accounting:approve",
      body: fieldBody("watch_enabled"),
    },
    field: "watch_enabled",
  },
  {
    id: "deadline-warn-first",
    group: "billing",
    pkg: "AE18",
    kind: "integer",
    range: [1, 365],
    default: 60,
    questions: ["M17-04"],
    href: "/abrechnung",
    permission: ACCOUNTING,
    read: { path: "billing/deadline-settings", pick: fieldPick("warn_days_first") },
    write: {
      method: "PUT",
      path: "billing/deadline-settings",
      permission: "accounting:approve",
      body: fieldBody("warn_days_first"),
    },
    field: "warn_days_first",
  },
  {
    id: "deadline-warn-second",
    group: "billing",
    pkg: "AE18",
    kind: "integer",
    range: [1, 365],
    default: 30,
    questions: ["M17-04"],
    href: "/abrechnung",
    permission: ACCOUNTING,
    read: { path: "billing/deadline-settings", pick: fieldPick("warn_days_second") },
    write: {
      method: "PUT",
      path: "billing/deadline-settings",
      permission: "accounting:approve",
      body: fieldBody("warn_days_second"),
    },
    field: "warn_days_second",
  },
  {
    id: "text-blocks",
    group: "billing",
    pkg: "AE16",
    kind: "count",
    default: 0,
    defaultText: true,
    questions: ["AA11-01", "AA11-02"],
    href: "/einstellungen/textbausteine",
    permission: ["documents:read"],
    // Freigegebene Textbausteine (GAE-38).
    read: { path: "document-text-blocks/codes", pick: releasedCount },
  },
  {
    // PUT /document-text-blocks/policy: switching off demands a reason (AF12, GAE-16).
    id: "text-block-second-person",
    group: "billing",
    pkg: "AF12",
    kind: "boolean",
    default: true,
    questions: ["AA11-01", "AA11-02"],
    href: "/einstellungen/textbausteine",
    permission: SETTINGS,
    read: { path: "document-text-blocks/policy", pick: fieldPick("require_second_person") },
    write: {
      method: "PUT",
      path: "document-text-blocks/policy",
      permission: "tenant_settings:update",
      needsReason: (value) => value === false,
      reasonMin: 10,
      body: (_doc, value, reason) => ({ require_second_person: value, reason: reason.trim() || null }),
    },
    field: "require_second_person",
  },
  // --- WEG -----------------------------------------------------------------------------------
  {
    id: "opening-lock-mode",
    group: "hoa",
    pkg: "AE07",
    kind: "enum",
    options: ["locked", "logged", "four_eyes"],
    default: "locked",
    questions: ["V01-01"],
    href: "/weg",
    permission: SETTINGS,
    read: { path: "hoa/reserve-policy", pick: fieldPick("opening_lock_mode") },
    write: {
      method: "PUT",
      path: "hoa/reserve-policy",
      permission: "tenant_settings:update",
      body: fieldBody("opening_lock_mode"),
    },
    field: "opening_lock_mode",
  },
  {
    id: "reserve-plan-tax",
    group: "hoa",
    pkg: "AE07",
    kind: "link",
    default: null,
    defaultText: true,
    questions: ["AE07-01"],
    href: "/weg",
    permission: ACCOUNTING,
  },
  {
    id: "reserve-payment-mode",
    group: "hoa",
    pkg: "AE08",
    kind: "enum",
    options: ["bound_only", "plan_ratio_proposal"],
    default: "bound_only",
    questions: ["P07-02", "P07-04"],
    href: "/weg",
    permission: SETTINGS,
    read: { path: "hoa/reserve-payment-settings", pick: fieldPick("mode") },
    write: {
      method: "PUT",
      path: "hoa/reserve-payment-settings",
      permission: "tenant_settings:update",
      body: fieldBody("mode"),
    },
    field: "mode",
  },
  {
    id: "plan-change-mode",
    group: "hoa",
    pkg: "AE09",
    kind: "enum",
    options: ["notice", "due_now", "next_instalment"],
    default: "notice",
    questions: ["M12-L2", "P07-01"],
    href: "/weg",
    permission: SETTINGS,
    read: { path: "hoa/plan-change-settings", pick: fieldPick("mode") },
    write: {
      method: "PUT",
      path: "hoa/plan-change-settings",
      permission: "tenant_settings:update",
      body: fieldBody("mode"),
    },
    field: "mode",
  },
  {
    id: "correction-report",
    group: "hoa",
    pkg: "AF08",
    kind: "boolean",
    default: false,
    questions: ["P02"],
    href: "/weg",
    permission: SETTINGS,
    read: { path: "hoa/correction-report-settings", pick: fieldPick("enabled") },
    write: {
      method: "PUT",
      path: "hoa/correction-report-settings",
      permission: "tenant_settings:update",
      body: fieldBody("enabled"),
    },
    field: "enabled",
  },
  ...acquisitionRules,
  {
    id: "allocation-proposal",
    group: "hoa",
    pkg: "AG20",
    kind: "boolean",
    default: false,
    questions: ["AA07-01", "P01"],
    href: "/weg",
    permission: SETTINGS,
    read: { path: "hoa/allocation-proposal-settings", pick: fieldPick("enabled") },
    write: {
      method: "PUT",
      path: "hoa/allocation-proposal-settings",
      permission: "tenant_settings:update",
      body: fieldBody("enabled"),
    },
    field: "enabled",
  },
  {
    id: "virtual-meetings",
    group: "hoa",
    pkg: "AE12",
    kind: "boolean",
    default: false,
    questions: ["V13", "AA06-02"],
    href: "/weg",
    permission: SETTINGS,
    read: { path: "hoa/meeting-settings", pick: fieldPick("virtual_meetings_enabled") },
    write: {
      method: "PUT",
      path: "hoa/meeting-settings",
      permission: "tenant_settings:update",
      body: meetingBody("virtual_meetings_enabled"),
    },
    field: "virtual_meetings_enabled",
  },
  {
    id: "virtual-basis-term-lock",
    group: "hoa",
    pkg: "AE12",
    kind: "boolean",
    default: false,
    questions: ["AA06-02"],
    href: "/weg",
    permission: SETTINGS,
    read: { path: "hoa/meeting-settings", pick: fieldPick("virtual_basis_term_lock_enabled") },
    write: {
      method: "PUT",
      path: "hoa/meeting-settings",
      permission: "tenant_settings:update",
      body: meetingBody("virtual_basis_term_lock_enabled"),
    },
    field: "virtual_basis_term_lock_enabled",
  },
  {
    id: "virtual-basis-transition-date",
    group: "hoa",
    pkg: "AE12",
    kind: "date",
    default: null,
    questions: ["AA06-02"],
    href: "/weg",
    permission: SETTINGS,
    read: { path: "hoa/meeting-settings", pick: fieldPick("virtual_basis_transition_date") },
    write: {
      method: "PUT",
      path: "hoa/meeting-settings",
      permission: "tenant_settings:update",
      body: meetingBody("virtual_basis_transition_date"),
    },
    field: "virtual_basis_transition_date",
  },
  {
    id: "online-meeting",
    group: "hoa",
    pkg: "AE12",
    kind: "boolean",
    default: false,
    questions: ["AD06-01"],
    href: "/weg",
    permission: SETTINGS,
    read: { path: "hoa/online-meeting-settings", pick: fieldPick("enabled") },
    write: {
      method: "PUT",
      path: "hoa/online-meeting-settings",
      permission: "tenant_settings:update",
      body: onlineBody("enabled"),
    },
    field: "enabled",
  },
  {
    id: "proxy-conflict-mode",
    group: "hoa",
    pkg: "AE31",
    kind: "enum",
    options: ["flag", "first_vote", "proxy_priority", "own_priority"],
    default: "flag",
    questions: ["AD06-02"],
    href: "/weg",
    permission: SETTINGS,
    read: { path: "hoa/online-meeting-settings", pick: fieldPick("proxy_conflict_mode") },
    write: {
      method: "PUT",
      path: "hoa/online-meeting-settings",
      permission: "tenant_settings:update",
      body: onlineBody("proxy_conflict_mode"),
    },
    field: "proxy_conflict_mode",
  },
  {
    id: "portal-circular-resolution",
    group: "hoa",
    pkg: "AG07",
    kind: "boolean",
    default: false,
    questions: ["AE31-01"],
    href: "/weg",
    permission: SETTINGS,
    read: { path: "hoa/portal-circular-settings", pick: fieldPick("enabled") },
    write: {
      method: "PUT",
      path: "hoa/portal-circular-settings",
      permission: "tenant_settings:update",
      body: fieldBody("enabled"),
    },
    field: "enabled",
  },
  // --- Portal ---------------------------------------------------------------------------------
  {
    id: "owner-rental-income",
    group: "portal",
    pkg: "AE13",
    kind: "boolean",
    default: false,
    questions: ["P13-01", "Q10-02"],
    href: "/einstellungen/portalformulare",
    permission: ["tickets:read"],
    read: { path: "portal-admin/features", pick: fieldPick("owner_rental_income_enabled") },
    write: {
      method: "PATCH",
      path: "portal-admin/features",
      permission: "tenant_settings:update",
      body: fieldBody("owner_rental_income_enabled"),
    },
    field: "owner_rental_income_enabled",
  },
  {
    id: "portal-owner-receipts",
    group: "portal",
    pkg: "AG09",
    kind: "boolean",
    default: false,
    questions: ["AG09-01"],
    href: "/einstellungen/portalformulare",
    permission: ["tickets:read"],
    read: { path: "portal-admin/features", pick: fieldPick("portal_owner_receipts_enabled") },
    write: {
      method: "PATCH",
      path: "portal-admin/features",
      permission: "tenant_settings:update",
      body: fieldBody("portal_owner_receipts_enabled"),
    },
    field: "portal_owner_receipts_enabled",
  },
  {
    id: "owner-rental-statements-portal",
    group: "portal",
    pkg: "AF15",
    kind: "boolean",
    default: false,
    questions: ["AF15-01"],
    href: "/einstellungen/portalformulare",
    permission: ["tickets:read"],
    read: { path: "portal-admin/features", pick: fieldPick("owner_rental_statements_enabled") },
    write: {
      method: "PATCH",
      path: "portal-admin/features",
      permission: "tenant_settings:update",
      body: fieldBody("owner_rental_statements_enabled"),
    },
    field: "owner_rental_statements_enabled",
  },
  {
    id: "owner-hoa-rental-statements-portal",
    group: "portal",
    pkg: "AG12",
    kind: "boolean",
    default: false,
    questions: ["AF25-02"],
    href: "/einstellungen/portalformulare",
    permission: ["tickets:read"],
    read: {
      path: "portal-admin/features",
      pick: fieldPick("owner_hoa_rental_statements_enabled"),
    },
    write: {
      method: "PATCH",
      path: "portal-admin/features",
      permission: "tenant_settings:update",
      body: fieldBody("owner_hoa_rental_statements_enabled"),
    },
    field: "owner_hoa_rental_statements_enabled",
  },
  {
    id: "tenant-statement-portal",
    group: "portal",
    pkg: "AF16",
    kind: "boolean",
    default: false,
    questions: ["AF16-01"],
    href: "/einstellungen/portalformulare",
    permission: ["tickets:read"],
    read: { path: "portal-admin/features", pick: fieldPick("tenant_statement_enabled") },
    write: {
      method: "PATCH",
      path: "portal-admin/features",
      permission: "tenant_settings:update",
      body: fieldBody("tenant_statement_enabled"),
    },
    field: "tenant_statement_enabled",
  },
  {
    id: "owner-ticket-scope",
    group: "portal",
    pkg: "AE13",
    kind: "enum",
    options: ["none", "released", "property"],
    default: "released",
    questions: ["P13-01"],
    href: "/einstellungen/portalformulare",
    permission: ["tickets:read"],
    read: { path: "portal-admin/features", pick: fieldPick("owner_ticket_scope") },
    write: {
      method: "PATCH",
      path: "portal-admin/features",
      permission: "tenant_settings:update",
      body: fieldBody("owner_ticket_scope"),
    },
    field: "owner_ticket_scope",
  },
  {
    id: "provider-rating-display",
    group: "portal",
    pkg: "AE30",
    kind: "enum",
    options: ["off", "staff", "all"],
    default: "off",
    questions: ["AA14-02", "AE30-02"],
    href: "/einstellungen/portalformulare",
    permission: ["tickets:read"],
    read: { path: "portal-admin/features", pick: fieldPick("provider_rating_display") },
    write: {
      method: "PATCH",
      path: "portal-admin/features",
      permission: "tenant_settings:update",
      body: fieldBody("provider_rating_display"),
    },
    field: "provider_rating_display",
  },
  {
    id: "portal-chat-bot",
    group: "portal",
    pkg: "AE28",
    kind: "boolean",
    default: false,
    questions: ["AE28-01", "AE28-03"],
    href: "/einstellungen/portalformulare",
    permission: ["tickets:read"],
    read: { path: "portal-admin/features", pick: fieldPick("chat_bot_enabled") },
    write: {
      method: "PATCH",
      path: "portal-admin/features",
      permission: "tenant_settings:update",
      body: fieldBody("chat_bot_enabled"),
    },
    field: "chat_bot_enabled",
  },
  {
    id: "portal-chat-privacy",
    group: "portal",
    pkg: "AE28",
    kind: "boolean",
    default: false,
    questions: ["AE28-01", "AE28-02"],
    href: "/einstellungen/portalformulare",
    permission: ["tickets:read"],
    read: { path: "portal-admin/features", pick: fieldPick("privacy_feature_enabled") },
    write: {
      method: "PATCH",
      path: "portal-admin/features",
      permission: "tenant_settings:update",
      body: fieldBody("privacy_feature_enabled"),
    },
    field: "privacy_feature_enabled",
  },
  {
    id: "terms-version-mode",
    group: "portal",
    pkg: "AE29",
    kind: "enum",
    options: ["manual", "follow_text"],
    default: "manual",
    questions: ["AE29-01", "AC06-03"],
    href: "/einstellungen/portal-rechtstexte",
    permission: SETTINGS,
    read: { path: "tenant/legal-texts-config", pick: fieldPick("terms_version_mode") },
    write: {
      method: "PUT",
      path: "tenant/legal-texts-config",
      permission: "contacts:approve",
      body: fieldBody("terms_version_mode"),
    },
    field: "terms_version_mode",
  },
  // --- Sicherheit und Datenschutz -------------------------------------------------------------
  ...legalBasisRules,
  {
    id: "mfa-crm-mode",
    group: "security",
    pkg: "AE27",
    kind: "enum",
    options: ["voluntary", "all_staff", "roles"],
    default: "voluntary",
    questions: ["AE27-01"],
    href: "/einstellungen/rollen",
    permission: SETTINGS,
    read: { path: "auth/mfa-policy", pick: fieldPick("crm_mode") },
    write: { method: "PUT", path: "auth/mfa-policy", permission: "tenant_settings:update", body: mfaBody("crm_mode") },
    field: "crm_mode",
  },
  {
    id: "mfa-portal-required",
    group: "security",
    pkg: "AE27",
    kind: "boolean",
    default: false,
    questions: ["AE27-01"],
    href: "/einstellungen/rollen",
    permission: SETTINGS,
    read: { path: "auth/mfa-policy", pick: fieldPick("portal_required") },
    write: { method: "PUT", path: "auth/mfa-policy", permission: "tenant_settings:update", body: mfaBody("portal_required") },
    field: "portal_required",
  },
  {
    id: "mfa-admin-reset",
    group: "security",
    pkg: "AI09",
    kind: "boolean",
    default: false,
    questions: ["AI09-01"],
    href: "/einstellungen/rollen",
    permission: SETTINGS,
    read: { path: "auth/mfa-reset/settings", pick: fieldPick("enabled") },
    write: { method: "PUT", path: "auth/mfa-reset/settings", permission: "tenant_settings:update", body: fieldBody("enabled") },
    field: "enabled",
  },
  {
    id: "access-export-third-party",
    group: "security",
    pkg: "AE33",
    kind: "enum",
    options: ["none", "names"],
    default: "none",
    questions: ["AC07-01", "AE33-02"],
    href: "/einstellungen/datenschutz",
    permission: SETTINGS,
    read: { path: "contact-access-export-settings", pick: fieldPick("third_party_scope") },
    write: {
      method: "PUT",
      path: "contact-access-export-settings",
      permission: "tenant_settings:update",
      body: mergeBody(["third_party_scope", "include_internal_notes"], "third_party_scope"),
    },
    field: "third_party_scope",
  },
  {
    id: "access-export-internal-notes",
    group: "security",
    pkg: "AE33",
    kind: "boolean",
    default: false,
    questions: ["AC07-01", "AE33-02"],
    href: "/einstellungen/datenschutz",
    permission: SETTINGS,
    read: { path: "contact-access-export-settings", pick: fieldPick("include_internal_notes") },
    write: {
      method: "PUT",
      path: "contact-access-export-settings",
      permission: "tenant_settings:update",
      body: mergeBody(["third_party_scope", "include_internal_notes"], "include_internal_notes"),
    },
    field: "include_internal_notes",
  },
  {
    id: "document-trash-enabled",
    group: "security",
    pkg: "AE33",
    kind: "boolean",
    default: false,
    questions: ["AC07-03", "AE33-01"],
    href: "/einstellungen/aufbewahrung",
    permission: SETTINGS,
    read: { path: "documents/trash-settings", pick: fieldPick("enabled") },
    write: {
      method: "PUT",
      path: "documents/trash-settings",
      permission: "tenant_settings:update",
      body: mergeBody(["enabled", "retention_days"], "enabled"),
    },
    field: "enabled",
  },
  {
    id: "document-trash-days",
    group: "security",
    pkg: "AE33",
    kind: "integer",
    range: [1, 365],
    default: 30,
    questions: ["AC07-03", "AE33-01"],
    href: "/einstellungen/aufbewahrung",
    permission: SETTINGS,
    read: { path: "documents/trash-settings", pick: fieldPick("retention_days") },
    write: {
      method: "PUT",
      path: "documents/trash-settings",
      permission: "tenant_settings:update",
      body: mergeBody(["enabled", "retention_days"], "retention_days"),
    },
    field: "retention_days",
  },
  // --- Bank und Automatik ---------------------------------------------------------------------
  {
    // Switching on needs an open G1 and a request approved by a second person: read-only here.
    id: "automation-switch",
    group: "banking",
    pkg: "AE03",
    kind: "boolean",
    default: false,
    questions: ["BK2-03", "M12-09"],
    href: "/einstellungen/buchhaltung/automatik",
    permission: ACCOUNTING,
    read: { path: "banking/automation/switch-requests", pick: fieldPick("enabled") },
  },
  {
    id: "credit-payable-mode",
    group: "banking",
    pkg: "AE22",
    kind: "enum",
    options: ["off", "subledger", "reclass"],
    default: "off",
    questions: ["AE22-01", "Q01-01", "P04-04"],
    href: "/bank/zahllauf",
    permission: ACCOUNTING,
    read: { path: "accounting/credit-payables/settings", pick: fieldPick("mode") },
    write: {
      method: "PUT",
      path: "accounting/credit-payables/settings",
      permission: "tenant_settings:update",
      body: fieldBody("mode"),
    },
    field: "mode",
  },
  {
    id: "credit-payable-four-eyes",
    group: "banking",
    pkg: "AE22",
    kind: "boolean",
    default: true,
    questions: ["AE22-01", "Q01-01"],
    href: "/bank/zahllauf",
    permission: ACCOUNTING,
    read: { path: "accounting/credit-payables/settings", pick: fieldPick("four_eyes_required") },
    write: {
      method: "PUT",
      path: "accounting/credit-payables/settings",
      permission: "tenant_settings:update",
      body: fieldBody("four_eyes_required"),
    },
    field: "four_eyes_required",
  },
  {
    id: "ebics-enabled",
    group: "banking",
    pkg: "AE23",
    kind: "boolean",
    default: false,
    questions: ["AE23-01"],
    href: "/bank",
    permission: ACCOUNTING,
    read: { path: "banking/ebics/status", pick: fieldPick("enabled") },
    write: {
      method: "PUT",
      path: "banking/ebics/settings",
      permission: "tenant_settings:update",
      body: fieldBody("enabled"),
    },
    field: "enabled",
  },
  {
    id: "ebics-signature-key-mode",
    group: "banking",
    pkg: "AE23",
    kind: "enum",
    options: ["external", "server"],
    default: "external",
    questions: ["AE23-05"],
    href: "/bank",
    permission: ACCOUNTING,
    read: { path: "banking/ebics/status", pick: fieldPick("signature_key_mode") },
    write: {
      method: "PUT",
      path: "banking/ebics/settings",
      permission: "tenant_settings:update",
      body: fieldBody("signature_key_mode"),
    },
    field: "signature_key_mode",
  },
  {
    id: "g1-checklist",
    group: "banking",
    pkg: "AE03",
    kind: "link",
    default: null,
    defaultText: true,
    questions: ["M12-09"],
    href: "/einstellungen/buchhaltung/g1-oeffnung",
    permission: ACCOUNTING,
  },
  // --- Plattform ------------------------------------------------------------------------------
  {
    id: "acceptance-register",
    group: "platform",
    pkg: "AE01",
    kind: "link",
    default: null,
    defaultText: true,
    questions: ["V16", "AE01-01"],
    href: "/plattform/abnahme",
    permission: ["acceptance:read"],
  },
  {
    id: "invoice-intake-auto",
    group: "platform",
    pkg: "AF10",
    kind: "boolean",
    default: false,
    questions: ["AF10-01"],
    href: "/dokumente/eingang",
    permission: ["documents:read"],
    read: { path: "document-invoice-intake-auto", pick: fieldPick("enabled") },
    write: {
      method: "PUT",
      path: "document-invoice-intake-auto",
      permission: "tenant_settings:update",
      body: fieldBody("enabled"),
    },
    field: "enabled",
  },
  {
    id: "webhook-auto-disable",
    group: "platform",
    pkg: "AI07",
    kind: "integer",
    range: [0, 100],
    default: 0,
    questions: ["AI07-02"],
    href: "/einstellungen/webhooks",
    permission: ["tenant_settings:read"],
    read: { path: "tenant/webhook-settings", pick: (doc) => (rec(doc).auto_disable_after as number | null) ?? 0 },
    write: {
      method: "PUT",
      path: "tenant/webhook-settings",
      permission: "tenant_settings:update",
      body: (_doc, value) => ({ auto_disable_after: value === 0 || value === null ? null : value }),
      apply: (doc, value) => ({ ...rec(doc), auto_disable_after: value === 0 ? null : value }),
    },
    field: "auto_disable_after",
  },
  {
    id: "objektakte-webhook-timestamp",
    group: "security",
    pkg: "AI07",
    kind: "boolean",
    default: false,
    questions: ["AI07-01"],
    permission: ["tenant_settings:read"],
    read: { path: "tenant/webhook-settings", pick: fieldPick("objektakte_require_timestamp") },
    write: {
      method: "PUT",
      path: "tenant/webhook-settings",
      permission: "tenant_settings:update",
      body: fieldBody("objektakte_require_timestamp"),
    },
    field: "objektakte_require_timestamp",
  },
  {
    id: "insurance-broker-access",
    group: "security",
    pkg: "AG03",
    kind: "boolean",
    default: false,
    questions: ["GAC-07"],
    href: "/einstellungen/benutzer",
    permission: ["tenant_settings:read"],
    read: { path: "tenant/settings", pick: fieldPick("insurance_broker_access") },
    write: {
      method: "PATCH",
      path: "tenant/settings",
      permission: "tenant_settings:update",
      body: fieldBody("insurance_broker_access"),
    },
    field: "insurance_broker_access",
  },
  {
    id: "onboarding-link-threshold",
    group: "platform",
    pkg: "AG03",
    kind: "integer",
    range: [1, 100],
    default: 90,
    questions: ["GAF-11"],
    permission: ["tenant_settings:read"],
    read: { path: "onboarding/match-settings", pick: (doc) => percentOf(doc, "link_threshold") },
    write: {
      method: "PUT",
      path: "onboarding/match-settings",
      permission: "tenant_settings:update",
      body: (doc, value) => matchBody(doc, "link_threshold", value),
      apply: (doc, value) => ({ ...rec(doc), link_threshold: ratio(value) }),
    },
    field: "link_threshold",
  },
  {
    id: "onboarding-suggest-threshold",
    group: "platform",
    pkg: "AG03",
    kind: "integer",
    range: [1, 100],
    default: 60,
    questions: ["GAF-11"],
    permission: ["tenant_settings:read"],
    read: { path: "onboarding/match-settings", pick: (doc) => percentOf(doc, "suggest_threshold") },
    write: {
      method: "PUT",
      path: "onboarding/match-settings",
      permission: "tenant_settings:update",
      body: (doc, value) => matchBody(doc, "suggest_threshold", value),
      apply: (doc, value) => ({ ...rec(doc), suggest_threshold: ratio(value) }),
    },
    field: "suggest_threshold",
  },
];

export const RULE_GROUPS: readonly RuleGroup[] = ["accounting", "billing", "hoa", "portal", "security", "banking", "platform"];

/** Any permission of the rule's list shows it (same reading as the settings index). */
export function visibleRules(permissions: readonly string[]): BusinessRule[] {
  return BUSINESS_RULES.filter((rule) => rule.permission.some((p) => permissions.includes(p)));
}

/** Distinct read paths of the given rules, fetched once each. */
export function readPaths(rules: readonly BusinessRule[]): string[] {
  return [...new Set(rules.flatMap((r) => (r.read ? [r.read.path] : [])))];
}

export type RuleDocs = Record<string, unknown>;

/** Current value of a rule from the fetched documents; `undefined` when the document or the
 *  field could not be read. */
export function currentValue(rule: BusinessRule, docs: RuleDocs): RuleValue | undefined {
  if (!rule.read) return undefined;
  const doc = docs[rule.read.path];
  if (doc === undefined || doc === null) return undefined;
  return rule.read.pick(doc);
}

export function canChange(rule: BusinessRule, permissions: readonly string[]): boolean {
  return rule.write !== undefined && permissions.includes(rule.write.permission);
}

/** Request of a write, or null when the rule has no write endpoint, its document is missing or
 *  the endpoint cannot be addressed (for example no chart version yet). */
export function buildWrite(
  rule: BusinessRule,
  docs: RuleDocs,
  value: RuleValue,
  reason = "",
): { method: "PUT" | "PATCH"; path: string; body: unknown } | null {
  if (!rule.write || !rule.read) return null;
  const doc = docs[rule.read.path];
  if (doc === undefined || doc === null) return null;
  const path = typeof rule.write.path === "function" ? rule.write.path(doc) : rule.write.path;
  if (!path) return null;
  return { method: rule.write.method, path, body: rule.write.body(doc, value, reason) };
}

/** Documents after a successful write of `value` (immutable). */
export function applyWrite(rule: BusinessRule, docs: RuleDocs, value: RuleValue): RuleDocs {
  if (!rule.read || !rule.write) return docs;
  const path = rule.read.path;
  const doc = docs[path];
  const next = rule.write.apply
    ? rule.write.apply(doc, value)
    : rule.field
      ? { ...rec(doc), [rule.field]: value }
      : doc;
  return { ...docs, [path]: next };
}

/** The reason input is needed for this value (always, never or only for some values). */
export function reasonRequired(rule: BusinessRule, value: RuleValue): boolean {
  const need = rule.write?.needsReason;
  return typeof need === "function" ? need(value) : need === true;
}

export function reasonMinLength(rule: BusinessRule): number {
  return rule.write?.reasonMin ?? 3;
}

/** True when the value leaves the conservative default (the page asks for a confirmation). */
export function leavesDefault(rule: BusinessRule, value: RuleValue): boolean {
  return value !== rule.default;
}
