// Business calendar day in Europe/Berlin (GAI-104, rule M1-09). Safe on server and client.
// The UTC day (toISOString slice) lags one day behind between
// 00:00 and 02:00 local time.
const BUSINESS_TZ = "Europe/Berlin";

export function today(now: Date = new Date()): string {
  // sv-SE formats as YYYY-MM-DD
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: BUSINESS_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}
