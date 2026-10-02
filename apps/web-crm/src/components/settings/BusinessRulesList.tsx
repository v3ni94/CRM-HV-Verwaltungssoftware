"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import {
  RULE_GROUPS,
  applyWrite,
  buildWrite,
  canChange,
  currentValue,
  leavesDefault,
  reasonMinLength,
  reasonRequired,
  visibleRules,
  type BusinessRule,
  type RuleDocs,
  type RuleValue,
} from "@/lib/business-rules";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type RowState = {
  draft: RuleValue;
  reason: string;
  confirming: boolean;
  busy: boolean;
  message: string | null;
  error: string | null;
};

function toRaw(rule: BusinessRule, text: string): RuleValue {
  if (rule.kind === "boolean") return text === "true";
  if (rule.kind === "integer") return text === "" ? null : Number(text);
  if (rule.kind === "date") return text === "" ? null : text;
  return text;
}

function toText(value: RuleValue | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

/** Central list of the tenant switches for professionally open decisions (wave 16, AE39). One
 *  row per switch: current value, variants, default, the open question and, where the API has
 *  a PUT endpoint, the change itself. A value that leaves the default needs a confirmation. The
 *  software decides no legal or tax question; nothing here books, sends or deletes. */
export function BusinessRulesList({
  initialDocs,
  permissions,
}: {
  /** Documents of the GET endpoints by path; `null` means the endpoint could not be read. */
  initialDocs: RuleDocs;
  permissions: string[];
}) {
  const t = useTranslations("BusinessRules");
  const tf = useTranslations("AF19");
  const [docs, setDocs] = useState<RuleDocs>(initialDocs);
  const [rows, setRows] = useState<Record<string, RowState>>({});
  const rules = visibleRules(permissions);

  function row(rule: BusinessRule): RowState {
    return (
      rows[rule.id] ?? {
        draft: currentValue(rule, docs) ?? rule.default,
        reason: "",
        confirming: false,
        busy: false,
        message: null,
        error: null,
      }
    );
  }

  function patch(id: string, rule: BusinessRule, change: Partial<RowState>) {
    setRows((prev) => ({ ...prev, [id]: { ...row(rule), ...(prev[id] ?? {}), ...change } }));
  }

  const optionLabel = (rule: BusinessRule, value: string) => t(`options.${rule.optionSet ?? rule.id}.${value}`);

  function valueLabel(rule: BusinessRule, value: RuleValue | undefined): string {
    if (value === undefined) return t("notSet");
    if (rule.kind === "boolean") return value ? t("on") : t("off");
    if (rule.kind === "enum") return typeof value === "string" ? optionLabel(rule, value) : t("notSet");
    if (rule.kind === "date") return typeof value === "string" && value ? formatDate(value) : t("notSet");
    if (rule.kind === "count") return t("entries", { count: Number(value) });
    if (rule.kind === "integer") return value === null ? t("notSet") : String(value);
    return t("notSet");
  }

  function defaultLabel(rule: BusinessRule): string {
    if (rule.defaultText) return t(`rules.${rule.textKey ?? rule.id}.defaultText`);
    return valueLabel(rule, rule.default);
  }

  async function save(rule: BusinessRule) {
    const state = row(rule);
    const request = buildWrite(rule, docs, state.draft, state.reason);
    if (!request) return;
    patch(rule.id, rule, { busy: true, error: null, message: null, confirming: false });
    const res = await bff<unknown>(`/api/bff/${request.path}`, { method: request.method, body: JSON.stringify(request.body) });
    if (!res.ok) {
      patch(rule.id, rule, { busy: false, error: res.message });
      return;
    }
    setDocs((prev) => applyWrite(rule, prev, state.draft));
    patch(rule.id, rule, { busy: false, reason: "", message: t("saved") });
  }

  async function resetRule(rule: BusinessRule) {
    if (!rule.reset || !rule.read) return;
    const doc = docs[rule.read.path];
    const path = typeof rule.reset.path === "function" ? rule.reset.path(doc) : rule.reset.path;
    if (!path || !window.confirm(tf("rules.resetConfirm"))) return;
    patch(rule.id, rule, { busy: true, error: null, message: null });
    const res = await bff<unknown>(`/api/bff/${path}`, { method: "DELETE" });
    if (!res.ok) {
      patch(rule.id, rule, { busy: false, error: res.message });
      return;
    }
    setDocs((prev) => applyWrite(rule, prev, rule.default));
    patch(rule.id, rule, { busy: false, reason: "", draft: rule.default, confirming: false, message: t("saved") });
  }

  function requestSave(rule: BusinessRule) {
    if (leavesDefault(rule, row(rule).draft)) patch(rule.id, rule, { confirming: true, error: null, message: null });
    else void save(rule);
  }

  const openCount = rules.filter((r) => r.questions.length > 0).length;

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <p className="text-sm text-muted" data-testid="rules-summary">
        {t("summary", { count: rules.length, open: openCount })}
      </p>
      <nav aria-label={t("groupsNav")} className="flex flex-wrap gap-2">
        {RULE_GROUPS.filter((g) => rules.some((r) => r.group === g)).map((g) => (
          <a key={g} href={`#group-${g}`} className={ui.buttonSm}>
            {t(`groups.${g}`)}
          </a>
        ))}
      </nav>
      {RULE_GROUPS.map((group) => {
        const inGroup = rules.filter((r) => r.group === group);
        if (inGroup.length === 0) return null;
        return (
          <section key={group} id={`group-${group}`} aria-labelledby={`group-title-${group}`} className="flex min-w-0 flex-col gap-3">
            <h2 id={`group-title-${group}`} className={ui.h2}>
              {t(`groups.${group}`)}
            </h2>
            <ul className="flex min-w-0 flex-col gap-3">
              {inGroup.map((rule) => {
                const state = row(rule);
                const docMissing = rule.read ? docs[rule.read.path] === undefined || docs[rule.read.path] === null : false;
                const current = currentValue(rule, docs);
                const editable = canChange(rule, permissions) && !docMissing;
                const textKey = rule.textKey ?? rule.id;
                const titleId = `rule-title-${rule.id}`;
                return (
                  <li key={rule.id} id={rule.id} aria-labelledby={titleId} className={`${ui.card} flex min-w-0 flex-col gap-3`}>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 id={titleId} className="text-sm font-semibold">
                        {t(`rules.${rule.id}.title`)}
                      </h3>
                      <StatusPill label={t("decisionOpen")} variant="warning" />
                    </div>
                    <p className="text-sm text-muted">{t(`rules.${textKey}.description`)}</p>
                    <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
                      {rule.read ? (
                        <>
                          <dt className="text-subtle">{t("current")}</dt>
                          <dd data-testid={`current-${rule.id}`}>{docMissing ? t("unavailable") : valueLabel(rule, current)}</dd>
                        </>
                      ) : null}
                      <dt className="text-subtle">{t("default")}</dt>
                      <dd data-testid={`default-${rule.id}`}>{defaultLabel(rule)}</dd>
                      {rule.kind === "enum" || rule.kind === "boolean" ? (
                        <>
                          <dt className="text-subtle">{t("variants")}</dt>
                          <dd>
                            {rule.kind === "boolean"
                              ? `${t("on")}, ${t("off")}`
                              : (rule.options ?? []).map((o) => optionLabel(rule, o)).join("; ")}
                          </dd>
                        </>
                      ) : null}
                      <dt className="text-subtle">{rule.questions.length === 1 ? t("questionOne") : t("questionMany")}</dt>
                      <dd>
                        <span className="font-mono">{rule.questions.join(", ")}</span> {t("questionFile")}
                      </dd>
                    </dl>
                    {editable && rule.kind !== "link" && rule.kind !== "count" ? (
                      <div className="flex min-w-0 flex-wrap items-end gap-2">
                        <label className="flex min-w-0 flex-col gap-1 text-sm" htmlFor={`input-${rule.id}`}>
                          <span className={ui.label}>{t("change")}</span>
                          {rule.kind === "enum" || rule.kind === "boolean" ? (
                            <select
                              id={`input-${rule.id}`}
                              className={ui.input}
                              value={toText(state.draft)}
                              disabled={state.busy}
                              onChange={(e) => patch(rule.id, rule, { draft: toRaw(rule, e.target.value), confirming: false })}
                            >
                              {rule.kind === "boolean" ? (
                                <>
                                  <option value="true">{t("on")}</option>
                                  <option value="false">{t("off")}</option>
                                </>
                              ) : (
                                (rule.options ?? []).map((o) => (
                                  <option key={o} value={o}>
                                    {optionLabel(rule, o)}
                                    {o === rule.default ? ` (${t("default")})` : ""}
                                  </option>
                                ))
                              )}
                            </select>
                          ) : (
                            <input
                              id={`input-${rule.id}`}
                              className={ui.input}
                              type={rule.kind === "date" ? "date" : "number"}
                              min={rule.range?.[0]}
                              max={rule.range?.[1]}
                              value={toText(state.draft)}
                              disabled={state.busy}
                              onChange={(e) => patch(rule.id, rule, { draft: toRaw(rule, e.target.value), confirming: false })}
                            />
                          )}
                        </label>
                        {reasonRequired(rule, state.draft) ? (
                          <label className="flex min-w-0 flex-col gap-1 text-sm" htmlFor={`reason-${rule.id}`}>
                            <span className={ui.label}>{t("reason")}</span>
                            <input
                              id={`reason-${rule.id}`}
                              className={ui.input}
                              value={state.reason}
                              maxLength={2000}
                              disabled={state.busy}
                              onChange={(e) => patch(rule.id, rule, { reason: e.target.value })}
                            />
                          </label>
                        ) : null}
                        {rule.reset && permissions.includes(rule.reset.permission) && current !== rule.default ? (
                          <button type="button" className={ui.secondary} disabled={state.busy} onClick={() => void resetRule(rule)}>
                            {tf("rules.reset")}
                          </button>
                        ) : null}
                        {state.confirming ? null : (
                          <button
                            type="button"
                            className={ui.primary}
                            disabled={state.busy || state.draft === current || (reasonRequired(rule, state.draft) && state.reason.trim().length < reasonMinLength(rule))}
                            onClick={() => requestSave(rule)}
                          >
                            {t("save")}
                          </button>
                        )}
                      </div>
                    ) : rule.write && !docMissing ? (
                      <p className={ui.help}>{t("noPermission")}</p>
                    ) : rule.read && !rule.write ? (
                      <p className={ui.help}>{t("readOnly")}</p>
                    ) : null}
                    {state.confirming ? (
                      <div role="alertdialog" aria-label={t("confirmLabel")} className={ui.notice}>
                        <p>{t("confirm")}</p>
                        <div className={`mt-2 ${ui.formActions}`}>
                          <button type="button" className={ui.primary} disabled={state.busy} onClick={() => void save(rule)}>
                            {t("confirmYes")}
                          </button>
                          <button type="button" className={ui.secondary} onClick={() => patch(rule.id, rule, { confirming: false })}>
                            {t("cancel")}
                          </button>
                        </div>
                      </div>
                    ) : null}
                    {state.error ? (
                      <p role="alert" className={ui.alert}>
                        {state.error}
                      </p>
                    ) : null}
                    {state.message ? (
                      <p role="status" className="text-sm text-muted">
                        {state.message}
                      </p>
                    ) : null}
                    {rule.href ? (
                      <Link href={rule.href} className="text-sm underline hover:text-fg">
                        {t("openMask")}
                      </Link>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
