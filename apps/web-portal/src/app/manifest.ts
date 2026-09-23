import type { MetadataRoute } from "next";

// PWA manifest only; no service worker in M1. Colors are the neutral light tokens
// (tenant branding from /api/v1/tenant/branding replaces them in M2, V14).
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "MH Verwaltungsplattform Portal",
    short_name: "MHVP Portal",
    description: "Portal der MH Verwaltungsplattform",
    lang: "de",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#ffffff",
  };
}
