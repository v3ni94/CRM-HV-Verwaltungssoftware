"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export function UserMenu({ name }: { name: string }) {
  const t = useTranslations("Shell");
  const router = useRouter();

  async function logout() {
    await bff<null>("/api/session/logout", { method: "POST" });
    router.push("/anmelden");
    router.refresh();
  }

  return (
    <details className="relative">
      <summary className={`${ui.button} cursor-pointer list-none`} aria-label={t("userMenu")}>
        {name}
      </summary>
      <div className="absolute right-0 z-40 mt-1 w-44 rounded border border-border bg-bg p-1 shadow">
        <button type="button" className="w-full rounded px-3 py-1.5 text-left text-sm hover:bg-surface" onClick={() => void logout()}>
          {t("logout")}
        </button>
      </div>
    </details>
  );
}
