"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

/** Number of text variants stored per time window (Greeting.<window>.0 .. Greeting.<window>.n-1
 *  in messages/de.json and en.json). Kept in one place so `greetingKey` and the catalogue stay
 *  in sync. */
const VARIANT_COUNT: Record<Window, number> = { morning: 3, midday: 3, evening: 3, late: 2 };

type Window = "morning" | "midday" | "evening" | "late";

/** Hour of the day in the tenant time zone (Europe/Berlin), independent of the viewer's or
 *  server's own time zone. */
function berlinHour(date: Date): number {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Berlin", hour: "2-digit", hour12: false }).formatToParts(date);
  const hour = parts.find((part) => part.type === "hour")?.value ?? "0";
  // "24" at midnight with this formatter/locale combination means 0.
  return Number.parseInt(hour, 10) % 24;
}

/** Day of the year (1-366) in the tenant time zone, used to pick a variant deterministically:
 *  stable within one day, changing from day to day so the greeting feels alive. */
function berlinDayOfYear(date: Date): number {
  const iso = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Berlin" }).format(date); // YYYY-MM-DD
  const parts = iso.split("-").map((part) => Number.parseInt(part, 10));
  const year = parts[0] ?? 1970;
  const month = parts[1] ?? 1;
  const day = parts[2] ?? 1;
  const start = Date.UTC(year, 0, 1);
  const current = Date.UTC(year, month - 1, day);
  return Math.round((current - start) / 86_400_000) + 1;
}

function windowOf(hour: number): Window {
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 18) return "midday";
  if (hour >= 18 && hour < 22) return "evening";
  return "late";
}

/** Message key for the greeting text at `date` (Europe/Berlin), e.g. "morning.1". The variant
 *  index rotates by day of year so a reload during the same day never changes the text. */
export function greetingKey(date: Date): string {
  const window = windowOf(berlinHour(date));
  const variant = berlinDayOfYear(date) % VARIANT_COUNT[window];
  return `${window}.${variant}`;
}

/** First name for the informal "Du" address: first word of the display name, or, missing
 *  that, the local part of the e-mail before the first dot, capitalised. */
export function firstName(displayName: string | null | undefined, email: string | null | undefined): string {
  const trimmed = displayName?.trim();
  if (trimmed) return trimmed.split(/\s+/)[0] ?? trimmed;
  const local = email?.split("@")[0]?.split(".")[0];
  if (!local) return "";
  return local.charAt(0).toUpperCase() + local.slice(1);
}

/** Dashboard greeting (operator 27.09.2026): informal, per first name, varying by time of day
 *  and lightly by day so it feels alive without jumping on reload. Client component so the
 *  viewer's own clock decides the window; the server render always uses the safe, static
 *  fallback text below so hydration never mismatches. */
export function Greeting({ displayName, email }: { displayName: string | null | undefined; email: string | null | undefined }) {
  const t = useTranslations("Greeting");
  const locale = useLocale();
  const name = firstName(displayName, email);
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
  }, []);

  if (!now) {
    // SSR-safe fallback: no window/variant guess before the client clock is known.
    return (
      <div className="flex flex-col gap-1">
        <p className="mhvp-title font-semibold text-fg">{t("fallback", { name })}</p>
      </div>
    );
  }

  const dateLine = new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
    timeZone: "Europe/Berlin",
    weekday: "long",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(now);

  return (
    <div className="flex flex-col gap-1">
      <p className="mhvp-title font-semibold text-fg">{t(greetingKey(now), { name })}</p>
      <p className="text-sm text-muted">{dateLine}</p>
    </div>
  );
}
