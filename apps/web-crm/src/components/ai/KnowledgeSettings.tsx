"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import type { KnowledgeEntry } from "@/lib/ai";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const KINDS = ["filing_rule", "workflow", "correction", "fact"] as const;
type Kind = (typeof KINDS)[number];

type PropertyOption = { id: string; number: string; name: string };

const emptyForm = { propertyId: "", kind: "fact" as Kind, title: "", content: "" };

/** Wissensbasis je Mandant und Objekt (Welle 3 Punkt 14, M33): Ablageregeln, Arbeitsabläufe,
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
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const propertyName = useMemo(() => {
    const byId = new Map(properties.map((p) => [p.id, `${p.number} ${p.name}`]));
    return (id: string | null) => (id ? byId.get(id) ?? id : t("knowledge.global"));
  }, [properties, t]);

  const reload = async () => {
    const params = new URLSearchParams();
    if (filterProperty) params.set("property_id", filterProperty);
    if (filterKind) params.set("kind", filterKind);
    const res = await bff<KnowledgeEntry[]>(`/api/bff/ai/knowledge?${params.toString()}`);
    if (res.ok) setEntries(res.data);
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterProperty, filterKind]);

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
      </div>

      <ul className="flex flex-col gap-2">
        {entries.length === 0 ? <li className="text-xs text-muted">{t("knowledge.empty")}</li> : null}
        {entries.map((entry) => (
          <li key={entry.id} className="rounded-md border border-border p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium">{entry.title}</span>
              <span className="text-xs text-muted">
                {t(`knowledge.kind.${entry.kind}`)} · {propertyName(entry.property_id)}
                {entry.source === "learned" ? ` · ${t("knowledge.learned")}` : ""}
              </span>
            </div>
            <p className="mt-1 whitespace-pre-wrap text-sm text-muted">{entry.content}</p>
            <div className="mt-2 flex gap-2">
              <button type="button" className={ui.buttonSm} onClick={() => edit(entry)} disabled={busy}>
                {t("knowledge.edit")}
              </button>
              <button type="button" className={ui.buttonSm} onClick={() => void remove(entry.id)} disabled={busy}>
                {t("knowledge.delete")}
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
