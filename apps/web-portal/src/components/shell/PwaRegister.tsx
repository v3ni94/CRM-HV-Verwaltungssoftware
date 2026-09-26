"use client";

import { useEffect } from "react";

/** Registers the service worker of the portal (A57). The worker caches only the static offline
 *  start page and its icons; no API response and no personal data is ever cached (see
 *  public/sw.js). Registration is skipped where service workers are unavailable. */
export function PwaRegister() {
  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      // Offline shell is a convenience only; the portal works without it.
    });
  }, []);
  return null;
}
