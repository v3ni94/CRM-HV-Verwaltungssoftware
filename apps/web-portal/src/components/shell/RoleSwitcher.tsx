"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

export const VIEW_COOKIE = "portal_view";

/** Rollenwechsel (M21-05, S16-10): nur für Konten mit mehreren abgeleiteten Portalrollen. Die
 *  Auswahl begrenzt nur die Navigation (Cookie), sie vergibt keine Rechte; der Zugriff wird
 *  weiterhin in der API aus den Berechtigungen geprüft. */
export function RoleSwitcher({ roles, current }: { roles: string[]; current: string | null }) {
  const t = useTranslations("Portal.roleSwitch");
  const router = useRouter();
  if (roles.length < 2) return null;

  function choose(value: string) {
    document.cookie = `${VIEW_COOKIE}=${value}; path=/; max-age=31536000; samesite=strict`;
    router.refresh();
  }

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted">{t("label")}</span>
      <select
        value={current ?? ""}
        onChange={(event) => choose(event.target.value)}
        className="min-h-11 pointer-fine:min-h-9 rounded-md border border-border bg-surface px-2 text-sm"
      >
        <option value="">{t("all")}</option>
        {roles.map((role) => (
          <option key={role} value={role}>
            {t(role as "owner")}
          </option>
        ))}
      </select>
    </label>
  );
}
