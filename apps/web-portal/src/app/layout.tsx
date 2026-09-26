import type { Metadata, Viewport } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getTranslations } from "next-intl/server";

import { PwaRegister } from "@/components/shell/PwaRegister";

import "./globals.css";

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
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#2e2d2e" },
    { media: "(prefers-color-scheme: dark)", color: "#121212" },
  ],
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  return (
    <html lang={locale}>
      <body className="min-h-screen antialiased">
        <NextIntlClientProvider>{children}</NextIntlClientProvider>
        <PwaRegister />
      </body>
    </html>
  );
}
