import { getTranslations } from "next-intl/server";

import { ApiStatusLine } from "@/components/ApiStatusLine";

/** Centered card for the public pages (login, invitation). Mobile first, no side panel. */
export async function AuthCard({ title, children }: { title: string; children: React.ReactNode }) {
  const t = await getTranslations("Home");
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <div>
          <p className="mhvp-label">{t("productName")}</p>
          <p className="text-sm text-muted">{t("area")}</p>
        </div>
        <h1 className="mhvp-title text-2xl font-semibold tracking-tight">{title}</h1>
        <div className="rounded-xl border border-border bg-bg p-6 shadow-card">{children}</div>
        <ApiStatusLine />
      </div>
    </main>
  );
}
