"use client";

import { useEffect, useState } from "react";

/** Phone: below the Tailwind `sm` breakpoint (640 px). */
export const PHONE = "(max-width: 639.98px)";
/** Tablet: `sm` up to below `lg` (640 to 1023 px); the drawer replaces the rail here. */
export const TABLET = "(min-width: 640px) and (max-width: 1023.98px)";
/** Coarse pointer (touch) regardless of width; mirrors the `pointer-coarse` variant. */
export const COARSE_POINTER = "(pointer: coarse)";

/** SSR safe media query hook: `false` on the server and on the first client render (no
 *  hydration mismatch), then the live value of `window.matchMedia`. A missing or throwing
 *  `matchMedia` (some test environments) yields `false` instead of a crash. Layout that must
 *  be right on the first paint belongs in CSS variants, not here. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    let mql: MediaQueryList | null = null;
    try {
      mql = window.matchMedia(query);
    } catch {
      /* matchMedia unavailable: keep false, no crash */
    }
    if (!mql) return;
    const list = mql;
    const update = () => setMatches(list.matches);
    update();
    if (typeof list.addEventListener === "function") {
      list.addEventListener("change", update);
      return () => list.removeEventListener("change", update);
    }
    list.addListener(update);
    return () => list.removeListener(update);
  }, [query]);
  return matches;
}
