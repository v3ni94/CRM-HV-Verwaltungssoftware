import { getTranslations } from "next-intl/server";

import { ApiStatusLine } from "@/components/ApiStatusLine";

// Render per request so the API status is always current.
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const t = await getTranslations("Home");
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-4 px-6 py-16">
      <h1 className="text-3xl font-semibold">{t("productName")}</h1>
      <p className="text-lg text-muted">{t("area")}</p>
      <ApiStatusLine />
    </main>
  );
}
