import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getTranslations } from "next-intl/server";

import { PwaRegister } from "@/components/shell/PwaRegister";
import { ThemeController } from "@/components/shell/ThemeToggle";
import { PORTAL_THEME_SCRIPT } from "@/lib/theme";

import "./globals.css";

// Variable UI font, self hosted by next/font (no external CSS); tokens.css reads --font-inter.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Metadata");
  return {
    title: t("title"),
    description: t("description"),
    // PWA (A57): manifest link and home screen title; icons come from the manifest.
    manifest: "/manifest.webmanifest",
    appleWebApp: { capable: true, title: "MH Portal", statusBarStyle: "default" },
  };
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Installed app: content may extend under the notch; the body keeps the side insets and the
  // footer the bottom inset (M31 WP5, same as the CRM root layout).
  viewportFit: "cover",
  // Browser chrome follows the header surface (surface-2 of tokens.css) of the matching mode.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf9f7" },
    { media: "(prefers-color-scheme: dark)", color: "#1c2028" },
  ],
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  return (
    // data-theme is set by the inline script before the first paint, hence suppressHydrationWarning.
    <html lang={locale} className={inter.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: PORTAL_THEME_SCRIPT }} />
      </head>
      <body
        className="min-h-screen antialiased"
        style={{
          paddingLeft: "env(safe-area-inset-left)",
          paddingRight: "env(safe-area-inset-right)",
        }}
      >
        <NextIntlClientProvider>{children}</NextIntlClientProvider>
        <ThemeController />
        <PwaRegister />
      </body>
    </html>
  );
}
