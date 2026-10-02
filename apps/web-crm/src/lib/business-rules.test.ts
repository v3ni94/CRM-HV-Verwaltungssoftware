import { readFileSync } from "node:fs";
import path from "node:path";

import de from "../../messages/de.json";
import en from "../../messages/en.json";

import {
  BUSINESS_RULES,
  RULE_GROUPS,
  applyWrite,
  buildWrite,
  canChange,
  currentValue,
  leavesDefault,
  readPaths,
  reasonMinLength,
  reasonRequired,
  visibleRules,
  type BusinessRule,
} from "./business-rules";
import { settingsSearchIndex } from "./settings-index";

const REPO = path.resolve(import.meta.dirname, "..", "..", "..", "..");
const QUESTIONS = readFileSync(path.join(REPO, "docs", "OPEN_QUESTIONS.md"), "utf-8");

type Catalogue = { BusinessRules: { rules: Record<string, Record<string, string>>; options: Record<string, Record<string, string>>; groups: Record<string, string> } };

function text(cat: Catalogue, rule: BusinessRule, key: "title" | "description" | "defaultText"): string | undefined {
  const textKey = key === "title" ? rule.id : (rule.textKey ?? rule.id);
  return cat.BusinessRules.rules[textKey]?.[key];
}

describe("business rule registry", () => {
  it("has unique ids and at least one open question per rule that exists in OPEN_QUESTIONS.md", () => {
    const ids = BUSINESS_RULES.map((r) => r.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const rule of BUSINESS_RULES) {
      expect(rule.questions.length, rule.id).toBeGreaterThan(0);
      for (const q of rule.questions) {
        expect(QUESTIONS.includes(`| ${q} |`), `${rule.id}: question ${q} is not in docs/OPEN_QUESTIONS.md`).toBe(true);
      }
    }
  });

  it("covers every switch of the wave 16 packages named in the brief", () => {
    const packages = new Set(BUSINESS_RULES.map((r) => r.pkg));
    for (const pkg of ["AE01", "AE02", "AE03", "AE04", "AE05", "AE06", "AE07", "AE08", "AE09", "AE10", "AE12", "AE13", "AE15", "AE16", "AE17", "AE18", "AE19", "AE20", "AE22", "AE23", "AE27", "AE28", "AE29", "AE30", "AE31", "AE33", "AE34"]) {
      expect(packages.has(pkg), pkg).toBe(true);
    }
  });

  it("has titles, descriptions and option labels in German and English, without dashes in German", () => {
    for (const [lang, cat] of [["de", de], ["en", en]] as const) {
      for (const rule of BUSINESS_RULES) {
        expect(text(cat as unknown as Catalogue, rule, "title"), `${lang} ${rule.id} title`).toBeTruthy();
        expect(text(cat as unknown as Catalogue, rule, "description"), `${lang} ${rule.id} description`).toBeTruthy();
        if (rule.defaultText) expect(text(cat as unknown as Catalogue, rule, "defaultText"), `${lang} ${rule.id} defaultText`).toBeTruthy();
        for (const option of rule.options ?? []) {
          const label = (cat as unknown as Catalogue).BusinessRules.options[rule.optionSet ?? rule.id]?.[option];
          expect(label, `${lang} ${rule.id} option ${option}`).toBeTruthy();
        }
      }
      for (const group of RULE_GROUPS) expect((cat as unknown as Catalogue).BusinessRules.groups[group], `${lang} ${group}`).toBeTruthy();
    }
    expect(JSON.stringify(de.BusinessRules)).not.toMatch(/[–—]| - /);
  });

  it("keeps the conservative default inside the variants and flags every kind consistently", () => {
    for (const rule of BUSINESS_RULES) {
      if (rule.kind === "enum") {
        expect(rule.options?.length, rule.id).toBeGreaterThan(1);
        expect(rule.options, rule.id).toContain(rule.default);
      }
      if (rule.kind === "boolean") expect(typeof rule.default, rule.id).toBe("boolean");
      if (rule.kind === "integer") expect(rule.range, rule.id).toBeDefined();
      if (rule.kind === "link" || rule.kind === "count") expect(rule.defaultText, rule.id).toBe(true);
      if (rule.write) {
        expect(rule.read, `${rule.id} needs a GET to build the body`).toBeDefined();
        expect(rule.permission.length).toBeGreaterThan(0);
      }
    }
  });

  it("starts every switch with the conservative variant of the API", () => {
    const defaults = Object.fromEntries(BUSINESS_RULES.map((r) => [r.id, r.default]));
    expect(defaults).toMatchObject({
      "rent-invoice-numbering": "draft_numbers",
      "subledger-exclude-written-off": true,
      "period-lock-mode": "ledger_only",
      "period-lock-auto": false,
      "period-lock-reopen": false,
      "advance-open-mode": "info_only",
      "allocation-basis-block": true,
      "deadline-policy": "block_claims",
      "deadline-watch": false,
      "opening-lock-mode": "locked",
      "reserve-payment-mode": "bound_only",
      "correction-report": false,
      "plan-change-mode": "notice",
      "acquisition-purchase": "manual_release",
      "virtual-meetings": false,
      "online-meeting": false,
      "owner-rental-income": false,
      "terms-version-mode": "manual",
      "automation-switch": false,
      "credit-payable-mode": "off",
      "ebics-enabled": false,
      "ebics-signature-key-mode": "external",
      "mfa-crm-mode": "voluntary",
      "portal-chat-bot": false,
      "access-export-third-party": "none",
      "access-export-internal-notes": false,
      "text-block-second-person": true,
      "document-trash-enabled": false,
      "document-trash-days": 30,
      "legal-basis-email-delivery": "consent",
      "legal-basis-marketing": "consent",
    });
  });

  it("is reachable from the settings search with the permission of the rule", () => {
    const page = settingsSearchIndex.find((e) => e.id === "fachliche-regeln");
    expect(page?.href).toBe("/einstellungen/fachliche-regeln");
    for (const rule of BUSINESS_RULES) {
      if (rule.id.startsWith("acquisition-") && rule.id !== "acquisition-purchase") continue;
      if (rule.href?.startsWith("/plattform")) continue;
      const entry = settingsSearchIndex.find((e) => e.id === `fachliche-regeln-${rule.id}`);
      expect(entry, rule.id).toBeDefined();
      expect(entry?.href).toBe(`/einstellungen/fachliche-regeln#${rule.id}`);
      expect(entry?.permission).toEqual([...rule.permission]);
    }
  });
});

describe("business rule helpers", () => {
  const settings = { lock_mode: "object_period", auto_lock_on_close: false, reopen_enabled: true };

  it("shows a rule when any of its permissions is present and lists each GET once", () => {
    const only = visibleRules(["tenant_settings:read"]);
    expect(only.map((r) => r.id)).toContain("opening-lock-mode");
    expect(only.map((r) => r.id)).not.toContain("period-lock-mode");
    expect(visibleRules([])).toEqual([]);
    const paths = readPaths(visibleRules(["accounting:read", "tenant_settings:read", "tickets:read", "contracts:read"]));
    expect(new Set(paths).size).toBe(paths.length);
    expect(paths.filter((p) => p === "billing/deadline-settings")).toHaveLength(1);
  });

  it("reads the current value from the shared document", () => {
    const rule = BUSINESS_RULES.find((r) => r.id === "period-lock-mode")!;
    expect(currentValue(rule, { "accounting/period-locks/settings": settings })).toBe("object_period");
    expect(currentValue(rule, { "accounting/period-locks/settings": null })).toBeUndefined();
    expect(currentValue(rule, {})).toBeUndefined();
  });

  it("builds a partial body for the period lock and applies it to the document", () => {
    const rule = BUSINESS_RULES.find((r) => r.id === "period-lock-reopen")!;
    const docs = { "accounting/period-locks/settings": settings };
    expect(buildWrite(rule, docs, false)).toEqual({ method: "PUT", path: "accounting/period-locks/settings", body: { reopen_enabled: false } });
    expect(applyWrite(rule, docs, false)["accounting/period-locks/settings"]).toEqual({ ...settings, reopen_enabled: false });
    expect(buildWrite(rule, {}, false)).toBeNull();
  });

  it("sends the whole tax document back with the one field changed", () => {
    const rule = BUSINESS_RULES.find((r) => r.id === "subledger-exclude-written-off")!;
    const doc = {
      input_tax_enabled: true,
      input_tax_account_number: "140000",
      construction_withholding_enabled: false,
      construction_withholding_percent: "15.00",
      section_35a_enabled: true,
      approval_limits_enabled: true,
      approval_limits: [{ role_code: "accountant", limit_amount: "500.00", extra: "dropped" }],
      subledger_exclude_written_off: true,
    };
    const req = buildWrite(rule, { "accounting/tax/settings": doc }, false)!;
    expect(req.body).toEqual({
      input_tax_enabled: true,
      input_tax_account_number: "140000",
      construction_withholding_enabled: false,
      construction_withholding_percent: "15.00",
      section_35a_enabled: true,
      approval_limits_enabled: true,
      approval_limits: [{ role_code: "accountant", limit_amount: "500.00" }],
      subledger_exclude_written_off: false,
    });
  });

  it("keeps the other meeting fields when one switch changes and may clear the transition date", () => {
    const doc = {
      invitation_weeks: 3,
      virtual_meetings_enabled: true,
      virtual_basis_term_lock_enabled: false,
      virtual_basis_transition_date: "2026-12-01",
    };
    const lock = BUSINESS_RULES.find((r) => r.id === "virtual-basis-term-lock")!;
    expect(buildWrite(lock, { "hoa/meeting-settings": doc }, true)!.body).toEqual({ ...doc, virtual_basis_term_lock_enabled: true });
    const date = BUSINESS_RULES.find((r) => r.id === "virtual-basis-transition-date")!;
    expect(buildWrite(date, { "hoa/meeting-settings": doc }, null)!.body).toEqual({ ...doc, virtual_basis_transition_date: null });
  });

  it("keeps the proxy mode when the online switch changes", () => {
    const rule = BUSINESS_RULES.find((r) => r.id === "online-meeting")!;
    const doc = { enabled: false, proxy_conflict_mode: "first_vote" };
    expect(buildWrite(rule, { "hoa/online-meeting-settings": doc }, true)!.body).toEqual({ enabled: true, proxy_conflict_mode: "first_vote" });
  });

  it("addresses each acquisition kind and keeps its source note", () => {
    const rule = BUSINESS_RULES.find((r) => r.id === "acquisition-inheritance")!;
    const doc = {
      items: [
        { acquisition_kind: "purchase", variant: "manual_release", source_note: null },
        { acquisition_kind: "inheritance", variant: "manual_release", source_note: "Gutachten 2026" },
      ],
    };
    const docs = { "hoa/acquisition-rules": doc };
    expect(currentValue(rule, docs)).toBe("manual_release");
    expect(buildWrite(rule, docs, "by_due_date")).toEqual({
      method: "PUT",
      path: "hoa/acquisition-rules/inheritance",
      body: { variant: "by_due_date", source_note: "Gutachten 2026" },
    });
    const next = applyWrite(rule, docs, "by_due_date");
    expect(currentValue(rule, next)).toBe("by_due_date");
    expect(currentValue(BUSINESS_RULES.find((r) => r.id === "acquisition-purchase")!, next)).toBe("manual_release");
  });

  it("reads and changes the four eyes switch of the newest chart version with a reason", () => {
    const rule = BUSINESS_RULES.find((r) => r.id === "chart-four-eyes")!;
    const docs = {
      "accounting/templates": [
        { id: "11111111-1111-1111-1111-111111111111", version: 1, four_eyes_required: true },
        { id: "22222222-2222-2222-2222-222222222222", version: 2, four_eyes_required: false },
      ],
    };
    expect(currentValue(rule, docs)).toBe(false);
    expect(currentValue(rule, { "accounting/templates": [{ version: 1, four_eyes_required: null }] })).toBe(true);
    expect(currentValue(rule, { "accounting/templates": [] })).toBeUndefined();
    expect(canChange(rule, ["accounting:approve"])).toBe(true);
    expect(rule.write?.needsReason).toBe(true);
    expect(buildWrite(rule, docs, true, "  Prüfung durch Steuerberater  ")).toEqual({
      method: "PUT",
      path: "accounting/templates/22222222-2222-2222-2222-222222222222/four-eyes",
      body: { required: true, reason: "Prüfung durch Steuerberater" },
    });
    const next = applyWrite(rule, docs, true);
    expect(currentValue(rule, next)).toBe(true);
    expect((next["accounting/templates"] as { four_eyes_required: boolean }[])[0]!.four_eyes_required).toBe(true);
    // no chart version yet: nothing to address
    expect(buildWrite(rule, { "accounting/templates": [] }, true, "Begründung")).toBeNull();
  });

  it("offers per purpose only the bases of the API and asks for a justification beside consent", () => {
    const marketing = BUSINESS_RULES.find((r) => r.id === "legal-basis-marketing")!;
    expect(marketing.options).toEqual(["consent", "legitimate_interest"]);
    expect(BUSINESS_RULES.find((r) => r.id === "legal-basis-portal-terms")!.options).toEqual(["consent", "contract"]);
    expect(reasonRequired(marketing, "consent")).toBe(false);
    expect(reasonRequired(marketing, "legitimate_interest")).toBe(true);
    expect(reasonMinLength(marketing)).toBe(10);
    const docs = {
      "consent-legal-basis": {
        items: [
          { purpose: "email_delivery", basis: "consent", note: null },
          { purpose: "marketing", basis: "consent", note: null },
        ],
      },
    };
    expect(currentValue(marketing, docs)).toBe("consent");
    expect(buildWrite(marketing, docs, "legitimate_interest", " Abwägung dokumentiert am 01.10.2026 ")).toEqual({
      method: "PUT",
      path: "consent-legal-basis/marketing",
      body: { basis: "legitimate_interest", note: "Abwägung dokumentiert am 01.10.2026" },
    });
    expect(buildWrite(marketing, docs, "consent", "")!.body).toEqual({ basis: "consent", note: null });
    const next = applyWrite(marketing, docs, "legitimate_interest");
    expect(currentValue(marketing, next)).toBe("legitimate_interest");
    expect(currentValue(BUSINESS_RULES.find((r) => r.id === "legal-basis-email-delivery")!, next)).toBe("consent");
  });

  it("counts the checkpoints and keeps the booking automation display only", () => {
    expect(currentValue(BUSINESS_RULES.find((r) => r.id === "rule-checkpoints")!, { "accounting/rule-versions/checkpoints": [{}, {}] })).toBe(2);
    const automation = BUSINESS_RULES.find((r) => r.id === "automation-switch")!;
    expect(automation.write).toBeUndefined();
    expect(canChange(automation, ["accounting:approve", "tenant_settings:update"])).toBe(false);
  });

  it("asks for confirmation only when a value leaves the default", () => {
    const rule = BUSINESS_RULES.find((r) => r.id === "plan-change-mode")!;
    expect(leavesDefault(rule, "notice")).toBe(false);
    expect(leavesDefault(rule, "due_now")).toBe(true);
    expect(canChange(rule, ["tenant_settings:read"])).toBe(false);
    expect(canChange(rule, ["tenant_settings:update"])).toBe(true);
  });
});
