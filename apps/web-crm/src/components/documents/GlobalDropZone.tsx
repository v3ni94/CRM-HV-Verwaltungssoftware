"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type PropertyItem = { id: string; number: string; name: string };
type CategoryItem = { id: string; code: string; name: string };
type ZipResult = { import_run_id: string | null; created: string[]; skipped: { name: string; reason: string }[] };

export type DropOutcome = { filed: number; skipped: { name: string; reason: string }[]; failed: string[] };

function isZip(file: File): boolean {
  return file.type === "application/zip" || file.type === "application/x-zip-compressed" || file.name.toLowerCase().endsWith(".zip");
}

/** Uploads the dropped files with the chosen object and category (11.4): a ZIP archive goes to
 *  the bulk import (import_run, M6-03), every other file to the normal upload. */
export async function fileDropped(files: File[], propertyId: string, categoryId: string): Promise<DropOutcome> {
  const outcome: DropOutcome = { filed: 0, skipped: [], failed: [] };
  const links = propertyId ? JSON.stringify([{ entity_type: "property", entity_id: propertyId }]) : null;
  for (const file of files) {
    const body = new FormData();
    body.set("file", file, file.name);
    if (categoryId) body.set("category_id", categoryId);
    if (links) body.set("links", links);
    if (isZip(file)) {
      const res = await bff<ZipResult>("/api/bff/documents/zip-import", { method: "POST", body });
      if (res.ok) {
        outcome.filed += res.data.created.length;
        outcome.skipped.push(...res.data.skipped);
      } else outcome.failed.push(`${file.name}: ${res.message}`);
    } else {
      const res = await bff<{ id: string }>("/api/bff/documents", { method: "POST", body });
      if (res.ok) outcome.filed += 1;
      else outcome.failed.push(`${file.name}: ${res.message}`);
    }
  }
  return outcome;
}

/** Global drop zone in the header (11.4, M6-02): files dragged anywhere onto the window or
 *  picked with the button open a dialog with object and category; the result reports what was
 *  filed automatically and what was refused. */
export function GlobalDropZone() {
  const t = useTranslations("GlobalDropZone");
  const [dragging, setDragging] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [properties, setProperties] = useState<PropertyItem[]>([]);
  const [categories, setCategories] = useState<CategoryItem[]>([]);
  const [propertyId, setPropertyId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<DropOutcome | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const depth = useRef(0);

  const open = useCallback((picked: File[]) => {
    if (picked.length === 0) return;
    setFiles(picked);
    setOutcome(null);
  }, []);

  useEffect(() => {
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth.current += 1;
      setDragging(true);
    };
    const leave = () => {
      depth.current = Math.max(0, depth.current - 1);
      if (depth.current === 0) setDragging(false);
    };
    const over = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault();
    };
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth.current = 0;
      setDragging(false);
      open(Array.from(e.dataTransfer?.files ?? []));
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [open]);

  useEffect(() => {
    if (files.length === 0 || properties.length > 0) return;
    let active = true;
    void (async () => {
      const [props, cats] = await Promise.all([
        bff<{ items: PropertyItem[] }>("/api/bff/properties?page_size=200"),
        bff<CategoryItem[]>("/api/bff/document-categories"),
      ]);
      if (!active) return;
      if (props.ok) setProperties(props.data.items);
      if (cats.ok) setCategories(cats.data);
    })();
    return () => {
      active = false;
    };
  }, [files, properties.length]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setOutcome(await fileDropped(files, propertyId, categoryId));
    setBusy(false);
  }

  function close() {
    setFiles([]);
    setOutcome(null);
  }

  return (
    <>
      <button type="button" className={ui.buttonSm} onClick={() => inputRef.current?.click()} aria-label={t("button")}>
        {t("button")}
      </button>
      <input
        ref={inputRef}
        type="file"
        multiple
        className="sr-only"
        data-testid="global-drop-input"
        onChange={(e) => {
          open(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
      {dragging ? (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-bg/80" aria-hidden="true">
          <p className="rounded-lg border-2 border-dashed border-accent bg-surface px-6 py-4 text-sm font-medium">{t("overlay")}</p>
        </div>
      ) : null}
      {files.length > 0 ? (
        <div role="dialog" aria-modal="true" aria-label={t("title")} className="fixed inset-0 z-50 flex items-center justify-center bg-bg/70 p-4">
          <form onSubmit={submit} className={`${ui.card} flex w-full max-w-lg flex-col gap-3`}>
            <h2 className="text-base font-semibold">{t("title")}</h2>
            <ul className="text-sm text-muted">
              {files.map((f) => (
                <li key={f.name} className="[overflow-wrap:anywhere]">
                  {f.name}
                  {isZip(f) ? ` (${t("zipHint")})` : ""}
                </li>
              ))}
            </ul>
            <label className={ui.label}>
              {t("property")}
              <select className={ui.input} value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
                <option value="">{t("noProperty")}</option>
                {properties.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.number} {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label className={ui.label}>
              {t("category")}
              <select className={ui.input} value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
                <option value="">{t("noCategory")}</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            {outcome ? (
              <div className="flex flex-col gap-2" role="status">
                <p className={outcome.failed.length ? ui.notice : ui.success}>{t("filed", { count: outcome.filed })}</p>
                {outcome.skipped.map((x) => (
                  <p key={x.name} className={ui.help}>
                    {t("skipped", { name: x.name, reason: x.reason })}
                  </p>
                ))}
                {outcome.failed.map((x) => (
                  <p key={x} className={ui.error}>
                    {x}
                  </p>
                ))}
              </div>
            ) : null}
            <div className={ui.formActions}>
              {outcome ? null : (
                <button type="submit" className={ui.primary} disabled={busy}>
                  {busy ? t("busy") : t("submit")}
                </button>
              )}
              <button type="button" className={ui.secondary} onClick={close}>
                {outcome ? t("close") : t("cancel")}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </>
  );
}
