"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import type { KnowledgeEntry, KnowledgeStatus } from "@/lib/ai";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const KINDS = ["filing_rule", "workflow", "correction", "fact"] as const;
type Kind = (typeof KINDS)[number];
const STATUSES = ["draft", "in_review", "approved", "withdrawn"] as const;

type PropertyOption = { id: string; number: string; name: string };

const emptyForm = {
  propertyId: "",
  kind: "fact" as Kind,
  title: "",
  content: "",
  validFrom: "",
  validUntil: "",
};

/** Naive line diff (added/removed only, no move detection): good enough to show what changed
 * between two versions of a knowledge entry's content without a diff library dependency. */
function lineDiff(before: string, after: string): { text: string; kind: "same" | "add" | "del" }[] {
  const a = before.split("\n");
  const b = after.split("\n");
  const rows: { text: string; kind: "same" | "add" | "del" }[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    const lineA = a[i];
    const lineB = b[j];
    if (lineA !== undefined && lineB !== undefined && lineA === lineB) {
      rows.push({ text: lineA, kind: "same" });
      i += 1;
      j += 1;
    } else if (lineB !== undefined && !a.slice(i).includes(lineB)) {
      rows.push({ text: lineB, kind: "add" });
      j += 1;
    } else if (lineA !== undefined) {
      rows.push({ text: lineA, kind: "del" });
      i += 1;
    } else if (lineB !== undefined) {
      rows.push({ text: lineB, kind: "add" });
      j += 1;
    }
  }
  return rows;
}

/** Wissensbasis je Mandant und Objekt (Welle 3 Punkt 14, M34): Ablageregeln, Arbeitsabläufe,
 * Korrekturen und Fakten, die als Kontext in KI-Läufe (Chat, Mail-Vorbereitung) einfließen.
 * Nur Vorschlagskontext, nie automatisch geschrieben (Regel 0.1.6). */
export function KnowledgeSettings({
  initial,
  properties,
}: {
  initial: KnowledgeEntry[];
  properties: PropertyOption[];
}) {
  const t = useTranslations("AiSettings");
  const [entries, setEntries] = useState(initial);
  const [filterProperty, setFilterProperty] = useState("");
  const [filterKind, setFilterKind] = useState<Kind | "">("");
  const [filterStatus, setFilterStatus] = useState<KnowledgeStatus | "">("");
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [historyFor, setHistoryFor] = useState<string | null>(null);
  const [history, setHistory] = useState<KnowledgeEntry[]>([]);
  const [diffAgainst, setDiffAgainst] = useState<string | null>(null);

  const propertyName = useMemo(() => {
    const byId = new Map(properties.map((p) => [p.id, `${p.number} ${p.name}`]));
    return (id: string | null) => (id ? byId.get(id) ?? id : t("knowledge.global"));
  }, [properties, t]);

  const reload = async () => {
    const params = new URLSearchParams();
    if (filterProperty) params.set("property_id", filterProperty);
    if (filterKind) params.set("kind", filterKind);
    if (filterStatus) params.set("status", filterStatus);
    const res = await bff<KnowledgeEntry[]>(`/api/bff/ai/knowledge?${params.toString()}`);
    if (res.ok) setEntries(res.data);
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterProperty, filterKind, filterStatus]);

  const resetForm = () => {
    setForm(emptyForm);
    setEditingId(null);
  };

  const edit = (entry: KnowledgeEntry) => {
    setEditingId(entry.id);
    setForm({
      propertyId: entry.property_id ?? "",
      kind: entry.kind as Kind,
      title: entry.title,
      content: entry.content,
      validFrom: entry.valid_from ?? "",
      validUntil: entry.valid_until ?? "",
    });
  };

  const save = async () => {
    if (!form.title.trim() || !form.content.trim()) {
      setError(t("knowledge.required"));
      return;
    }
    setBusy(true);
    setError(null);
    const body = JSON.stringify({
      property_id: form.propertyId || null,
      kind: form.kind,
      title: form.title,
      content: form.content,
      valid_from: form.validFrom || null,
      valid_until: form.validUntil || null,
    });
    const res = editingId
      ? await bff<KnowledgeEntry>(`/api/bff/ai/knowledge/${editingId}`, { method: "PUT", body })
      : await bff<KnowledgeEntry>("/api/bff/ai/knowledge", { method: "POST", body });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    resetForm();
    await reload();
  };

  const remove = async (id: string) => {
    setBusy(true);
    setError(null);
    const res = await bff<null>(`/api/bff/ai/knowledge/${id}`, { method: "DELETE" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    if (editingId === id) resetForm();
    await reload();
  };

  const transition = async (
    id: string,
    action: "submit" | "approve" | "withdraw" | "reject",
    body?: Record<string, unknown>,
  ) => {
    setBusy(true);
    setError(null);
    const res = await bff<KnowledgeEntry>(`/api/bff/ai/knowledge/${id}/${action}`, {
      method: "POST",
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    await reload();
    if (historyFor) await loadHistory(historyFor);
  };

  const reject = async (id: string) => {
    const reason = window.prompt(t("knowledge.rejectReasonPrompt"));
    if (reason === null) return;
    if (!reason.trim()) {
      setError(t("knowledge.rejectReasonRequired"));
      return;
    }
    await transition(id, "reject", { reason: reason.trim() });
  };

  const loadHistory = async (id: string) => {
    const res = await bff<KnowledgeEntry[]>(`/api/bff/ai/knowledge/${id}/versions`);
    if (res.ok) setHistory(res.data);
  };

  const toggleHistory = async (id: string) => {
    if (historyFor === id) {
      setHistoryFor(null);
      setHistory([]);
      setDiffAgainst(null);
      return;
    }
    setHistoryFor(id);
    setDiffAgainst(null);
    await loadHistory(id);
  };

  return (
    <section className={`${ui.card} flex flex-col gap-4`} aria-label={t("knowledge.title")}>
      <h2 className="text-sm font-semibold">{t("knowledge.title")}</h2>
      <p className="text-xs text-muted">{t("knowledge.intro")}</p>

      <div className="flex flex-col gap-2 sm:flex-row">
        <label className="flex flex-1 flex-col gap-1">
          <span className={ui.label}>{t("knowledge.filterProperty")}</span>
          <select className={ui.input} value={filterProperty} onChange={(e) => setFilterProperty(e.target.value)}>
            <option value="">{t("knowledge.allProperties")}</option>
            {properties.map((p) => (
              <option key={p.id} value={p.id}>
                {p.number} {p.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-1 flex-col gap-1">
          <span className={ui.label}>{t("knowledge.filterKind")}</span>
          <select className={ui.input} value={filterKind} onChange={(e) => setFilterKind(e.target.value as Kind | "")}>
            <option value="">{t("knowledge.allKinds")}</option>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`knowledge.kind.${k}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-1 flex-col gap-1">
          <span className={ui.label}>{t("knowledge.filterStatus")}</span>
          <select
            className={ui.input}
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as KnowledgeStatus | "")}
          >
            <option value="">{t("knowledge.allStatuses")}</option>
            {STATUSES.map((st) => (
              <option key={st} value={st}>
                {t(`knowledge.status.${st}`)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <ul className="flex flex-col gap-2">
        {entries.length === 0 ? <li className="text-xs text-muted">{t("knowledge.empty")}</li> : null}
        {entries.map((entry) => (
          <li key={entry.id} className="rounded-md border border-border p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium">{entry.title}</span>
              <span className="text-xs text-muted">
                {t(`knowledge.kind.${entry.kind}`)} · {propertyName(entry.property_id)} ·{" "}
                {t(`knowledge.status.${entry.status}`)} · {t("knowledge.version", { version: entry.version ?? 1 })}
                {entry.source === "learned" ? ` · ${t("knowledge.learned")}` : ""}
              </span>
            </div>
            <p className="mt-1 whitespace-pre-wrap text-sm text-muted">{entry.content}</p>
            {entry.status === "draft" && entry.rejection_reason ? (
              <p className="mt-1 text-xs text-red-600">
                {t("knowledge.rejectedHint", { reason: entry.rejection_reason })}
              </p>
            ) : null}
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" className={ui.buttonSm} onClick={() => edit(entry)} disabled={busy}>
                {t("knowledge.edit")}
              </button>
              {entry.status === "draft" ? (
                <button
                  type="button"
                  className={ui.buttonSm}
                  onClick={() => void transition(entry.id, "submit")}
                  disabled={busy}
                >
                  {t("knowledge.submit")}
                </button>
              ) : null}
              {entry.status === "in_review" ? (
                <button
                  type="button"
                  className={ui.buttonSm}
                  onClick={() => void transition(entry.id, "approve")}
                  disabled={busy}
                  title={t("knowledge.fourEyesHint")}
                >
                  {t("knowledge.approve")}
                </button>
              ) : null}
              {entry.status === "in_review" ? (
                <button
                  type="button"
                  className={ui.buttonSm}
                  onClick={() => void reject(entry.id)}
                  disabled={busy}
                  title={t("knowledge.fourEyesHint")}
                >
                  {t("knowledge.reject")}
                </button>
              ) : null}
              {entry.status === "in_review" || entry.status === "approved" ? (
                <button
                  type="button"
                  className={ui.buttonSm}
                  onClick={() => void transition(entry.id, "withdraw")}
                  disabled={busy}
                >
                  {t("knowledge.withdraw")}
                </button>
              ) : null}
              <button type="button" className={ui.buttonSm} onClick={() => void toggleHistory(entry.id)} disabled={busy}>
                {historyFor === entry.id ? t("knowledge.historyHide") : t("knowledge.history")}
              </button>
              <button type="button" className={ui.buttonSm} onClick={() => void remove(entry.id)} disabled={busy}>
                {t("knowledge.delete")}
              </button>
            </div>
            {historyFor === entry.id ? (
              <div className="mt-3 flex flex-col gap-2 border-t border-border pt-2">
                <h4 className="text-xs font-semibold">{t("knowledge.history")}</h4>
                {history.length <= 1 ? <p className="text-xs text-muted">{t("knowledge.noHistory")}</p> : null}
                <ul className="flex flex-col gap-1">
                  {history.map((v) => (
                    <li key={v.id} className="flex flex-wrap items-center gap-2 text-xs">
                      <span>
                        {t("knowledge.version", { version: v.version ?? 1 })} · {t(`knowledge.status.${v.status}`)}
                        {v.superseded_at ? ` · ${t("knowledge.supersededOn", { date: v.superseded_at.slice(0, 10) })}` : ""}
                      </span>
                      <button
                        type="button"
                        className={ui.buttonSm}
                        onClick={() => setDiffAgainst(diffAgainst === v.id ? null : v.id)}
                      >
                        Diff
                      </button>
                    </li>
                  ))}
                </ul>
                {diffAgainst
                  ? (() => {
                      const other = history.find((v) => v.id === diffAgainst);
                      const current = history.find((v) => v.id === historyFor) ?? entry;
                      if (!other) return null;
                      return (
                        <div className="rounded-md bg-surface-muted p-2 font-mono text-xs">
                          <p className="mb-1 text-muted">
                            {t("knowledge.diffWith", { version: other.version ?? 1 })}
                          </p>
                          {lineDiff(other.content, current.content).map((row, idx) => (
                            <div
                              key={idx}
                              className={
                                row.kind === "add"
                                  ? "bg-emerald-500/10 text-emerald-700"
                                  : row.kind === "del"
                                    ? "bg-red-500/10 text-red-700 line-through"
                                    : ""
                              }
                            >
                              {row.kind === "add" ? "+ " : row.kind === "del" ? "- " : "  "}
                              {row.text}
                            </div>
                          ))}
                        </div>
                      );
                    })()
                  : null}
              </div>
            ) : null}
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
        <h3 className="text-xs font-semibold">{editingId ? t("knowledge.editTitle") : t("knowledge.newTitle")}</h3>
        <div className="flex flex-col gap-2 sm:flex-row">
          <label className="flex flex-1 flex-col gap-1">
            <span className={ui.label}>{t("knowledge.property")}</span>
            <select
              className={ui.input}
              value={form.propertyId}
              onChange={(e) => setForm((f) => ({ ...f, propertyId: e.target.value }))}
            >
              <option value="">{t("knowledge.global")}</option>
              {properties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.number} {p.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-1 flex-col gap-1">
            <span className={ui.label}>{t("knowledge.kindLabel")}</span>
            <select className={ui.input} value={form.kind} onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value as Kind }))}>
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {t(`knowledge.kind.${k}`)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("knowledge.titleLabel")}</span>
          <input className={ui.input} value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} maxLength={200} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("knowledge.contentLabel")}</span>
          <textarea
            className={`${ui.input} min-h-24`}
            value={form.content}
            onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
          />
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <label className="flex flex-1 flex-col gap-1">
            <span className={ui.label}>{t("knowledge.validFrom")}</span>
            <input
              type="date"
              className={ui.input}
              value={form.validFrom}
              onChange={(e) => setForm((f) => ({ ...f, validFrom: e.target.value }))}
            />
          </label>
          <label className="flex flex-1 flex-col gap-1">
            <span className={ui.label}>{t("knowledge.validUntil")}</span>
            <input
              type="date"
              className={ui.input}
              value={form.validUntil}
              onChange={(e) => setForm((f) => ({ ...f, validUntil: e.target.value }))}
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
            {editingId ? t("knowledge.save") : t("knowledge.create")}
          </button>
          {editingId ? (
            <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={resetForm} disabled={busy}>
              {t("knowledge.cancel")}
            </button>
          ) : null}
        </div>
      </form>
    </section>
  );
}
