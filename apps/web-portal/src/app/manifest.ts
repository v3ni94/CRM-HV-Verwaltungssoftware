import type { MetadataRoute } from "next";

// PWA manifest of the portal (A57). Colours are the light tokens of @mhvp/ui (bg #ffffff,
// accent #2e2d2e); tenant branding replaces them at runtime (V14). Icons are the existing
// brand asset of the product owner padded to a square (public/icons), no invented logo.
// The service worker (public/sw.js) caches only the static offline page.
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
    background_color: "#ffffff",
    theme_color: "#2e2d2e",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
    ],
  };
}
