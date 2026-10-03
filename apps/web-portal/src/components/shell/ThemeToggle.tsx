"use client";

import { ThemeSwitch as SharedThemeSwitch, useThemeSync } from "@mhvp/ui/theme-switch";
import { useTranslations } from "next-intl";

import { portalThemeStore } from "@/lib/theme";

/** Keeps data-theme on <html> current on every portal page (also sign in and invitation):
 *  in automatic mode it follows changes of the operating system preference live. */
export function ThemeController() {
  useThemeSync(portalThemeStore);
  return null;
}

/** Segmented switch Hell, Dunkel, Automatisch in the portal header; stored in this browser. */
export function ThemeSwitch({ className = "" }: { className?: string }) {
  const t = useTranslations("Portal");
  return (
    <SharedThemeSwitch
      store={portalThemeStore}
      label={t("theme.group")}
      optionLabels={{ day: t("theme.day"), evening: t("theme.evening"), auto: t("theme.auto") }}
      className={`inline-flex items-center gap-0.5 rounded-full border border-border bg-surface p-0.5 ${className}`}
      optionClassName={(checked) =>
        `inline-flex min-h-11 pointer-fine:min-h-9 items-center rounded-full px-2.5 text-xs font-medium transition duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus sm:px-3 ${
          checked ? "bg-accent-soft text-fg shadow-xs ring-1 ring-inset ring-accent" : "text-muted hover:text-fg"
        }`
      }
    />
  );
}
