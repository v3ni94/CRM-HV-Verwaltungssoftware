"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type TreeCategory = {
  id: string;
  code: string;
  name: string;
  parent_id: string | null;
  paperless_document_type: string | null;
  paperless_tag: string | null;
  drive_folder: string | null;
  sort_order: number;
};

export type CategoryNode = TreeCategory & { children: CategoryNode[]; depth: number };

/** Flat list to tree (6.7, M6-09); unknown parents become roots so nothing is hidden. */
export function buildTree(items: TreeCategory[]): CategoryNode[] {
  const byId = new Map<string, CategoryNode>();
  for (const c of items) byId.set(c.id, { ...c, children: [], depth: 0 });
  const roots: CategoryNode[] = [];
  for (const node of byId.values()) {
    const parent = node.parent_id ? byId.get(node.parent_id) : undefined;
    if (parent && parent.id !== node.id) parent.children.push(node);
    else roots.push(node);
  }
  const order = (a: CategoryNode, b: CategoryNode) => a.sort_order - b.sort_order || a.name.localeCompare(b.name, "de");
  const walk = (nodes: CategoryNode[], depth: number, seen: Set<string>) => {
    nodes.sort(order);
    for (const n of nodes) {
      n.depth = depth;
      if (seen.has(n.id)) {
        n.children = [];
        continue;
      }
      seen.add(n.id);
      walk(n.children, depth + 1, seen);
    }
  };
  walk(roots, 0, new Set());
  return roots;
}

function flatten(nodes: CategoryNode[]): CategoryNode[] {
  return nodes.flatMap((n) => [n, ...flatten(n.children)]);
}

type Draft = { paperless_document_type: string; paperless_tag: string; drive_folder: string };

/** Category tree with the mapping to Paperless document type and tag and the Drive folder
 *  (6.7, M6-09). A changed mapping is pushed to existing mirrors by the API. */
export function CategoryTree({ categories: initial }: { categories: TreeCategory[] }) {
  const t = useTranslations("CategoryTree");
  const [categories, setCategories] = useState(initial);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>({ paperless_document_type: "", paperless_tag: "", drive_folder: "" });
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [newCat, setNewCat] = useState({ code: "", name: "", parent_id: "" });
  const rows = flatten(buildTree(categories));

  function edit(c: CategoryNode) {
    setEditing(c.id);
    setDraft({
      paperless_document_type: c.paperless_document_type ?? "",
      paperless_tag: c.paperless_tag ?? "",
      drive_folder: c.drive_folder ?? "",
    });
  }

  async function save(id: string) {
    const body = {
      paperless_document_type: draft.paperless_document_type.trim() || null,
      paperless_tag: draft.paperless_tag.trim() || null,
      drive_folder: draft.drive_folder.trim() || null,
    };
    const res = await bff<TreeCategory>(`/api/bff/document-categories/${id}`, { method: "PATCH", body: JSON.stringify(body) });
    if (res.ok) {
      setCategories((all) => all.map((c) => (c.id === id ? { ...c, ...res.data } : c)));
      setEditing(null);
      setMessage({ ok: true, text: t("saved") });
    } else setMessage({ ok: false, text: res.message });
  }

  async function create(e: FormEvent) {
    e.preventDefault();
    const body = { code: newCat.code.trim(), name: newCat.name.trim(), parent_id: newCat.parent_id || null };
    const res = await bff<TreeCategory>("/api/bff/document-categories", { method: "POST", body: JSON.stringify(body) });
    if (res.ok) {
      setCategories((all) => [...all, res.data]);
      setNewCat({ code: "", name: "", parent_id: "" });
      setMessage({ ok: true, text: t("created") });
    } else setMessage({ ok: false, text: res.message });
  }

  return (
    <div className="flex flex-col gap-4">
      {message ? (
        <p role="status" className={message.ok ? ui.success : ui.alert}>
          {message.text}
        </p>
      ) : null}
      <ul className={`${ui.card} flex flex-col divide-y divide-border-soft`} aria-label={t("tree")} role="tree">
        {rows.map((c) => (
          <li key={c.id} role="treeitem" aria-level={c.depth + 1} aria-selected={editing === c.id} className="py-2" style={{ paddingLeft: `${c.depth * 1.25}rem` }}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{c.name}</span>
              <span className="text-xs text-subtle">{c.code}</span>
              <span className="text-xs text-muted">
                {t("mapping", {
                  type: c.paperless_document_type ?? "-",
                  tag: c.paperless_tag ?? "-",
                  folder: c.drive_folder ?? "-",
                })}
              </span>
              {editing === c.id ? null : (
                <button type="button" className={ui.buttonSm} onClick={() => edit(c)}>
                  {t("edit")}
                </button>
              )}
            </div>
            {editing === c.id ? (
              <div className="mt-2 grid gap-2 sm:grid-cols-3">
                <label className={ui.label}>
                  {t("documentType")}
                  <input className={ui.input} value={draft.paperless_document_type} maxLength={128} onChange={(e) => setDraft({ ...draft, paperless_document_type: e.target.value })} />
                </label>
                <label className={ui.label}>
                  {t("tag")}
                  <input className={ui.input} value={draft.paperless_tag} maxLength={128} onChange={(e) => setDraft({ ...draft, paperless_tag: e.target.value })} />
                </label>
                <label className={ui.label}>
                  {t("driveFolder")}
                  <input className={ui.input} value={draft.drive_folder} maxLength={64} onChange={(e) => setDraft({ ...draft, drive_folder: e.target.value })} />
                </label>
                <div className={ui.formActions}>
                  <button type="button" className={ui.primary} onClick={() => void save(c.id)}>
                    {t("save")}
                  </button>
                  <button type="button" className={ui.secondary} onClick={() => setEditing(null)}>
                    {t("cancel")}
                  </button>
                </div>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
      <form onSubmit={create} className={`${ui.card} grid gap-2 sm:grid-cols-4`}>
        <h2 className="text-sm font-semibold sm:col-span-4">{t("newTitle")}</h2>
        <label className={ui.label}>
          {t("code")}
          <input className={ui.input} required pattern="[a-z0-9_]{2,63}" value={newCat.code} onChange={(e) => setNewCat({ ...newCat, code: e.target.value })} />
        </label>
        <label className={ui.label}>
          {t("name")}
          <input className={ui.input} required maxLength={200} value={newCat.name} onChange={(e) => setNewCat({ ...newCat, name: e.target.value })} />
        </label>
        <label className={ui.label}>
          {t("parent")}
          <select className={ui.input} value={newCat.parent_id} onChange={(e) => setNewCat({ ...newCat, parent_id: e.target.value })}>
            <option value="">{t("root")}</option>
            {rows.map((c) => (
              <option key={c.id} value={c.id}>
                {" ".repeat(c.depth * 2)}
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-end">
          <button type="submit" className={ui.primary}>
            {t("create")}
          </button>
        </div>
      </form>
    </div>
  );
}
