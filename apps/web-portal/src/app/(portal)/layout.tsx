import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { LogoutButton } from "@/components/shell/LogoutButton";

/** Signed-in area of the portal: slim header, content, footer note. */
export default async function PortalLayout({ children }: { children: React.ReactNode }) {
  const [t, home] = await Promise.all([getTranslations("Portal"), getTranslations("Home")]);
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex w-full max-w-4xl items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-baseline gap-3">
            <Link href="/uebergabe" className="text-sm font-semibold">
              {home("productName")}
            </Link>
            <span className="mhvp-label">{t("title")}</span>
          </div>
          <LogoutButton />
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-5 px-4 py-6">{children}</main>
      <footer className="mx-auto w-full max-w-4xl px-4 py-4 text-xs text-subtle">{t("footer")}</footer>
    </div>
  );
}
