"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

import { ChevronIcon, MenuIcon, navIcon } from "./icons";

export type NavItem = { href: string; label: string; icon?: string };
export type NavGroup = { label: string; items: NavItem[] };

/** Rail modes (M31): `auto` renders the icon rail from `lg` and the full rail from `xl` purely
 *  by CSS (no matchMedia, no jump after hydration); `expanded` and `collapsed` are manual
 *  overrides stored per browser. */
export type RailMode = "auto" | "expanded" | "collapsed";

const STORAGE_KEY = "mhvp.nav.collapsed";
const RAIL_KEY = "mhvp.nav.rail.collapsed";
const PREFERENCES_ENDPOINT = "/api/bff/auth/me/preferences";
const SAVE_DEBOUNCE_MS = 500;

/** Window event that opens the navigation drawer (`MobileNav`) from elsewhere, for example
 *  from the head of the icon rail between `lg` and `xl`. */
export const OPEN_NAV_EVENT = "mhvp:open-nav";

export function openNavDrawer() {
  try {
    window.dispatchEvent(new Event(OPEN_NAV_EVENT));
  } catch {
    /* no window (server) */
  }
}

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

/** Tolerant parser of the stored rail mode: the boolean of versions up to 1.42 maps to the
 *  manual modes (true = collapsed, false = expanded), the three strings pass through, anything
 *  else (missing, unknown) is `auto`. */
export function parseRailMode(value: unknown): RailMode {
  if (value === true || value === "collapsed") return "collapsed";
  if (value === false || value === "expanded") return "expanded";
  return "auto";
}

function writeJSON(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // ignore (private mode, blocked storage)
  }
}

export function ItemIcon({ name }: { name?: string }) {
  const Icon = navIcon(name);
  return <Icon className="h-4.5 w-4.5 shrink-0" />;
}

/** Active check of a navigation entry: an entry with a query string (for example
 *  `/objekte?art=rental`) matches only the exact path plus query, a plain entry matches its
 *  path and every sub path. Shared by the rail and the drawer. */
export function useActiveHref() {
  const pathname = usePathname();
  const search = useSearchParams();
  const query = search?.toString() ?? "";
  const current = query ? `${pathname}?${query}` : pathname;
  const active = (href: string) => (href.includes("?") ? current === href : pathname === href || pathname.startsWith(`${href}/`));
  const hasActive = (g: NavGroup) => g.items.some((item) => active(item.href));
  return { active, hasActive };
}

type GroupState = Record<string, boolean>;

function fromList(list: string[]): GroupState {
  return Object.fromEntries(list.map((l) => [l, true]));
}

/** One module level store for the group expand state, read by the rail and the drawer through
 *  `useSyncExternalStore`. Both are mounted at the same time (the rail is only hidden by CSS
 *  below `lg`, the drawer keeps its hook while closed), so two `useState` copies diverged and
 *  overwrote each other's `PATCH nav_expanded_groups` with a stale list (review after M31
 *  WP1). One state, one debounce timer, one PATCH. The store empties itself when the last
 *  subscriber unmounts (next layout mount or test starts fresh from the server value). */
const navGroupStore: {
  state: GroupState | null;
  server: GroupState | null;
  listeners: Set<() => void>;
  timer: ReturnType<typeof setTimeout> | null;
} = { state: null, server: null, listeners: new Set(), timer: null };

function subscribeNavGroups(listener: () => void) {
  navGroupStore.listeners.add(listener);
  return () => {
    navGroupStore.listeners.delete(listener);
    if (navGroupStore.listeners.size === 0) {
      navGroupStore.state = null;
      navGroupStore.server = null;
    }
  };
}

function setNavGroups(next: GroupState) {
  navGroupStore.state = next;
  navGroupStore.listeners.forEach((listener) => listener());
}

function persistNavGroups(next: GroupState) {
  const groupLabels = Object.entries(next)
    .filter(([, on]) => on)
    .map(([l]) => l);
  writeJSON(STORAGE_KEY, groupLabels);
  if (navGroupStore.timer) clearTimeout(navGroupStore.timer);
  navGroupStore.timer = setTimeout(() => {
    navGroupStore.timer = null;
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

/** Group expand state, server side per user (operator 27.09.2026: all groups start collapsed,
 *  an opened group stays open until closed again, on every device) and mirrored into
 *  localStorage only to avoid a flash while the save round trip is in flight. Shared by the
 *  rail and the drawer through one store, so a group opened in the drawer is open in the rail
 *  and both send the same `PATCH nav_expanded_groups`. `initialExpandedGroups` is the server
 *  value of the first mount; undefined (not logged in yet) falls back to localStorage, then
 *  all closed. */
export function useNavGroups(initialExpandedGroups: string[] | undefined) {
  const expanded = useSyncExternalStore(
    subscribeNavGroups,
    () => {
      if (navGroupStore.state === null) {
        navGroupStore.state = fromList(initialExpandedGroups !== undefined ? asGroupList(initialExpandedGroups) : readGroupList(STORAGE_KEY));
      }
      return navGroupStore.state;
    },
    () => {
      // Server render and hydration: never read localStorage here, the client snapshot above
      // takes over right after hydration without a markup mismatch.
      if (navGroupStore.server === null) navGroupStore.server = fromList(initialExpandedGroups !== undefined ? asGroupList(initialExpandedGroups) : []);
      return navGroupStore.server;
    },
  );

  function toggleGroup(groupLabel: string) {
    const prev = navGroupStore.state ?? expanded;
    const next = { ...prev, [groupLabel]: !prev[groupLabel] };
    persistNavGroups(next);
    setNavGroups(next);
  }

  function collapseAll() {
    const next: GroupState = {};
    persistNavGroups(next);
    setNavGroups(next);
  }

  return { expanded, toggleGroup, collapseAll };
}

const RAIL_WIDTH: Record<RailMode, string> = {
  auto: "lg:w-[4.5rem] xl:w-64",
  expanded: "lg:w-64",
  collapsed: "lg:w-[4.5rem]",
};
/** Text next to an icon: hidden in the icon rail, visible in the full rail. */
const LABEL: Record<RailMode, string> = {
  auto: "lg:sr-only xl:not-sr-only",
  expanded: "",
  collapsed: "lg:sr-only",
};
/** Blocks that exist only in the full rail (product name, group buttons, collapse all). */
const FULL_ONLY: Record<RailMode, string> = {
  auto: "hidden xl:flex",
  expanded: "flex",
  collapsed: "hidden",
};
/** Blocks that exist only in the icon rail (group marker, drawer button). */
const ICON_ONLY: Record<RailMode, string> = {
  auto: "lg:flex xl:hidden",
  expanded: "hidden",
  collapsed: "lg:flex",
};
const ITEM_ALIGN: Record<RailMode, string> = {
  auto: "lg:justify-center lg:px-2 xl:justify-start xl:px-3",
  expanded: "",
  collapsed: "lg:justify-center lg:px-2",
};
const NEXT_MODE: Record<RailMode, RailMode> = { auto: "collapsed", collapsed: "expanded", expanded: "auto" };

/** The desktop rail: logo, grouped navigation and a mode toggle. Hidden below `lg` (the
 *  drawer of `MobileNav` serves phones and tablets), an icon rail of 4.5 rem from `lg` and the
 *  full rail of 16 rem from `xl` (M31, day: white with a soft accent tint on the active item;
 *  evening: near black with the active item in accent gold, 1.37 redesign). The icon rail
 *  carries a 44 px button that opens the drawer with all groups. The rail mode stays a per
 *  browser preference (localStorage, the only stored shell flag) and is announced as
 *  `data-rail` on `html` so a fixed bottom bar can follow the edge. */
export function SideNav({
  groups,
  label,
  logoSrc,
  productName,
  area,
  collapseLabel,
  expandLabel,
  autoLabel,
  openNavLabel,
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
  /** Label of the toggle when the next mode is `auto`; falls back to `expandLabel`. */
  autoLabel?: string;
  /** Label of the drawer button in the icon rail; falls back to `label`. */
  openNavLabel?: string;
  /** Group labels the signed in user last had open (from `GET /auth/me`, see `useNavGroups`).
   *  Undefined (not logged in yet) falls back to localStorage, then all closed. */
  initialExpandedGroups?: string[];
  collapseAllLabel?: string;
}) {
  const { active, hasActive } = useActiveHref();
  const { expanded, toggleGroup, collapseAll } = useNavGroups(initialExpandedGroups);
  const [mode, setMode] = useState<RailMode>("auto");
  useEffect(() => {
    setMode(parseRailMode(readJSON<unknown>(RAIL_KEY, null)));
  }, []);
  useEffect(() => {
    if (mode === "auto") delete document.documentElement.dataset.rail;
    else document.documentElement.dataset.rail = mode;
    return () => {
      delete document.documentElement.dataset.rail;
    };
  }, [mode]);

  function cycleMode() {
    setMode((prev) => {
      const next = NEXT_MODE[prev];
      writeJSON(RAIL_KEY, next);
      return next;
    });
  }

  const toggleLabel = { auto: collapseLabel, collapsed: expandLabel, expanded: autoLabel ?? expandLabel }[mode];

  return (
    <aside
      data-rail-mode={mode}
      className={`hidden flex-col bg-rail-bg text-rail-fg lg:sticky lg:top-0 lg:flex lg:h-dvh lg:shrink-0 lg:border-r lg:border-rail-border lg:transition-[width] lg:duration-200 ${RAIL_WIDTH[mode]}`}
    >
      <div className={`flex items-center gap-2 border-b border-rail-border px-3 py-3 ${mode === "auto" ? "lg:flex-col xl:flex-row xl:gap-3 xl:px-4 xl:py-4" : mode === "collapsed" ? "lg:flex-col" : "gap-3 px-4 py-4"}`}>
        <Link href="/start" className="flex min-w-0 items-center gap-3">
          <Image src={logoSrc} alt="" width={36} height={31} unoptimized priority className="mhvp-logo h-8 w-auto shrink-0" />
          <span className={`${FULL_ONLY[mode]} min-w-0 flex-col leading-tight`}>
            <span className="truncate text-sm font-semibold">{productName}</span>
            <span className="mhvp-label text-rail-muted">{area}</span>
          </span>
        </Link>
        <button
          type="button"
          aria-label={openNavLabel ?? label}
          onClick={openNavDrawer}
          data-testid="rail-open-nav"
          className={`${ICON_ONLY[mode]} h-11 w-11 shrink-0 items-center justify-center rounded-md text-rail-muted transition duration-150 hover:bg-rail-hover hover:text-rail-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-focus`}
        >
          <MenuIcon className="h-5 w-5" />
        </button>
      </div>
      <nav aria-label={label} className="flex flex-1 flex-col gap-1 overflow-y-auto px-3 py-4">
        {groups.map((g) => {
          const isCollapsed = !expanded[g.label] && !hasActive(g);
          return (
            <div key={g.label} className="mb-2 flex shrink-0 flex-col gap-1">
              <span className={`${ICON_ONLY[mode]} mhvp-label px-1 pb-1 pt-2 text-rail-muted`} aria-hidden="true">
                ·
              </span>
              <button
                type="button"
                aria-expanded={!isCollapsed}
                onClick={() => toggleGroup(g.label)}
                className={`${FULL_ONLY[mode]} mhvp-label min-h-11 w-full items-center pointer-fine:min-h-0 justify-between gap-2 rounded-md px-3 pb-1 pt-2 text-left text-rail-muted transition duration-150 hover:text-rail-fg`}
              >
                <span>{g.label}</span>
                <ChevronIcon className={`h-3 w-3 shrink-0 transition-transform duration-150 ${isCollapsed ? "-rotate-90" : ""}`} />
              </button>
              {isCollapsed ? null : (
                <div className="flex shrink-0 flex-col gap-1">
                  {g.items.map((item) => (
                    <Link
                      key={item.href}
                      href={item.href}
                      title={mode === "collapsed" ? item.label : undefined}
                      aria-current={active(item.href) ? "page" : undefined}
                      className={`relative flex min-h-11 items-center gap-2.5 whitespace-nowrap rounded-md px-3 py-2 text-sm transition duration-150 ${ITEM_ALIGN[mode]} ${
                        active(item.href) ? "bg-rail-active font-semibold text-rail-active-fg" : "text-rail-fg hover:bg-rail-hover hover:text-fg"
                      }`}
                    >
                      <span className="inline-flex">
                        <ItemIcon name={item.icon} />
                      </span>
                      <span className={LABEL[mode]}>{item.label}</span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </nav>
      {collapseAllLabel ? (
        <button
          type="button"
          onClick={collapseAll}
          className={`${FULL_ONLY[mode]} min-h-11 items-center justify-center gap-2 border-t pointer-fine:min-h-0 border-rail-border px-3 py-2 text-xs font-medium text-rail-muted transition duration-150 hover:bg-rail-hover hover:text-rail-fg`}
        >
          {collapseAllLabel}
        </button>
      ) : null}
      <button
        type="button"
        onClick={cycleMode}
        title={toggleLabel}
        aria-label={toggleLabel}
        aria-pressed={mode === "collapsed"}
        data-testid="rail-mode"
        className="hidden min-h-11 items-center justify-center gap-2 border-t border-rail-border px-3 py-3 text-xs font-medium text-rail-muted transition duration-150 pointer-fine:min-h-0 hover:bg-rail-hover hover:text-rail-fg lg:flex"
      >
        <ChevronIcon className={`h-3.5 w-3.5 transition-transform duration-150 ${mode === "collapsed" ? "rotate-180" : mode === "auto" ? "lg:rotate-180 xl:rotate-0" : ""}`} />
        <span className={LABEL[mode]}>{toggleLabel}</span>
      </button>
    </aside>
  );
}
