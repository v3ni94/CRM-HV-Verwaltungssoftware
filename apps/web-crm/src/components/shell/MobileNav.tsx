"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { CloseIcon, MenuIcon } from "./icons";
import type { NavGroup } from "./SideNav";

/** Mobile navigation: a hamburger button in the top bar that opens a slide-in drawer with the
 *  same grouped links as the desktop rail. Closes on route change and Escape, and locks body
 *  scroll while open. Rendered only below `md`; the desktop rail (`SideNav`) handles `md` and
 *  up and is hidden below it. */
export function MobileNav({
  groups,
  label,
  openLabel,
  closeLabel,
  productName,
  area,
}: {
  groups: NavGroup[];
  label: string;
  openLabel: string;
  closeLabel: string;
  productName: string;
  area: string;
}) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
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

  const active = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);

  return (
    <>
      <button
        type="button"
        aria-label={openLabel}
        aria-expanded={open}
        aria-controls="mobile-nav-drawer"
        onClick={() => setOpen(true)}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-fg transition duration-150 hover:bg-surface-2 md:hidden"
      >
        <MenuIcon className="h-5 w-5" />
      </button>
      {open && typeof document !== "undefined"
        ? // Portal: the sticky header uses backdrop blur, which would trap a fixed drawer inside it.
          createPortal(
            <div className="fixed inset-0 z-[60] md:hidden">
              <div
                className="fixed inset-0 bg-black/40"
                aria-hidden="true"
                onClick={() => setOpen(false)}
              />
              <div
                id="mobile-nav-drawer"
                role="dialog"
                aria-modal="true"
                aria-label={label}
                className="fixed inset-y-0 left-0 flex h-full w-72 max-w-[85vw] flex-col overflow-y-auto bg-rail-bg text-rail-fg shadow-lg"
                style={{
                  paddingTop: "env(safe-area-inset-top)",
                  paddingBottom: "env(safe-area-inset-bottom)",
                }}
              >
                <div className="flex items-center justify-between gap-3 border-b border-rail-border px-4 py-3">
                  <span className="flex min-w-0 flex-col leading-tight">
                    <span className="truncate text-sm font-semibold">
                      {productName}
                    </span>
                    <span className="mhvp-label text-rail-muted">{area}</span>
                  </span>
                  <button
                    type="button"
                    aria-label={closeLabel}
                    onClick={() => setOpen(false)}
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-rail-muted transition duration-150 hover:bg-rail-hover hover:text-rail-fg"
                  >
                    <CloseIcon className="h-5 w-5" />
                  </button>
                </div>
                <nav
                  aria-label={label}
                  className="flex flex-1 flex-col gap-1 px-2 py-3"
                >
                  {groups.map((g) => (
                    <div key={g.label} className="flex flex-col gap-1 pb-2">
                      <span className="mhvp-label px-3 pb-1 text-rail-muted">
                        {g.label}
                      </span>
                      {g.items.map((item) => (
                        <Link
                          key={item.href}
                          href={item.href}
                          aria-current={active(item.href) ? "page" : undefined}
                          className={`flex min-h-11 items-center gap-2.5 rounded-md px-3 py-2 text-sm transition duration-150 ${
                            active(item.href)
                              ? "bg-rail-active font-medium text-rail-fg"
                              : "text-rail-muted hover:bg-rail-hover hover:text-rail-fg"
                          }`}
                        >
                          {item.label}
                        </Link>
                      ))}
                    </div>
                  ))}
                </nav>
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
