"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

type Theme = "system" | "light" | "dark";
const KEY = "mhvp-theme";
const ORDER: Theme[] = ["system", "light", "dark"];

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

/** Inline script for the root layout: applies the stored theme before first paint. */
export const THEME_SCRIPT = `try{var t=localStorage.getItem("${KEY}");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}`;

/** Light, dark or system appearance; stored per browser (no personal data on the server). */
export function ThemeToggle() {
  const t = useTranslations("Workspace");
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => {
    try {
      const stored = localStorage.getItem(KEY);
      if (stored === "light" || stored === "dark") setTheme(stored);
    } catch {
      /* storage unavailable: keep system */
    }
  }, []);

  function next() {
    const value = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length]!;
    setTheme(value);
    applyTheme(value);
    try {
      if (value === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, value);
    } catch {
      /* ignore */
    }
  }

  return (
    <button
      type="button"
      className="inline-flex h-9 items-center gap-1.5 rounded-full border border-border bg-bg px-3 text-sm font-medium text-fg transition duration-150 hover:border-gold hover:bg-surface focus:outline-none focus:ring-2 focus:ring-gold/40"
      onClick={next}
      aria-label={t("themeLabel", { theme: t(`theme.${theme}`) })}
    >
      {t(`theme.${theme}`)}
    </button>
  );
}
