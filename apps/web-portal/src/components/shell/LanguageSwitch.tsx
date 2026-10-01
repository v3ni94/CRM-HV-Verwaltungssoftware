"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

import { LOCALE_NAMES, SUPPORTED_LOCALES, isLocale } from "@/lib/locale";

/** Language selection in the portal header (GA11-01); the choice is a cookie, the page reloads. */
export function LanguageSwitch({ className = "" }: { className?: string }) {
  const t = useTranslations("Portal");
  const locale = useLocale();
  const router = useRouter();
  async function change(value: string) {
    if (!isLocale(value)) return;
    const res = await fetch("/api/locale", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ locale: value }),
    });
    if (res.ok) router.refresh();
  }
  return (
    <label className={`inline-flex items-center gap-1 text-xs text-muted ${className}`}>
      <span className="sr-only">{t("language.label")}</span>
      <select
        value={locale}
        onChange={(event) => void change(event.target.value)}
        className="min-h-9 rounded-full border border-border bg-surface px-2 text-xs text-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
      >
        {SUPPORTED_LOCALES.map((code) => (
          <option key={code} value={code} lang={code}>
            {LOCALE_NAMES[code]}
          </option>
        ))}
      </select>
    </label>
  );
}
