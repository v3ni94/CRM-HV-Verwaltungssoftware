/**
 * Appearance of the web CRM (operator decision 27.09.2026): day mode is design A "Klar und
 * ruhig", evening mode is design B "Dunkel und präzise". The user picks day, evening or auto;
 * auto resolves to evening from 19:00 to 06:59 local time and is re-evaluated every minute.
 *
 * Storage: server side in ``app_user.ui_preferences.theme`` (PATCH /api/v1/auth/me/preferences)
 * with a localStorage copy for the first paint. Every stored value is parsed tolerantly
 * (lesson of incident 1.35.1): unknown values fall back to auto, never throw.
 */
export type ThemePreference = "day" | "evening" | "auto";
export type ResolvedTheme = "day" | "evening";

export const THEME_STORAGE_KEY = "mhvp-theme";
export const THEME_PREFERENCES = ["day", "evening", "auto"] as const;
export const DEFAULT_THEME: ThemePreference = "auto";
export const EVENING_FROM_HOUR = 19;
export const EVENING_UNTIL_HOUR = 7;
const PREFERENCES_ENDPOINT = "/api/v1/auth/me/preferences";

/** Tolerant parsing: accepts the current values, maps the legacy light/dark/system values of
 *  versions up to 1.36.x and returns the default for anything else (null, JSON, numbers). */
export function parseThemePreference(raw: unknown): ThemePreference {
  if (typeof raw !== "string") return DEFAULT_THEME;
  const value = raw.trim().toLowerCase();
  if (value === "day" || value === "light") return "day";
  if (value === "evening" || value === "dark") return "evening";
  return DEFAULT_THEME;
}

export function isEveningHour(date: Date): boolean {
  const hour = date.getHours();
  return hour >= EVENING_FROM_HOUR || hour < EVENING_UNTIL_HOUR;
}

export function resolveTheme(preference: ThemePreference, now: Date = new Date()): ResolvedTheme {
  if (preference === "auto") return isEveningHour(now) ? "evening" : "day";
  return preference;
}

export function applyResolvedTheme(theme: ResolvedTheme): void {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", theme);
}

export function readStoredPreference(): ThemePreference {
  try {
    return parseThemePreference(window.localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return DEFAULT_THEME;
  }
}

function writeStoredPreference(preference: ThemePreference): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    /* storage unavailable: the server copy still holds the choice */
  }
}

/** Inline script for the root layout: applies the stored preference before the first paint.
 *  Mirrors parseThemePreference and resolveTheme; any error leaves the day theme in place. */
export const THEME_SCRIPT = `try{var p="auto";try{var s=localStorage.getItem("${THEME_STORAGE_KEY}");s=typeof s==="string"?s.trim().toLowerCase():"";if(s==="day"||s==="light")p="day";else if(s==="evening"||s==="dark")p="evening"}catch(e){}var h=new Date().getHours();document.documentElement.setAttribute("data-theme",p==="auto"?(h>=${EVENING_FROM_HOUR}||h<${EVENING_UNTIL_HOUR}?"evening":"day"):p)}catch(e){}`;

/** Script emitted by the app shell with the server side preference: overrides a stale or
 *  missing local copy before the page content paints (new device, other browser). */
export function serverThemeScript(preference: unknown): string {
  const value = parseThemePreference(preference);
  return `try{localStorage.setItem("${THEME_STORAGE_KEY}","${value}")}catch(e){}try{var h=new Date().getHours();document.documentElement.setAttribute("data-theme","${value}"==="auto"?(h>=${EVENING_FROM_HOUR}||h<${EVENING_UNTIL_HOUR}?"evening":"day"):"${value}")}catch(e){}`;
}

// Small external store so the header switch and the profile switch stay in sync.
type Listener = () => void;
const listeners = new Set<Listener>();
let current: ThemePreference | null = null;

export function getThemePreference(): ThemePreference {
  if (current === null) current = typeof window === "undefined" ? DEFAULT_THEME : readStoredPreference();
  return current;
}

export function getServerThemePreference(): ThemePreference {
  return DEFAULT_THEME;
}

export function subscribeTheme(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Sets the preference: applies it, stores it locally and on the server (best effort). */
export function setThemePreference(preference: ThemePreference, options: { persist?: boolean } = {}): void {
  const value = parseThemePreference(preference);
  current = value;
  applyResolvedTheme(resolveTheme(value));
  writeStoredPreference(value);
  listeners.forEach((listener) => listener());
  if (options.persist === false) return;
  try {
    void fetch(PREFERENCES_ENDPOINT, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ theme: value }),
    }).catch(() => {
      /* offline or session expired: the local copy keeps this browser consistent */
    });
  } catch {
    /* fetch unavailable */
  }
}

/** For tests: forget the cached preference. */
export function resetThemeStore(): void {
  current = null;
}
