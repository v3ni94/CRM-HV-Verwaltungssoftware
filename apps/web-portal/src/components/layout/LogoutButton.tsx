"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ui } from "@/lib/ui";

export function LogoutButton({ label }: { label: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function onLogout() {
    setBusy(true);
    try {
      await fetch("/api/session/logout", { method: "POST", credentials: "same-origin" });
    } catch {
      // The cookies are cleared server side; a network error still leads to the login page.
    }
    router.push("/anmelden");
    router.refresh();
  }

  return (
    <button type="button" onClick={onLogout} disabled={busy} className={ui.buttonSm}>
      {label}
    </button>
  );
}
