/** GA11-01 (14): portal languages. A further language needs only a file messages/<code>.json,
 *  its code in SUPPORTED_LOCALES and its name in LOCALE_NAMES (the message loader imports by code). */
export const SUPPORTED_LOCALES = ["de", "en"] as const;
export type PortalLocale = (typeof SUPPORTED_LOCALES)[number];
export const DEFAULT_LOCALE: PortalLocale = "de";
export const LOCALE_COOKIE = "mhvp_locale";
/** Language names in their own language (not translated, so a user finds their language). */
export const LOCALE_NAMES: Record<PortalLocale, string> = { de: "Deutsch", en: "English" };

export function isLocale(value: unknown): value is PortalLocale {
  return typeof value === "string" && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

/** Order: stored choice (cookie), then Accept-Language by quality, then German. */
export function resolveLocale(cookie: string | undefined, acceptLanguage: string | null | undefined): PortalLocale {
  if (isLocale(cookie)) return cookie;
  const ranked = (acceptLanguage ?? "")
    .split(",")
    .map((part) => {
      const [tag, ...params] = part.trim().split(";");
      const q = params.map((p) => p.trim()).find((p) => p.startsWith("q="));
      const quality = q ? Number.parseFloat(q.slice(2)) : 1;
      return { code: (tag ?? "").trim().toLowerCase().split("-")[0], quality: Number.isNaN(quality) ? 0 : quality };
    })
    .filter((entry) => entry.code && entry.quality > 0)
    .sort((a, b) => b.quality - a.quality);
  const match = ranked.find((entry) => isLocale(entry.code));
  return match && isLocale(match.code) ? match.code : DEFAULT_LOCALE;
}
