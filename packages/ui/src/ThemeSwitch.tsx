"use client";

import { useEffect, useRef, useSyncExternalStore, type KeyboardEvent } from "react";

import { THEME_PREFERENCES, applyResolvedTheme, type ThemePreference, type ThemeStore } from "./theme-mode";

/** Current preference of a theme store; server render and hydration start with auto. */
export function useThemePreference(store: ThemeStore): ThemePreference {
  return useSyncExternalStore(store.subscribe, store.get, store.getServer);
}

/** Keeps data-theme on <html> current: applies the preference and, while auto is active,
 *  re-evaluates it through the store's watcher (timer or operating system preference). */
export function useThemeSync(store: ThemeStore): ThemePreference {
  const preference = useThemePreference(store);
  useEffect(() => {
    applyResolvedTheme(store.resolve(preference));
    if (preference !== "auto") return;
    return store.watchAuto(() => applyResolvedTheme(store.resolve("auto")));
  }, [preference, store]);
  return preference;
}

export type ThemeSwitchProps = {
  store: ThemeStore;
  /** Accessible name of the radio group (e.g. "Darstellung"). */
  label: string;
  /** Visible label per option, already translated by the app. */
  optionLabels: Record<ThemePreference, string>;
  /** Styling stays in the app (Tailwind scans the app sources only). */
  className?: string;
  optionClassName: (checked: boolean) => string;
};

/**
 * Headless segmented switch day, evening, auto as an ARIA radio group: roving tab stop on the
 * checked option, arrow keys (and Home/End) move and select, as in the WAI-ARIA radio pattern.
 */
export function ThemeSwitch({ store, label, optionLabels, className = "", optionClassName }: ThemeSwitchProps) {
  const preference = useThemePreference(store);
  const refs = useRef<Partial<Record<ThemePreference, HTMLButtonElement | null>>>({});

  function select(value: ThemePreference, focus: boolean) {
    store.set(value);
    if (focus) refs.current[value]?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = THEME_PREFERENCES.length - 1;
    let next: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = index === last ? 0 : index + 1;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = index === 0 ? last : index - 1;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = last;
    if (next === null) return;
    event.preventDefault();
    const value = THEME_PREFERENCES[next];
    if (value) select(value, true);
  }

  return (
    <div role="radiogroup" aria-label={label} className={className}>
      {THEME_PREFERENCES.map((value, index) => {
        const checked = preference === value;
        return (
          <button
            key={value}
            ref={(element) => {
              refs.current[value] = element;
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            onClick={() => select(value, false)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={optionClassName(checked)}
          >
            {optionLabels[value]}
          </button>
        );
      })}
    </div>
  );
}
