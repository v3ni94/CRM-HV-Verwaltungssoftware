import { cookies, headers } from "next/headers";
import { getRequestConfig } from "next-intl/server";

import { DEFAULT_LOCALE, LOCALE_COOKIE, resolveLocale } from "@/lib/locale";

export const defaultLocale = DEFAULT_LOCALE;
// Timestamps are stored in UTC (ISO 8601); the UI shows them in German business time.
export const timeZone = "Europe/Berlin";

// GA11-01: language from the cookie, else Accept-Language, else German; the files in
// messages/ are the only place a further language is added.
export default getRequestConfig(async () => {
  const [jar, hdrs] = await Promise.all([cookies(), headers()]);
  const locale = resolveLocale(jar.get(LOCALE_COOKIE)?.value, hdrs.get("accept-language"));
  return {
    locale,
    timeZone,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
