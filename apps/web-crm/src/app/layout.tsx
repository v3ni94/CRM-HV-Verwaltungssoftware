import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { headers } from "next/headers";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getTranslations } from "next-intl/server";

import { MaintenanceBanner } from "@/components/shell/MaintenanceBanner";
import { NONCE_HEADER } from "@/lib/csp";
import { THEME_SCRIPT } from "@/lib/theme";

import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Metadata");
  return {
    title: t("title"),
    description: t("description"),
    // Installable shell (M31 WP5, M30-08): manifest link and home screen title; the icons of
    // the home screen come from the manifest, the touch icon stays for older Safari versions.
    manifest: "/manifest.webmanifest",
    appleWebApp: { capable: true, title: "MHVP", statusBarStyle: "default" },
    icons: {
      icon: [{ url: "/favicon.png", type: "image/png" }],
      apple: [{ url: "/apple-touch-icon.png" }],
    },
  };
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  // GAH-303: nonce of this request from the middleware (CSP without script unsafe-inline).
  const nonce = (await headers()).get(NONCE_HEADER) ?? undefined;
  return (
    <html lang={locale} className={inter.variable} suppressHydrationWarning>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body
        className="min-h-screen antialiased"
        /* Top safe area is handled by the sticky app header itself (M31); left and right stay. */
        style={{
          paddingLeft: "env(safe-area-inset-left)",
          paddingRight: "env(safe-area-inset-right)",
        }}
      >
        <NextIntlClientProvider>
          <MaintenanceBanner />
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
