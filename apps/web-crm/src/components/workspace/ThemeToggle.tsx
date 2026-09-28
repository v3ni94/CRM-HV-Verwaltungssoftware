"use client";

import { ThemeSwitch as SharedThemeSwitch, useThemePreference as useSharedThemePreference, useThemeSync } from "@mhvp/ui/theme-switch";
import { useTranslations } from "next-intl";
import { useEffect } from "react";

import { crmThemeStore, parseThemePreference, setThemePreference, type ThemePreference } from "@/lib/theme";

export { THEME_SCRIPT } from "@/lib/theme";

export function useThemePreference(): ThemePreference {
  return useSharedThemePreference(crmThemeStore);
}

/** Keeps the document theme current: adopts the server side preference once and re-evaluates
 *  the automatic mode every minute (evening from 19 to 7 o'clock local time). */
export function ThemeController({ serverPreference }: { serverPreference?: unknown }) {
  useThemeSync(crmThemeStore);

  useEffect(() => {
    if (serverPreference === undefined || serverPreference === null) return;
    setThemePreference(parseThemePreference(serverPreference), { persist: false });
  }, [serverPreference]);

  return null;
}

/** Segmented switch Tag, Abend, Automatisch; stored per user. */
export function ThemeSwitch({ className = "" }: { className?: string }) {
  const t = useTranslations("Workspace");
  return (
    <SharedThemeSwitch
      store={crmThemeStore}
      label={t("themeGroup")}
      optionLabels={{ day: t("theme.day"), evening: t("theme.evening"), auto: t("theme.auto") }}
      className={`inline-flex items-center gap-0.5 rounded-full border border-border bg-surface-2 p-0.5 ${className}`}
      optionClassName={(checked) =>
        `min-h-11 rounded-full px-3 text-xs font-medium transition duration-150 sm:pointer-fine:min-h-8 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus ${
          checked ? "bg-accent-soft text-fg shadow-xs ring-1 ring-inset ring-accent" : "text-muted hover:text-fg"
        }`
      }
    />
  );
}
