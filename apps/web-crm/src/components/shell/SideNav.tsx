"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ChevronIcon, navIcon } from "./icons";

export type NavItem = { href: string; label: string; icon?: string; external?: boolean };
export type NavGroup = { label: string; items: NavItem[] };

const STORAGE_KEY = "mhvp.nav.collapsed";
const RAIL_KEY = "mhvp.nav.rail.collapsed";

function readJSON<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJSON(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // ignore (private mode, blocked storage)
  }
}

function ItemIcon({ name }: { name?: string }) {
  const Icon = navIcon(name);
  return <Icon className="h-4.5 w-4.5 shrink-0" />;
}

/** The full sidebar rail: logo, grouped navigation and a collapse toggle. Renders as a calm
 *  dark anthracite rail on desktop (CI "Goldpunkt" gold active indicator) and as a horizontal
 *  scroller on small screens. Group collapse and the icon-only rail mode are both remembered
 *  per browser (localStorage); neither changes the routing or data of the pages themselves. */
export function SideNav({
  groups,
  label,
  logoSrc,
  productName,
  area,
  collapseLabel,
  expandLabel,
}: {
  groups: NavGroup[];
  label: string;
  logoSrc: string;
  productName: string;
  area: string;
  collapseLabel: string;
  expandLabel: string;
}) {
  const pathname = usePathname();
  const search = useSearchParams();
  const current = search?.toString() ? `${pathname}?${search.toString()}` : pathname;
  const active = (href: string) =>
    href.includes("?") ? current === href : pathname === href || pathname.startsWith(`${href}/`);
  const hasActive = (g: NavGroup) => g.items.some((item) => active(item.href));

  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [railCollapsed, setRailCollapsed] = useState(false);
  useEffect(() => {
    setCollapsed(readJSON(STORAGE_KEY, {}));
    setRailCollapsed(readJSON(RAIL_KEY, false));
  }, []);

  function toggleGroup(groupLabel: string) {
    setCollapsed((prev) => {
      const next = { ...prev, [groupLabel]: !prev[groupLabel] };
      writeJSON(STORAGE_KEY, next);
      return next;
    });
  }

  function toggleRail() {
    setRailCollapsed((prev) => {
      const next = !prev;
      writeJSON(RAIL_KEY, next);
      return next;
    });
  }

  return (
    <aside
      className={`flex flex-col border-b border-rail-border bg-rail-bg text-rail-fg md:sticky md:top-0 md:h-screen md:shrink-0 md:border-b-0 md:border-r md:transition-[width] md:duration-200 ${
        railCollapsed ? "md:w-[4.5rem]" : "md:w-64"
      }`}
    >
      <Link
        href="/start"
        className="flex items-center gap-3 border-b border-rail-border px-4 py-3 md:py-4"
      >
        <Image src={logoSrc} alt="" width={36} height={31} unoptimized priority className="h-8 w-auto shrink-0" />
        {railCollapsed ? null : (
          <span className="flex min-w-0 flex-col leading-tight">
            <span className="truncate text-sm font-semibold">{productName}</span>
            <span className="mhvp-label text-rail-muted">{area}</span>
          </span>
        )}
      </Link>
      <nav
        aria-label={label}
        className="flex flex-1 gap-1 overflow-x-auto px-2 py-2 md:flex-col md:gap-1 md:overflow-y-auto md:overflow-x-visible md:px-3 md:py-4"
      >
        {groups.map((g) => {
          const isCollapsed = Boolean(collapsed[g.label]) && !hasActive(g);
          return (
            <div key={g.label} className="flex shrink-0 gap-1 md:mb-2 md:flex-col">
              {railCollapsed ? (
                <span className="mhvp-label hidden px-1 pb-1 pt-2 text-rail-muted md:block" aria-hidden="true">
                  ·
                </span>
              ) : (
                <button
                  type="button"
                  aria-expanded={!isCollapsed}
                  onClick={() => toggleGroup(g.label)}
                  className="mhvp-label hidden w-full items-center justify-between gap-2 rounded-md px-3 pb-1 pt-2 text-left text-rail-muted transition duration-150 hover:text-rail-fg md:flex"
                >
                  <span>{g.label}</span>
                  <ChevronIcon className={`h-3 w-3 shrink-0 transition-transform duration-150 ${isCollapsed ? "-rotate-90" : ""}`} />
                </button>
              )}
              <span className="mhvp-label px-3 pb-1 text-rail-muted md:hidden">{g.label}</span>
              {isCollapsed ? null : (
                <div className="flex shrink-0 gap-1 md:flex-col">
                  {g.items.map((item) => {
                    const itemClass = `relative flex items-center gap-2.5 whitespace-nowrap rounded-md px-3 py-2 text-sm transition duration-150 ${
                      railCollapsed ? "md:justify-center md:px-2" : ""
                    } ${
                      !item.external && active(item.href)
                        ? "bg-rail-active font-medium text-rail-fg md:before:absolute md:before:bottom-2 md:before:left-0 md:before:top-2 md:before:w-0.5 md:before:rounded-full md:before:bg-gold"
                        : "text-rail-muted hover:bg-rail-hover hover:text-rail-fg"
                    }`;
                    const body = (
                      <>
                        <span className="hidden md:inline-flex">
                          <ItemIcon name={item.icon} />
                        </span>
                        <span className={railCollapsed ? "md:sr-only" : ""}>{item.label}</span>
                      </>
                    );
                    return item.external ? (
                      <a
                        key={item.href}
                        href={item.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={railCollapsed ? item.label : undefined}
                        className={itemClass}
                      >
                        {body}
                      </a>
                    ) : (
                      <Link
                        key={item.href}
                        href={item.href}
                        title={railCollapsed ? item.label : undefined}
                        aria-current={active(item.href) ? "page" : undefined}
                        className={itemClass}
                      >
                        {body}
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
      <button
        type="button"
        onClick={toggleRail}
        title={railCollapsed ? expandLabel : collapseLabel}
        aria-pressed={railCollapsed}
        className="hidden items-center justify-center gap-2 border-t border-rail-border px-3 py-3 text-xs font-medium text-rail-muted transition duration-150 hover:bg-rail-hover hover:text-rail-fg md:flex"
      >
        <ChevronIcon className={`h-3.5 w-3.5 transition-transform duration-150 ${railCollapsed ? "rotate-180" : ""}`} />
        {railCollapsed ? null : <span>{collapseLabel}</span>}
      </button>
    </aside>
  );
}
