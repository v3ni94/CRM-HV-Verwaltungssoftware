"use client";

import { useEffect } from "react";

import { installThemeColorMeta } from "@/lib/theme";

/** Registers the service worker of the CRM shell (M31 WP5, M30-08) and keeps the browser
 *  chrome colour in step with the day and evening theme. The worker caches only the static
 *  offline page and the icons; no API response, page or document is ever cached (see
 *  public/sw.js and ADR 0017). Registration is skipped where service workers are unavailable. */
export function PwaRegister() {
  useEffect(() => installThemeColorMeta(), []);
  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      // The offline shell is a convenience only; the CRM works without it.
    });
  }, []);
  return null;
}
