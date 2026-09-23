import { getRequestConfig } from "next-intl/server";

// No locale routing in M1: German is the default, English messages are prepared.
export const defaultLocale = "de";
// Timestamps are stored in UTC (ISO 8601); the UI shows them in German business time.
export const timeZone = "Europe/Berlin";

export default getRequestConfig(async () => {
  const locale = defaultLocale;
  return {
    locale,
    timeZone,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
