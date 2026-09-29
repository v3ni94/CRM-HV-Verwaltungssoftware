import type { MetadataRoute } from "next";

// PWA manifest of the portal (A57, M31 WP5). Colours are a hex copy of the day tokens of
// packages/ui/src/tokens.css (manifest.ts reads no CSS): background_color = --mhvp-color-bg
// #f6f5f2, theme_color = --mhvp-color-surface-2 #faf9f7 (header surface, same value as the
// light theme colour of the root layout). Tenant branding replaces the accent at runtime (V14).
// Icons are the existing brand asset of the product owner padded to a square (public/icons),
// the maskable variant with the safe zone margin, no invented logo. The service worker
// (public/sw.js) caches only the static offline page and the icons.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "MH Portal",
    short_name: "MH Portal",
    description: "Portal der MH Verwaltungsplattform für Mieter, Eigentümer und Dienstleister",
    id: "/start",
    lang: "de",
    start_url: "/start",
    scope: "/",
    display: "standalone",
    background_color: "#f6f5f2",
    theme_color: "#faf9f7",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512-maskable.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Übergabeprotokoll", url: "/uebergabe", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Meldung", url: "/meldungen", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
    ],
  };
}
