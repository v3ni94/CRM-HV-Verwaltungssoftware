"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

export type NavGroup = { label: string; items: { href: string; label: string }[] };

const STORAGE_KEY = "mhvp.nav.collapsed";

function readCollapsed(): Record<string, boolean> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, boolean>) : {};
  } catch {
    return {};
  }
}

function writeCollapsed(value: Record<string, boolean>) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    // ignore (private mode, blocked storage)
  }
}

/** Grouped main navigation with the active entry marked by a gold bar (CI "Goldpunkt").
 *  Renders as a sidebar on wide screens and as a scrollable row on small ones. Groups can be
 *  collapsed on the sidebar; the state is remembered per browser (localStorage). */
export function SideNav({ groups, label }: { groups: NavGroup[]; label: string }) {
  const pathname = usePathname();
  const search = useSearchParams();
  const current = search?.toString() ? `${pathname}?${search.toString()}` : pathname;
  const active = (href: string) =>
    href.includes("?") ? current === href : pathname === href || pathname.startsWith(`${href}/`);
  const hasActive = (g: NavGroup) => g.items.some((item) => active(item.href));

  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  useEffect(() => {
    setCollapsed(readCollapsed());
  }, []);

  function toggle(groupLabel: string) {
    setCollapsed((prev) => {
      const next = { ...prev, [groupLabel]: !prev[groupLabel] };
      writeCollapsed(next);
      return next;
    });
  }

  return (
    <nav aria-label={label} className="flex gap-1 overflow-x-auto px-2 py-2 md:flex-col md:gap-1 md:overflow-visible md:px-3 md:py-4">
      {groups.map((g) => {
        const isCollapsed = Boolean(collapsed[g.label]) && !hasActive(g);
        return (
          <div key={g.label} className="flex shrink-0 gap-1 md:flex-col md:mb-2">
            <button
              type="button"
              aria-expanded={!isCollapsed}
              onClick={() => toggle(g.label)}
              className="mhvp-label hidden w-full items-center justify-between gap-2 rounded-md px-3 pb-1 pt-2 text-left hover:text-fg md:flex"
            >
              <span>{g.label}</span>
              <svg
                aria-hidden="true"
                viewBox="0 0 20 20"
                className={`h-3 w-3 shrink-0 fill-current transition-transform ${isCollapsed ? "-rotate-90" : ""}`}
              >
                <path d="M5.5 7.5 10 12l4.5-4.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <span className="mhvp-label px-3 pb-1 md:hidden">{g.label}</span>
            {isCollapsed ? null : (
              <div className="flex shrink-0 gap-1 md:flex-col">
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
            )}
          </div>
        );
      })}
    </nav>
  );
}
