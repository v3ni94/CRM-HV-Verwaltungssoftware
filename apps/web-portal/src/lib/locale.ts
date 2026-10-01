/** GA11-01, GB14-01: portal languages. The list is not written in code: next.config.ts derives it at
 *  build time from the files messages/<code>.json (NEXT_PUBLIC_PORTAL_LOCALES) and vitest.config.mts does
 *  the same for tests. A further language is only a new file (and MHVP_PORTAL_LOCALES at the API). */
export const DEFAULT_LOCALE = "de";
const CODE = /^[a-z]{2,3}(-[A-Z]{2})?$/;

/** Parses a comma separated code list; invalid codes are dropped, German always stays available. */
export function parseLocales(raw: string | undefined | null): readonly string[] {
  const codes = (raw ?? "").split(",").map((c) => c.trim()).filter((c) => CODE.test(c));
  return [...new Set([DEFAULT_LOCALE, ...codes])];
}

export const SUPPORTED_LOCALES: readonly string[] = parseLocales(process.env.NEXT_PUBLIC_PORTAL_LOCALES);
export type PortalLocale = string;
export const LOCALE_COOKIE = "mhvp_locale";

/** Language names in their own language (not translated, so a user finds their language). */
export function localeName(code: string): string {
  try {
    const name = new Intl.DisplayNames([code], { type: "language" }).of(code);
    return name ? name.charAt(0).toLocaleUpperCase(code) + name.slice(1) : code;
  } catch {
    return code;
  }
}
export const LOCALE_NAMES: Record<string, string> = Object.fromEntries(SUPPORTED_LOCALES.map((c) => [c, localeName(c)]));

export function isLocale(value: unknown, locales: readonly string[] = SUPPORTED_LOCALES): value is PortalLocale {
  return typeof value === "string" && locales.includes(value);
}

/** Order: stored choice (cookie), then Accept-Language by quality, then German. */
export function resolveLocale(
  cookie: string | undefined,
  acceptLanguage: string | null | undefined,
  locales: readonly string[] = SUPPORTED_LOCALES,
): PortalLocale {
  if (isLocale(cookie, locales)) return cookie;
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
  const match = ranked.find((entry) => isLocale(entry.code, locales));
  return match && isLocale(match.code, locales) ? match.code : DEFAULT_LOCALE;
}
