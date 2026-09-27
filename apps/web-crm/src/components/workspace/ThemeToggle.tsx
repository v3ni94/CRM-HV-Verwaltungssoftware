"use client";

import { useTranslations } from "next-intl";
import { useEffect, useSyncExternalStore } from "react";

import {
  THEME_PREFERENCES,
  applyResolvedTheme,
  getServerThemePreference,
  getThemePreference,
  parseThemePreference,
  resolveTheme,
  setThemePreference,
  subscribeTheme,
  type ThemePreference,
} from "@/lib/theme";

export { THEME_SCRIPT } from "@/lib/theme";

const MINUTE_MS = 60_000;

export function useThemePreference(): ThemePreference {
  return useSyncExternalStore(subscribeTheme, getThemePreference, getServerThemePreference);
}

/** Keeps the document theme current: adopts the server side preference once and re-evaluates
 *  the automatic mode every minute (evening from 19 to 7 o'clock local time). */
export function ThemeController({ serverPreference }: { serverPreference?: unknown }) {
  const preference = useThemePreference();

  useEffect(() => {
    if (serverPreference === undefined || serverPreference === null) return;
    setThemePreference(parseThemePreference(serverPreference), { persist: false });
  }, [serverPreference]);

  useEffect(() => {
    applyResolvedTheme(resolveTheme(preference));
    if (preference !== "auto") return;
    const timer = setInterval(() => applyResolvedTheme(resolveTheme("auto")), MINUTE_MS);
    return () => clearInterval(timer);
  }, [preference]);

  return null;
}

/** Segmented switch Tag, Abend, Automatisch; stored per user. */
export function ThemeSwitch({ className = "" }: { className?: string }) {
  const t = useTranslations("Workspace");
  const preference = useThemePreference();
  return (
    <div
      role="radiogroup"
      aria-label={t("themeGroup")}
      className={`inline-flex items-center gap-0.5 rounded-full border border-border bg-surface p-0.5 ${className}`}
    >
      {THEME_PREFERENCES.map((value) => {
        const checked = preference === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={checked}
            onClick={() => setThemePreference(value)}
            className={`min-h-8 rounded-full px-3 text-xs font-medium transition duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus ${
              checked ? "bg-accent-soft text-fg shadow-xs" : "text-muted hover:text-fg"
            }`}
          >
            {t(`theme.${value}`)}
          </button>
        );
      })}
    </div>
  );
}
