"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { bff } from "@/lib/bff";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return (parts[0] ?? "?").slice(0, 2).toUpperCase();
  const first = parts[0]?.[0] ?? "";
  const last = parts[parts.length - 1]?.[0] ?? "";
  return `${first}${last}`.toUpperCase() || "?";
}

export function UserMenu({ name, email }: { name: string; email?: string }) {
  const t = useTranslations("Shell");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClick(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
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
        className="flex h-9 w-9 items-center justify-center rounded-full bg-gold-soft text-sm font-semibold text-fg shadow-xs transition duration-150 hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-gold/60 focus:ring-offset-2"
      >
        {initials(name)}
      </button>
      {open ? (
        <div
          role="menu"
          className="absolute right-0 z-40 mt-2 w-56 rounded-xl border border-border bg-bg p-1.5 shadow-lg"
        >
          <div className="border-b border-border-soft px-3 py-2">
            <p className="truncate text-sm font-medium text-fg">{name}</p>
            {email ? <p className="truncate text-xs text-muted">{email}</p> : null}
          </div>
          <Link
            href="/einstellungen/profil"
            role="menuitem"
            className="block rounded-md px-3 py-1.5 text-left text-sm transition duration-150 hover:bg-surface"
            onClick={() => setOpen(false)}
          >
            {t("myData")}
          </Link>
          <Link
            href="/einstellungen"
            role="menuitem"
            className="block rounded-md px-3 py-1.5 text-left text-sm transition duration-150 hover:bg-surface"
            onClick={() => setOpen(false)}
          >
            {t("settings")}
          </Link>
          <button
            type="button"
            role="menuitem"
            className="block w-full rounded-md px-3 py-1.5 text-left text-sm transition duration-150 hover:bg-surface"
            onClick={() => void logout()}
          >
            {t("logout")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
