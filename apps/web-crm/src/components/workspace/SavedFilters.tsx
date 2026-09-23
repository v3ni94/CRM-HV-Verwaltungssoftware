"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type SavedFilter = { id: string; resource: string; name: string; params: Record<string, string> };

/** Saved list filters of the current user; the params are the list's query string. */
export function SavedFilters({ resource, basePath, current }: { resource: string; basePath: string; current: Record<string, string> }) {
  const t = useTranslations("Workspace");
  const [filters, setFilters] = useState<SavedFilter[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = await bff<SavedFilter[]>(`/api/bff/workspace/filters?resource=${resource}`);
    if (result.ok) setFilters(result.data);
  }, [resource]);

  useEffect(() => {
    void load();
  }, [load]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const result = await bff("/api/bff/workspace/filters", {
      method: "PUT",
      body: JSON.stringify({ resource, name: name.trim(), params: current }),
    });
    if (result.ok) {
      setName("");
      setError(null);
      await load();
    } else setError(result.message);
  }

  async function remove(id: string) {
    const result = await bff(`/api/bff/workspace/filters/${id}`, { method: "DELETE" });
    if (result.ok) await load();
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm" aria-label={t("savedFilters")} role="group">
      <span className="text-muted">{t("savedFilters")}:</span>
      {filters.map((f) => (
        <span key={f.id} className="inline-flex items-center gap-1 rounded border border-border px-2 py-0.5">
          <Link href={`${basePath}?${new URLSearchParams(f.params)}`} className="hover:underline">
            {f.name}
          </Link>
          <button type="button" aria-label={t("deleteFilter", { name: f.name })} onClick={() => void remove(f.id)}>
            ×
          </button>
        </span>
      ))}
      <form onSubmit={save} className="flex items-center gap-1">
        <label htmlFor="filter-name" className="sr-only">
          {t("filterName")}
        </label>
        <input
          id="filter-name"
          required
          maxLength={100}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("filterName")}
          className={`${ui.input} w-40`}
        />
        <button type="submit" className={ui.button}>
          {t("saveFilter")}
        </button>
      </form>
      {error ? <span className={ui.error}>{error}</span> : null}
    </div>
  );
}
