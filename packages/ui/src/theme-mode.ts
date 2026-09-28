/**
 * Shared appearance core of the MHVP web apps (operator decision 27.09.2026): day mode is
 * design A "Klar und ruhig", evening mode is design B "Dunkel und präzise". The user picks day,
 * evening or auto; each app decides what auto means (web CRM: evening from 19 to 7 o'clock,
 * web portal: the operating system preference) and how a choice is persisted beyond the
 * browser (web CRM: user preference endpoint, web portal: local storage only).
 *
 * The resolved mode is always written explicitly as data-theme on <html> (tokens.css), so no
 * component reads prefers-color-scheme itself. Every stored value is parsed tolerantly (lesson
 * of incident 1.35.1): unknown values fall back to auto, nothing here throws.
 *
 * Framework free (no React): safe to import from server components and inline script builders.
 * The React hook and the switch component live in ./ThemeSwitch.tsx.
 */
export type ThemePreference = "day" | "evening" | "auto";
export type ResolvedTheme = "day" | "evening";

export const THEME_PREFERENCES = ["day", "evening", "auto"] as const;
export const DEFAULT_THEME: ThemePreference = "auto";
/** Media query of the operating system dark preference (auto mode of the portal). */
export const PREFERS_DARK_QUERY = "(prefers-color-scheme: dark)";

/** Tolerant parsing: accepts the current values, maps the legacy light/dark values of versions
 *  up to 1.36.x and returns the default for anything else (null, JSON, numbers). */
export function parseThemePreference(raw: unknown): ThemePreference {
  if (typeof raw !== "string") return DEFAULT_THEME;
  const value = raw.trim().toLowerCase();
  if (value === "day" || value === "light") return "day";
  if (value === "evening" || value === "dark") return "evening";
  return DEFAULT_THEME;
}

export function applyResolvedTheme(theme: ResolvedTheme): void {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", theme);
}

export function readStoredThemePreference(storageKey: string): ThemePreference {
  try {
    return parseThemePreference(window.localStorage.getItem(storageKey));
  } catch {
    return DEFAULT_THEME;
  }
}

export function writeStoredThemePreference(storageKey: string, preference: ThemePreference): void {
  try {
    window.localStorage.setItem(storageKey, preference);
  } catch {
    /* storage unavailable (private mode, quota, blocked site data): the choice lasts this page */
  }
}

/** Operating system preference; day when matchMedia is unavailable (old browser, jsdom). */
export function prefersEvening(): boolean {
  try {
    return typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia(PREFERS_DARK_QUERY).matches
      : false;
  } catch {
    return false;
  }
}

/** Calls onChange whenever the operating system preference changes; returns the cleanup. */
export function watchPrefersEvening(onChange: () => void): () => void {
  try {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => {};
    const query = window.matchMedia(PREFERS_DARK_QUERY);
    if (typeof query.addEventListener === "function") {
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    }
    // Safari before 14 only knows the deprecated listener API.
    query.addListener(onChange);
    return () => query.removeListener(onChange);
  } catch {
    return () => {};
  }
}

/**
 * Inline script for the root layout: applies the stored preference before the first paint (no
 * flash). Mirrors parseThemePreference; `autoEveningExpression` is a JavaScript expression that
 * is true when auto should resolve to evening. Any error leaves the day theme in place.
 */
export function themeBootScript(storageKey: string, autoEveningExpression: string): string {
  const key = JSON.stringify(storageKey);
  return `try{var p="auto";try{var s=localStorage.getItem(${key});s=typeof s==="string"?s.trim().toLowerCase():"";if(s==="day"||s==="light")p="day";else if(s==="evening"||s==="dark")p="evening"}catch(e){}document.documentElement.setAttribute("data-theme",p==="auto"?((${autoEveningExpression})?"evening":"day"):p)}catch(e){}`;
}

/** Boot script expression for auto = operating system preference. */
export const PREFERS_EVENING_EXPRESSION = `typeof matchMedia==="function"&&matchMedia(${JSON.stringify(PREFERS_DARK_QUERY)}).matches`;

export type ThemeStoreOptions = {
  /** localStorage key of this app (each app has its own origin and its own auto rule). */
  storageKey: string;
  /** What auto means in this app. */
  resolveAuto: (now: Date) => ResolvedTheme;
  /** Re-evaluates auto while it is active (timer, media query listener); returns the cleanup. */
  watchAuto: (onChange: () => void) => () => void;
  /** Optional persistence beyond this browser (best effort, never throws into the caller). */
  persist?: (preference: ThemePreference) => void;
};

export type ThemeStore = {
  readonly storageKey: string;
  resolve: (preference: ThemePreference, now?: Date) => ResolvedTheme;
  readStored: () => ThemePreference;
  /** Client snapshot for useSyncExternalStore. */
  get: () => ThemePreference;
  /** Server snapshot for useSyncExternalStore (the stored value is unknown on the server). */
  getServer: () => ThemePreference;
  subscribe: (listener: () => void) => () => void;
  /** Applies, stores locally, notifies subscribers and persists unless persist is false. */
  set: (preference: ThemePreference, options?: { persist?: boolean }) => void;
  watchAuto: (onChange: () => void) => () => void;
  /** For tests: forget the cached preference. */
  reset: () => void;
};

/** Small external store so several switches on one page (header, profile) stay in sync. */
export function createThemeStore(options: ThemeStoreOptions): ThemeStore {
  const { storageKey, resolveAuto, watchAuto, persist } = options;
  const listeners = new Set<() => void>();
  let current: ThemePreference | null = null;

  const resolve = (preference: ThemePreference, now: Date = new Date()): ResolvedTheme =>
    preference === "auto" ? resolveAuto(now) : preference;
  const readStored = () => readStoredThemePreference(storageKey);

  return {
    storageKey,
    resolve,
    readStored,
    get() {
      if (current === null) current = typeof window === "undefined" ? DEFAULT_THEME : readStored();
      return current;
    },
    getServer: () => DEFAULT_THEME,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    set(preference, setOptions = {}) {
      const value = parseThemePreference(preference);
      current = value;
      applyResolvedTheme(resolve(value));
      writeStoredThemePreference(storageKey, value);
      listeners.forEach((listener) => listener());
      if (setOptions.persist === false || !persist) return;
      try {
        persist(value);
      } catch {
        /* persistence is best effort: the local copy keeps this browser consistent */
      }
    },
    watchAuto,
    reset() {
      current = null;
    },
  };
}
