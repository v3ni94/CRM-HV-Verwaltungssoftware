"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type PatternType = "filename_regex" | "text_keyword" | "sender_domain" | "drive_folder";

export type ClassificationRule = {
  id: string;
  name: string;
  pattern_type: PatternType;
  pattern_value: string;
  target_category_id: string | null;
  target_document_type: string | null;
  priority: number;
  active: boolean;
  confidence: number;
};

export type CategoryOption = { id: string; code: string; name: string };

const PATTERN_TYPES: PatternType[] = ["filename_regex", "text_keyword", "sender_domain", "drive_folder"];

const emptyForm = {
  name: "",
  pattern_type: "filename_regex" as PatternType,
  pattern_value: "",
  target_category_id: "",
  target_document_type: "",
  priority: 100,
  confidence: 0.8,
};

/** M35 Stufe 3 part 5: rules settings page (list, create, edit, activate/deactivate) for
 * `objektakte_classification_rule` (the rule stage of the three stage classification,
 * docs/rules/M35-02.md). */
export function RulesSettings({
  initial,
  categories,
}: {
  initial: ClassificationRule[];
  categories: CategoryOption[];
}) {
  const t = useTranslations("Objektakte");
  const [rules, setRules] = useState(initial);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = async () => {
    const res = await bff<ClassificationRule[]>("/api/bff/objektakte/classification-rules");
    if (res.ok) setRules(res.data);
  };

  const resetForm = () => {
    setForm(emptyForm);
    setEditingId(null);
  };

  const edit = (rule: ClassificationRule) => {
    setEditingId(rule.id);
    setForm({
      name: rule.name,
      pattern_type: rule.pattern_type,
      pattern_value: rule.pattern_value,
      target_category_id: rule.target_category_id ?? "",
      target_document_type: rule.target_document_type ?? "",
      priority: rule.priority,
      confidence: rule.confidence,
    });
  };

  const save = async () => {
    if (!form.name.trim() || !form.pattern_value.trim()) {
      setError(t("rules.required"));
      return;
    }
    setBusy(true);
    setError(null);
    const body = JSON.stringify({
      name: form.name,
      pattern_type: form.pattern_type,
      pattern_value: form.pattern_value,
      target_category_id: form.target_category_id || null,
      target_document_type: form.target_document_type || null,
      priority: form.priority,
      confidence: form.confidence,
    });
    const res = editingId
      ? await bff<ClassificationRule>(`/api/bff/objektakte/classification-rules/${editingId}`, {
          method: "PATCH",
          body,
        })
      : await bff<ClassificationRule>("/api/bff/objektakte/classification-rules", {
          method: "POST",
          body,
        });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    resetForm();
    await reload();
  };

  const toggleActive = async (rule: ClassificationRule) => {
    setBusy(true);
    setError(null);
    const res = await bff<ClassificationRule>(`/api/bff/objektakte/classification-rules/${rule.id}`, {
      method: "PATCH",
      body: JSON.stringify({ active: !rule.active }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    await reload();
  };

  const remove = async (id: string) => {
    setBusy(true);
    setError(null);
    const res = await bff<null>(`/api/bff/objektakte/classification-rules/${id}`, { method: "DELETE" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    if (editingId === id) resetForm();
    await reload();
  };

  const categoryName = (id: string | null) => categories.find((c) => c.id === id)?.name ?? "–";

  return (
    <section className={`${ui.card} flex flex-col gap-4`} aria-label={t("rules.title")}>
      <h2 className="text-sm font-semibold">{t("rules.title")}</h2>
      <p className="text-xs text-muted">{t("rules.intro")}</p>

      <ul className="flex flex-col gap-2">
        {rules.length === 0 ? <li className="text-xs text-muted">{t("rules.empty")}</li> : null}
        {rules.map((rule) => (
          <li key={rule.id} className="rounded-md border border-border p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium">{rule.name}</span>
              <span className="text-xs text-muted">
                {t(`rules.patternType.${rule.pattern_type}`)} · {t("rules.priorityLabel")} {rule.priority} ·{" "}
                {categoryName(rule.target_category_id)}
              </span>
            </div>
            <p className="mt-1 font-mono text-xs text-muted">{rule.pattern_value}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" className={ui.buttonSm} onClick={() => edit(rule)} disabled={busy}>
                {t("rules.edit")}
              </button>
              <button type="button" className={ui.buttonSm} onClick={() => void toggleActive(rule)} disabled={busy}>
                {rule.active ? t("rules.deactivate") : t("rules.activate")}
              </button>
              <button type="button" className={ui.buttonSm} onClick={() => void remove(rule.id)} disabled={busy}>
                {t("rules.delete")}
              </button>
            </div>
          </li>
        ))}
      </ul>

      <form
        className="flex flex-col gap-2 border-t border-border pt-3"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <h3 className="text-xs font-semibold">{editingId ? t("rules.editTitle") : t("rules.newTitle")}</h3>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("rules.name")}</span>
          <input
            className={ui.input}
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            maxLength={200}
          />
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <label className="flex flex-1 flex-col gap-1">
            <span className={ui.label}>{t("rules.patternTypeLabel")}</span>
            <select
              className={ui.input}
              value={form.pattern_type}
              onChange={(e) => setForm((f) => ({ ...f, pattern_type: e.target.value as PatternType }))}
            >
              {PATTERN_TYPES.map((p) => (
                <option key={p} value={p}>
                  {t(`rules.patternType.${p}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-1 flex-col gap-1">
            <span className={ui.label}>{t("rules.targetCategory")}</span>
            <select
              className={ui.input}
              value={form.target_category_id}
              onChange={(e) => setForm((f) => ({ ...f, target_category_id: e.target.value }))}
            >
              <option value="">{t("rules.noCategory")}</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("rules.patternValue")}</span>
          <input
            className={`${ui.input} font-mono`}
            value={form.pattern_value}
            onChange={(e) => setForm((f) => ({ ...f, pattern_value: e.target.value }))}
          />
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <label className="flex flex-1 flex-col gap-1">
            <span className={ui.label}>{t("rules.priorityLabel")}</span>
            <input
              type="number"
              className={ui.input}
              value={form.priority}
              onChange={(e) => setForm((f) => ({ ...f, priority: Number(e.target.value) }))}
            />
          </label>
          <label className="flex flex-1 flex-col gap-1">
            <span className={ui.label}>{t("rules.confidence")}</span>
            <input
              type="number"
              step="0.05"
              min="0"
              max="1"
              className={ui.input}
              value={form.confidence}
              onChange={(e) => setForm((f) => ({ ...f, confidence: Number(e.target.value) }))}
            />
          </label>
        </div>
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        <div className={ui.formActions}>
          <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
            {editingId ? t("rules.save") : t("rules.create")}
          </button>
          {editingId ? (
            <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={resetForm} disabled={busy}>
              {t("rules.cancel")}
            </button>
          ) : null}
        </div>
      </form>
    </section>
  );
}
