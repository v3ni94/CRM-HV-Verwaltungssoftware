import { cookies, headers } from "next/headers";
import { getRequestConfig } from "next-intl/server";

import { DEFAULT_LOCALE, LOCALE_COOKIE, resolveLocale } from "@/lib/locale";

type Messages = { [key: string]: string | Messages };
function merge(base: Messages, over: Messages): Messages {
  const out: Messages = { ...base };
  for (const [key, value] of Object.entries(over)) {
    const current = out[key];
    out[key] =
      typeof value === "object" && value !== null && typeof current === "object" ? merge(current, value) : value;
  }
  return out;
}

export const defaultLocale = DEFAULT_LOCALE;
// Timestamps are stored in UTC (ISO 8601); the UI shows them in German business time.
export const timeZone = "Europe/Berlin";

// GA11-01: language from the cookie, else Accept-Language, else German; the files in
// messages/ are the only place a further language is added.
export default getRequestConfig(async () => {
  const [jar, hdrs] = await Promise.all([cookies(), headers()]);
  const locale = resolveLocale(jar.get(LOCALE_COOKIE)?.value, hdrs.get("accept-language"));
  const german = (await import("../../messages/de.json")).default as Messages;
  // GB14-01: missing keys of a further language fall back to German.
  const messages =
    locale === DEFAULT_LOCALE ? german : merge(german, (await import(`../../messages/${locale}.json`)).default);
  return { locale, timeZone, messages };
});
