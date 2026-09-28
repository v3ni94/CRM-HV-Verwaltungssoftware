"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ThemeSwitch } from "@/components/workspace/ThemeToggle";
import { bff } from "@/lib/bff";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return (parts[0] ?? "?").slice(0, 2).toUpperCase();
  const first = parts[0]?.[0] ?? "";
  const last = parts[parts.length - 1]?.[0] ?? "";
  return `${first}${last}`.toUpperCase() || "?";
}

/** Menu entries: 44 px on touch, the compact row with a mouse from `sm` (M31). */
const MENU_ITEM = "flex min-h-11 items-center rounded-md px-3 py-1.5 text-left text-sm transition duration-150 hover:bg-surface-2 sm:pointer-fine:min-h-0";

export function UserMenu({ name, email }: { name: string; email?: string }) {
  const t = useTranslations("Shell");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    // pointerdown instead of mousedown: fires for touch as well (M31).
    function onClick(event: PointerEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function logout() {
    await bff<null>("/api/session/logout", { method: "POST" });
    router.push("/anmelden");
    router.refresh();
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label={t("userMenu")}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex h-11 w-11 items-center justify-center rounded-full bg-gold-soft text-sm font-semibold text-fg shadow-xs transition duration-150 hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-focus focus:ring-offset-2 sm:pointer-fine:h-9 sm:pointer-fine:w-9"
      >
        {initials(name)}
      </button>
      {open ? (
        <div
          role="menu"
          className="absolute right-0 z-40 mt-2 w-64 rounded-xl border border-border bg-raised p-1.5 shadow-lg"
        >
          <div className="border-b border-border-soft px-3 py-2">
            <p className="truncate text-sm font-medium text-fg">{name}</p>
            {email ? <p className="truncate text-xs text-muted">{email}</p> : null}
          </div>
          <div className="border-b border-border-soft px-2 py-2">
            <ThemeSwitch className="w-full justify-between" />
          </div>
          <Link
            href="/einstellungen/profil"
            role="menuitem"
            className={MENU_ITEM}
            onClick={() => setOpen(false)}
          >
            {t("myData")}
          </Link>
          <Link
            href="/einstellungen"
            role="menuitem"
            className={MENU_ITEM}
            onClick={() => setOpen(false)}
          >
            {t("settings")}
          </Link>
          <button
            type="button"
            role="menuitem"
            className={`${MENU_ITEM} w-full`}
            onClick={() => void logout()}
          >
            {t("logout")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
