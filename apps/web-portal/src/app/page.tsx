import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { ApiStatusLine } from "@/components/ApiStatusLine";
import { ui } from "@/lib/ui";

// Render per request so the API status is always current.
export const dynamic = "force-dynamic";

// Mobile first: single column with small gutters, wider spacing from the sm breakpoint.
export default async function HomePage() {
  const t = await getTranslations("Home");
  return (
    <main className="mx-auto flex w-full max-w-xl flex-col gap-3 px-4 py-8 sm:gap-4 sm:px-6 sm:py-16">
      <h1 className="text-2xl font-semibold sm:text-3xl">{t("productName")}</h1>
      <p className="text-base text-muted sm:text-lg">{t("area")}</p>
      <p className="text-sm text-muted">{t("intro")}</p>
      <div className="flex flex-wrap gap-2">
        <Link href="/anmelden" className={ui.primary}>
          {t("login")}
        </Link>
        <Link href="/uebergabe" className={ui.button}>
          {t("handover")}
        </Link>
      </div>
      <ApiStatusLine />
    </main>
  );
}
