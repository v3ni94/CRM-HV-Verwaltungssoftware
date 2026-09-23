import { getTranslations } from "next-intl/server";

import { ApiStatusLine } from "@/components/ApiStatusLine";

// Render per request so the API status is always current.
export const dynamic = "force-dynamic";

// Mobile first: single column with small gutters, wider spacing from the sm breakpoint.
export default async function HomePage() {
  const t = await getTranslations("Home");
  return (
    <main className="mx-auto flex w-full max-w-xl flex-col gap-3 px-4 py-8 sm:gap-4 sm:px-6 sm:py-16">
      <h1 className="text-2xl font-semibold sm:text-3xl">{t("productName")}</h1>
      <p className="text-base text-muted sm:text-lg">{t("area")}</p>
      <ApiStatusLine />
    </main>
  );
}
