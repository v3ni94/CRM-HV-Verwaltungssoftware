"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

export type NavGroup = { label: string; items: { href: string; label: string }[] };

/** Grouped main navigation with the active entry marked by a gold bar (CI "Goldpunkt").
 *  Renders as a sidebar on wide screens and as a scrollable row on small ones. */
export function SideNav({ groups, label }: { groups: NavGroup[]; label: string }) {
  const pathname = usePathname();
  const search = useSearchParams();
  const current = search?.toString() ? `${pathname}?${search.toString()}` : pathname;
  const active = (href: string) =>
    href.includes("?") ? current === href : pathname === href || pathname.startsWith(`${href}/`);
  return (
    <nav aria-label={label} className="flex gap-1 overflow-x-auto px-2 py-2 md:flex-col md:gap-5 md:overflow-visible md:px-3 md:py-4">
      {groups.map((g) => (
        <div key={g.label} className="flex shrink-0 gap-1 md:flex-col">
          <span className="mhvp-label hidden px-3 pb-1 md:block">{g.label}</span>
          {g.items.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active(item.href) ? "page" : undefined}
              className={`relative whitespace-nowrap rounded-md px-3 py-1.5 text-sm transition md:py-2 ${
                active(item.href)
                  ? "bg-surface font-medium text-fg md:before:absolute md:before:left-0 md:before:top-2 md:before:bottom-2 md:before:w-0.5 md:before:rounded-full md:before:bg-gold"
                  : "text-muted hover:bg-surface hover:text-fg"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </div>
      ))}
    </nav>
  );
}
