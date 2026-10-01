import { getLocale, getTranslations } from "next-intl/server";

import { fetchMaintenance, formatWindow } from "@/lib/maintenance";

/** GB16-01: notice of an announced or running maintenance window (platform wide, plain text). */
export async function MaintenanceBanner() {
  const items = await fetchMaintenance();
  if (items.length === 0) return null;
  const [t, locale] = await Promise.all([getTranslations("AD10"), getLocale()]);
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-1">
      {items.map((item) => (
        <p
          key={item.id}
          className="border-b border-border-soft bg-surface-2 px-4 py-2 text-sm text-fg sm:px-6 lg:px-8"
        >
          <strong>{t(item.phase === "active" ? "bannerActive" : "bannerAnnounced")}</strong>{" "}
          {t("bannerPeriod", { from: formatWindow(item.starts_at, locale), to: formatWindow(item.ends_at, locale) })}
          {". "}
          {locale === "de" ? item.text_de : item.text_en}
        </p>
      ))}
    </div>
  );
}
