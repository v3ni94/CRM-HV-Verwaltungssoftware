/**
 * Appearance of the web CRM (operator decision 27.09.2026): day mode is design A "Klar und
 * ruhig", evening mode is design B "Dunkel und präzise". The user picks day, evening or auto;
 * auto resolves to evening from 19:00 to 06:59 local time and is re-evaluated every minute.
 *
 * Storage: server side in ``app_user.ui_preferences.theme`` (PATCH /api/v1/auth/me/preferences
 * through the BFF)
 * with a localStorage copy for the first paint. Parsing, storage, the inline script and the
 * external store are shared with the portal (@mhvp/ui/theme-mode); this file adds the CRM rules
 * (time based auto, server persistence).
 */
import {
  DEFAULT_THEME,
  THEME_PREFERENCES,
  applyResolvedTheme,
  createThemeStore,
  parseThemePreference,
  themeBootScript,
  type ResolvedTheme,
  type ThemePreference,
} from "@mhvp/ui/theme-mode";

export type { ResolvedTheme, ThemePreference };
export { DEFAULT_THEME, THEME_PREFERENCES, applyResolvedTheme, parseThemePreference };

export const THEME_STORAGE_KEY = "mhvp-theme";
export const EVENING_FROM_HOUR = 19;
export const EVENING_UNTIL_HOUR = 7;
// Through the BFF: the API takes the bearer token only, which the BFF adds from the httpOnly
// session cookie (a direct /api/v1 call from the browser never reached the account).
const PREFERENCES_ENDPOINT = "/api/bff/auth/me/preferences";
const MINUTE_MS = 60_000;

export function isEveningHour(date: Date): boolean {
  const hour = date.getHours();
  return hour >= EVENING_FROM_HOUR || hour < EVENING_UNTIL_HOUR;
}

function persistToServer(preference: ThemePreference): void {
  void fetch(PREFERENCES_ENDPOINT, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ theme: preference }),
  }).catch(() => {
    /* offline or session expired: the local copy keeps this browser consistent */
  });
}

export const crmThemeStore = createThemeStore({
  storageKey: THEME_STORAGE_KEY,
  resolveAuto: (now) => (isEveningHour(now) ? "evening" : "day"),
  watchAuto: (onChange) => {
    const timer = setInterval(onChange, MINUTE_MS);
    return () => clearInterval(timer);
  },
  persist: persistToServer,
});

const EVENING_HOUR_EXPRESSION = `(function(){var h=new Date().getHours();return h>=${EVENING_FROM_HOUR}||h<${EVENING_UNTIL_HOUR}})()`;

/** Inline script for the root layout: applies the stored preference before the first paint. */
export const THEME_SCRIPT = themeBootScript(THEME_STORAGE_KEY, EVENING_HOUR_EXPRESSION);

/** Script emitted by the app shell with the server side preference: overrides a stale or
 *  missing local copy before the page content paints (new device, other browser). */
export function serverThemeScript(preference: unknown): string {
  const value = parseThemePreference(preference);
  return `try{localStorage.setItem(${JSON.stringify(THEME_STORAGE_KEY)},"${value}")}catch(e){}try{document.documentElement.setAttribute("data-theme","${value}"==="auto"?(${EVENING_HOUR_EXPRESSION}?"evening":"day"):"${value}")}catch(e){}`;
}

export function resolveTheme(preference: ThemePreference, now: Date = new Date()): ResolvedTheme {
  return crmThemeStore.resolve(preference, now);
}

export const readStoredPreference = crmThemeStore.readStored;
export const getThemePreference = crmThemeStore.get;
export const getServerThemePreference = crmThemeStore.getServer;
export const subscribeTheme = crmThemeStore.subscribe;
/** Sets the preference: applies it, stores it locally and on the server (best effort). */
export const setThemePreference = crmThemeStore.set;
/** For tests: forget the cached preference. */
export const resetThemeStore = crmThemeStore.reset;

const THEME_COLOR_VARIABLE = "--mhvp-color-bg";

/** Writes the current page ground (token --mhvp-color-bg of the active data-theme) into
 *  <meta name="theme-color">, so the status bar of an installed app follows the day and
 *  evening theme without a hex value in code (M31 WP5, M30-08). Read from getComputedStyle,
 *  so tenant branding and future token changes carry over. */
export function syncThemeColorMeta(doc: Document = document): void {
  const value = getComputedStyle(doc.documentElement).getPropertyValue(THEME_COLOR_VARIABLE).trim();
  if (!value) return;
  let meta = doc.querySelector<HTMLMetaElement>('meta[name="theme-color"]:not([media])');
  if (!meta) {
    meta = doc.createElement("meta");
    meta.setAttribute("name", "theme-color");
    doc.head.appendChild(meta);
  }
  if (meta.getAttribute("content") !== value) meta.setAttribute("content", value);
}

/** Keeps the meta in step with every change of data-theme (manual switch, automatic evening
 *  mode, server preference). Returns the stop function. */
export function installThemeColorMeta(doc: Document = document): () => void {
  syncThemeColorMeta(doc);
  if (typeof MutationObserver === "undefined") return () => undefined;
  const observer = new MutationObserver(() => syncThemeColorMeta(doc));
  observer.observe(doc.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}
