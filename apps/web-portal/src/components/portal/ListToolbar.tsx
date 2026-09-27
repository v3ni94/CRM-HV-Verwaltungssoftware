"use client";

import { useTranslations } from "next-intl";
import { useId } from "react";

import { ui } from "@/lib/ui";

export type StatusOption = { value: string; label: string };

/** Case-insensitive text match over the given fields (client-side list search). */
export function matchesSearch(query: string, ...fields: (string | null | undefined)[]): boolean {
  const needle = query.trim().toLowerCase();
  if (needle === "") return true;
  return fields.some((field) => (field ?? "").toLowerCase().includes(needle));
}

/** Client-side toolbar for list pages: text search plus optional status filter as toggle
 *  buttons (aria-pressed). The data itself stays loaded by the server page. */
export function ListToolbar({
  search,
  onSearchChange,
  statuses,
  status,
  onStatusChange,
}: {
  search: string;
  onSearchChange: (value: string) => void;
  statuses?: StatusOption[];
  status?: string | null;
  onStatusChange?: (value: string | null) => void;
}) {
  const t = useTranslations("ListFilter");
  const searchId = useId();
  const tab = (active: boolean) => `${ui.buttonSm}${active ? " border-gold bg-gold-soft" : ""}`;
  return (
    <div className="flex flex-col gap-3">
      {statuses && statuses.length > 0 && onStatusChange ? (
        <div role="group" aria-label={t("statusFilterLabel")} className="flex flex-wrap gap-2">
          <button type="button" className={tab(status == null)} aria-pressed={status == null} onClick={() => onStatusChange(null)}>
            {t("statusAll")}
          </button>
          {statuses.map((option) => (
            <button
              key={option.value}
              type="button"
              className={tab(status === option.value)}
              aria-pressed={status === option.value}
              onClick={() => onStatusChange(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : null}
      <div className="flex flex-col gap-1 sm:max-w-xs">
        <label htmlFor={searchId} className={ui.label}>
          {t("searchLabel")}
        </label>
        <input
          id={searchId}
          type="search"
          className={ui.input}
          value={search}
          placeholder={t("searchPlaceholder")}
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </div>
    </div>
  );
}
