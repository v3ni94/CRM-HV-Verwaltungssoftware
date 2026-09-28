/**
 * Appearance of the customer portal: the same two modes as the web CRM (day "Klar und ruhig",
 * evening "Dunkel und präzise", tokens from @mhvp/ui). Default is auto, which follows the
 * operating system preference (prefers-color-scheme) and reacts to changes while the page is
 * open. The manual choice Hell, Dunkel or Automatisch is kept in this browser's localStorage
 * only; portal accounts have no preference endpoint.
 */
import {
  PREFERS_EVENING_EXPRESSION,
  createThemeStore,
  prefersEvening,
  themeBootScript,
  watchPrefersEvening,
} from "@mhvp/ui/theme-mode";

export type { ResolvedTheme, ThemePreference } from "@mhvp/ui/theme-mode";

/** Own key: the portal's auto rule differs from the CRM's, and the apps run on own origins. */
export const PORTAL_THEME_STORAGE_KEY = "mhvp-portal-theme";

export const portalThemeStore = createThemeStore({
  storageKey: PORTAL_THEME_STORAGE_KEY,
  resolveAuto: () => (prefersEvening() ? "evening" : "day"),
  watchAuto: watchPrefersEvening,
});

/** Inline script for the root layout: applies the stored choice or the operating system
 *  preference before the first paint (no flash of the wrong mode). */
export const PORTAL_THEME_SCRIPT = themeBootScript(PORTAL_THEME_STORAGE_KEY, PREFERS_EVENING_EXPRESSION);
