"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect } from "react";

import { ui } from "@/lib/ui";

/** Error boundary of the signed-in area: a failed API call renders a German notice with retry
 *  instead of the framework's default error screen. The technical cause is logged in the browser
 *  console only; nothing of it is shown to tenants or owners. */
export default function PortalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const t = useTranslations("Portal");
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div className={ui.pageGap} role="alert">
      <h1 className={ui.title}>{t("errorTitle")}</h1>
      <p className="text-sm text-muted">{t("errorHint")}</p>
      <div className={ui.formActions}>
        <button type="button" className={`${ui.primary} ${ui.actionFull}`} onClick={() => reset()}>
          {t("retry")}
        </button>
        <Link href="/start" className={`${ui.secondary} ${ui.actionFull}`}>
          {t("toStart")}
        </Link>
      </div>
    </div>
  );
}
