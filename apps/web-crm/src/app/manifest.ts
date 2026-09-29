import type { MetadataRoute } from "next";

// Web app manifest of the CRM (M31 WP5, operator decision M30-08 of 28.09.2026, ADR 0017):
// the CRM is installable as a shell without any data cache. Colours are a hex copy of the day
// tokens of packages/ui/src/tokens.css because manifest.ts reads no CSS: background_color and
// theme_color = --mhvp-color-bg #f6f5f2 (the header of the app shell sits on bg). The evening
// theme colour is set at runtime by src/lib/theme.ts (meta name="theme-color"). Icons are the
// existing brand mark (public/marke-mhag.png) on that ground, the maskable variant with the
// safe zone margin; no invented logo. The service worker (public/sw.js) caches only the
// offline page and these icons.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "MH Verwaltungsplattform",
    short_name: "MHVP",
    description: "Verwaltungsplattform der Müller Holding AG (Hausverwaltung, WEG, Vermietung)",
    id: "/start",
    lang: "de",
    start_url: "/start",
    scope: "/",
    display: "standalone",
    background_color: "#f6f5f2",
    theme_color: "#f6f5f2",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512-maskable.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Übergabeprotokolle", url: "/makler/uebergabe", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Kalender", url: "/kalender", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Tickets", url: "/tickets", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
    ],
  };
}
