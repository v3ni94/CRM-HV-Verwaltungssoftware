"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useState } from "react";

export type PortalNavLink = { href: string; label: string };

/** Portal navigation (O02): below `md` a toggle button with `aria-expanded` opens the link list
 *  as a collapsible menu (closed on route change and on Escape, no focus trap needed because
 *  the content below stays reachable); from `md` upwards the links are always shown in one
 *  horizontal row as before. The current page is marked with `aria-current="page"`. */
export function PortalNav({
  links,
  label,
  openLabel,
  closeLabel,
}: {
  links: PortalNavLink[];
  label: string;
  openLabel: string;
  closeLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname() ?? "";
  const menuId = useId();

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

  const active = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <nav aria-label={label} className="flex flex-col gap-1 md:block">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex min-h-11 w-full items-center justify-between gap-2 rounded-md border border-border bg-bg px-3 text-sm font-medium text-fg transition duration-150 hover:border-gold focus:outline-none focus:ring-2 focus:ring-gold/40 md:hidden"
      >
        <span>{open ? closeLabel : openLabel}</span>
        <span aria-hidden="true" className="text-xs text-muted">
          {open ? "▲" : "▼"}
        </span>
      </button>
      <ul
        id={menuId}
        data-open={open ? "true" : "false"}
        className={`${open ? "flex" : "hidden"} flex-col gap-1 border-t border-border pt-2 text-sm md:flex md:flex-row md:flex-wrap md:gap-x-4 md:gap-y-1 md:border-0 md:pt-0`}
      >
        {links.map((link) => {
          const current = active(link.href);
          return (
            <li key={link.href} className="flex">
              <Link
                href={link.href}
                aria-current={current ? "page" : undefined}
                onClick={() => setOpen(false)}
                className={`inline-flex min-h-11 w-full items-center rounded-md px-2 hover:text-fg hover:underline focus:outline-none focus:ring-2 focus:ring-gold/40 md:min-h-9 md:w-auto md:px-0 ${
                  current ? "bg-surface font-medium text-fg md:bg-transparent md:border-b-2 md:border-gold md:rounded-none" : "text-muted"
                }`}
              >
                {link.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
