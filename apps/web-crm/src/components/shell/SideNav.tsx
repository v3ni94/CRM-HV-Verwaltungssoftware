"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ChevronIcon, navIcon } from "./icons";

export type NavItem = { href: string; label: string; icon?: string };
export type NavGroup = { label: string; items: NavItem[] };

const STORAGE_KEY = "mhvp.nav.collapsed";
const RAIL_KEY = "mhvp.nav.rail.collapsed";
const PREFERENCES_ENDPOINT = "/api/bff/auth/me/preferences";
const SAVE_DEBOUNCE_MS = 500;

function readJSON<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

/** Open menu groups as a list of labels. Versions up to 1.34.x stored an object under the same
 *  key (label -> collapsed); any value that is not an array of strings is ignored instead of
 *  crashing the whole layout (production incident 27.09.2026, 1.35.1). */
function asGroupList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

function readGroupList(key: string): string[] {
  return asGroupList(readJSON<unknown>(key, []));
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
 *  rail on desktop (day: white with a soft accent tint on the active item; evening: near black
 *  with the active item in accent gold, 1.37 redesign) and as a horizontal scroller on small
 *  screens. Group expand state is server side per user (operator 27.09.2026:
 *  all groups start collapsed, an opened group stays open until closed again, on every device)
 *  and mirrored into localStorage only to avoid a flash while the save round trip is in flight.
 *  The icon-only rail mode stays a per-browser preference (localStorage). Neither changes the
 *  routing or data of the pages themselves. */
export function SideNav({
  groups,
  label,
  logoSrc,
  productName,
  area,
  collapseLabel,
  expandLabel,
  initialExpandedGroups,
  collapseAllLabel,
}: {
  groups: NavGroup[];
  label: string;
  logoSrc: string;
  productName: string;
  area: string;
  collapseLabel: string;
  expandLabel: string;
  /** Group labels the signed in user last had open (from `GET /auth/me`, section see SideNav
   *  doc comment). Undefined (not logged in yet) falls back to localStorage, then all closed. */
  initialExpandedGroups?: string[];
  collapseAllLabel?: string;
}) {
  const pathname = usePathname();
  const search = useSearchParams();
  const current = search?.toString() ? `${pathname}?${search.toString()}` : pathname;
  const active = (href: string) =>
    href.includes("?") ? current === href : pathname === href || pathname.startsWith(`${href}/`);
  const hasActive = (g: NavGroup) => g.items.some((item) => active(item.href));

  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    const initial =
      initialExpandedGroups !== undefined ? asGroupList(initialExpandedGroups) : readGroupList(STORAGE_KEY);
    return Object.fromEntries(initial.map((l) => [l, true]));
  });
  const [railCollapsed, setRailCollapsed] = useState(false);
  const saveTimer = useState<{ current: ReturnType<typeof setTimeout> | null }>(() => ({
    current: null,
  }))[0];
  useEffect(() => {
    if (initialExpandedGroups === undefined) {
      setExpanded(Object.fromEntries(readGroupList(STORAGE_KEY).map((l) => [l, true])));
    }
    setRailCollapsed(readJSON<unknown>(RAIL_KEY, false) === true);
    // Only on mount: initialExpandedGroups is the server value for this render and must not be
    // re-applied after the user has toggled a group.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function persist(next: Record<string, boolean>) {
    const groupLabels = Object.entries(next)
      .filter(([, on]) => on)
      .map(([l]) => l);
    writeJSON(STORAGE_KEY, groupLabels);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      fetch(PREFERENCES_ENDPOINT, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ nav_expanded_groups: groupLabels }),
      }).catch(() => {
        // offline or session expired: localStorage above still keeps this browser consistent
      });
    }, SAVE_DEBOUNCE_MS);
  }

  function toggleGroup(groupLabel: string) {
    setExpanded((prev) => {
      const next = { ...prev, [groupLabel]: !prev[groupLabel] };
      persist(next);
      return next;
    });
  }

  function collapseAll() {
    setExpanded(() => {
      const next: Record<string, boolean> = {};
      persist(next);
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
      className={`hidden flex-col bg-rail-bg text-rail-fg md:sticky md:top-0 md:flex md:h-screen md:shrink-0 md:border-r md:border-rail-border md:transition-[width] md:duration-200 ${
        railCollapsed ? "md:w-[4.5rem]" : "md:w-64"
      }`}
    >
      <Link
        href="/start"
        className="flex items-center gap-3 border-b border-rail-border px-4 py-3 md:py-4"
      >
        <Image src={logoSrc} alt="" width={36} height={31} unoptimized priority className="mhvp-logo h-8 w-auto shrink-0" />
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
          const isCollapsed = !expanded[g.label] && !hasActive(g);
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
                  {g.items.map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      title={railCollapsed ? item.label : undefined}
                      aria-current={active(item.href) ? "page" : undefined}
                      className={`relative flex min-h-11 items-center gap-2.5 whitespace-nowrap rounded-md px-3 py-2 text-sm transition duration-150 ${
                        railCollapsed ? "md:justify-center md:px-2" : ""
                      } ${
                        active(item.href)
                          ? "bg-rail-active font-semibold text-rail-active-fg"
                          : "text-rail-fg hover:bg-rail-hover hover:text-fg"
                      }`}
                    >
                      <span className="hidden md:inline-flex">
                        <ItemIcon name={item.icon} />
                      </span>
                      <span className={railCollapsed ? "md:sr-only" : ""}>{item.label}</span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </nav>
      {collapseAllLabel && !railCollapsed ? (
        <button
          type="button"
          onClick={collapseAll}
          className="hidden items-center justify-center gap-2 border-t border-rail-border px-3 py-2 text-xs font-medium text-rail-muted transition duration-150 hover:bg-rail-hover hover:text-rail-fg md:flex"
        >
          {collapseAllLabel}
        </button>
      ) : null}
      <button
        type="button"
        onClick={toggleRail}
        title={railCollapsed ? expandLabel : collapseLabel}
        aria-label={railCollapsed ? expandLabel : collapseLabel}
        aria-pressed={railCollapsed}
        className="hidden items-center justify-center gap-2 border-t border-rail-border px-3 py-3 text-xs font-medium text-rail-muted transition duration-150 hover:bg-rail-hover hover:text-rail-fg md:flex"
      >
        <ChevronIcon className={`h-3.5 w-3.5 transition-transform duration-150 ${railCollapsed ? "rotate-180" : ""}`} />
        {railCollapsed ? null : <span>{collapseLabel}</span>}
      </button>
    </aside>
  );
}
