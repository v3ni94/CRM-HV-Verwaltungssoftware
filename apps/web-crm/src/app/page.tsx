import { getTranslations } from "next-intl/server";
import { cookies } from "next/headers";
import Link from "next/link";

import { ApiStatusLine } from "@/components/ApiStatusLine";
import { COOKIE } from "@/lib/session";

// Render per request so the API status is always current.
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [t, store] = await Promise.all([getTranslations("Home"), cookies()]);
  const signedIn = !!store.get(COOKIE.refresh);
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-4 px-6 py-16">
      <h1 className="text-3xl font-semibold">{t("productName")}</h1>
      <p className="text-lg text-muted">{t("area")}</p>
      <ApiStatusLine />
      <p>
        <Link href={signedIn ? "/kontakte" : "/anmelden"} className="underline">
          {signedIn ? t("toContacts") : t("toLogin")}
        </Link>
      </p>
    </main>
  );
}
