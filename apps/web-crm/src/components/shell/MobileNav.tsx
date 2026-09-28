"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { ChevronIcon, CloseIcon, MenuIcon } from "./icons";
import { ItemIcon, OPEN_NAV_EVENT, useActiveHref, useNavGroups, type NavGroup } from "./SideNav";
import { TenantSwitcher } from "./TenantSwitcher";

const FOCUSABLE = "a[href], button:not([disabled]), select:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex='-1'])";

export type NavDrawerProps = {
  open: boolean;
  onClose: () => void;
  groups: NavGroup[];
  /** Group labels the signed in user last had open (`GET /auth/me`); same rule as the rail. */
  initialExpandedGroups?: string[];
  tenants?: { id: string; name: string }[];
  currentTenant?: string | null;
  /** Accessible name of the drawer and its nav. */
  label: string;
  closeLabel: string;
  productName: string;
  area: string;
};

/**
 * Navigation drawer (M31): the same grouped links as the rail with icons, the same group
 * expand state and the same `PATCH /api/bff/auth/me/preferences` (`nav_expanded_groups`)
 * via `useNavGroups`, the same active check (query aware) via `useActiveHref`. Focus moves to
 * the close button on open, Tab stays inside the panel and focus returns to the element that
 * opened the drawer. A tenant switcher sits under the head when the user has more than one
 * tenant. `z-[99]` scrim and `z-[100]` panel, above every sheet.
 */
export function NavDrawer({ open, onClose, groups, initialExpandedGroups, tenants = [], currentTenant = null, label, closeLabel, productName, area }: NavDrawerProps) {
  const { active, hasActive } = useActiveHref();
  const { expanded, toggleGroup } = useNavGroups(initialExpandedGroups);
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    openerRef.current = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    return () => {
      const opener = openerRef.current;
      openerRef.current = null;
      if (opener && opener.isConnected) opener.focus();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onCloseRef.current();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  function trapTab(e: React.KeyboardEvent) {
    if (e.key !== "Tab" || !panelRef.current) return;
    const nodes = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (nodes.length === 0) return;
    const first = nodes[0]!;
    const last = nodes[nodes.length - 1]!;
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  if (!open || typeof document === "undefined") return null;

  // Portal: the sticky header uses backdrop blur, which would trap a fixed drawer inside it.
  return createPortal(
    <div className="fixed inset-0 z-[99]">
      <div className="fixed inset-0 z-[99] bg-scrim" aria-hidden="true" onClick={() => onCloseRef.current()} />
      <div
        id="mobile-nav-drawer"
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        onKeyDown={trapTab}
        className="fixed inset-y-0 left-0 z-[100] flex h-full w-72 max-w-[85vw] flex-col overflow-y-auto bg-rail-bg text-rail-fg shadow-lg"
        style={{
          paddingTop: "env(safe-area-inset-top)",
          paddingBottom: "env(safe-area-inset-bottom)",
          paddingLeft: "env(safe-area-inset-left)",
        }}
      >
        <div className="flex items-center justify-between gap-3 border-b border-rail-border px-4 py-3">
          <span className="flex min-w-0 flex-col leading-tight">
            <span className="truncate text-sm font-semibold">{productName}</span>
            <span className="mhvp-label text-rail-muted">{area}</span>
          </span>
          <button
            ref={closeRef}
            type="button"
            aria-label={closeLabel}
            onClick={() => onCloseRef.current()}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-rail-muted transition duration-150 hover:bg-rail-hover hover:text-rail-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            <CloseIcon className="h-5 w-5" />
          </button>
        </div>
        {tenants.length > 1 ? (
          <div className="border-b border-rail-border px-4 py-3" data-testid="drawer-tenant">
            <TenantSwitcher tenants={tenants} current={currentTenant} variant="drawer" />
          </div>
        ) : null}
        <nav aria-label={label} className="flex flex-1 flex-col gap-1 px-2 py-3">
          {groups.map((g) => {
            const isCollapsed = !expanded[g.label] && !hasActive(g);
            return (
              <div key={g.label} className="flex flex-col gap-1 pb-2">
                <button
                  type="button"
                  aria-expanded={!isCollapsed}
                  onClick={() => toggleGroup(g.label)}
                  className="mhvp-label flex min-h-11 w-full items-center justify-between gap-2 rounded-md px-3 text-left text-rail-muted transition duration-150 hover:text-rail-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
                >
                  <span>{g.label}</span>
                  <ChevronIcon className={`h-3 w-3 shrink-0 transition-transform duration-150 ${isCollapsed ? "-rotate-90" : ""}`} />
                </button>
                {isCollapsed
                  ? null
                  : g.items.map((item) => (
                      <Link
                        key={item.href}
                        href={item.href}
                        aria-current={active(item.href) ? "page" : undefined}
                        className={`flex min-h-11 items-center gap-2.5 rounded-md px-3 py-2 text-sm transition duration-150 ${
                          active(item.href) ? "bg-rail-active font-semibold text-rail-active-fg" : "text-rail-fg hover:bg-rail-hover hover:text-fg"
                        }`}
                      >
                        <ItemIcon name={item.icon} />
                        {item.label}
                      </Link>
                    ))}
              </div>
            );
          })}
        </nav>
      </div>
    </div>,
    document.body,
  );
}

/** Hamburger in the top bar (below `lg`) that opens the `NavDrawer`. The drawer also opens on
 *  the window event `OPEN_NAV_EVENT`, sent by the icon rail between `lg` and `xl`, so the
 *  drawer itself has no breakpoint class. Closes on route change. */
export function MobileNav({
  groups,
  label,
  openLabel,
  closeLabel,
  productName,
  area,
  initialExpandedGroups,
  tenants,
  currentTenant,
}: {
  groups: NavGroup[];
  label: string;
  openLabel: string;
  closeLabel: string;
  productName: string;
  area: string;
  initialExpandedGroups?: string[];
  tenants?: { id: string; name: string }[];
  currentTenant?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    function onOpen() {
      setOpen(true);
    }
    window.addEventListener(OPEN_NAV_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_NAV_EVENT, onOpen);
  }, []);

  return (
    <>
      <button
        type="button"
        aria-label={openLabel}
        aria-expanded={open}
        aria-controls="mobile-nav-drawer"
        data-testid="nav-toggle"
        onClick={() => setOpen(true)}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-fg transition duration-150 hover:bg-surface-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus lg:hidden"
      >
        <MenuIcon className="h-5 w-5" />
      </button>
      <NavDrawer
        open={open}
        onClose={() => setOpen(false)}
        groups={groups}
        initialExpandedGroups={initialExpandedGroups}
        tenants={tenants}
        currentTenant={currentTenant}
        label={label}
        closeLabel={closeLabel}
        productName={productName}
        area={area}
      />
    </>
  );
}
