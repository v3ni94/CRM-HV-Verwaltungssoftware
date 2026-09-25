import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { LogoutButton } from "./LogoutButton";

export type NavItem = { href: string; label: string };

/** Simple top bar: portal name, horizontal navigation (scrollable on phones), sign out. */
export async function Topbar({ items }: { items: NavItem[] }) {
  const t = await getTranslations("Shell");
  return (
    <header className="border-b border-border bg-bg">
      <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <Link href="/" className="shrink-0">
          <span className="mhvp-label">{t("portalName")}</span>
        </Link>
        <nav
          aria-label={t("menu")}
          className="order-last -mx-4 flex w-[calc(100%+2rem)] gap-1 overflow-x-auto px-4 sm:order-none sm:mx-0 sm:w-auto sm:flex-1 sm:px-0"
        >
          {items.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm font-medium text-muted transition hover:bg-surface hover:text-fg"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto shrink-0">
          <LogoutButton label={t("logout")} />
        </div>
      </div>
    </header>
  );
}
