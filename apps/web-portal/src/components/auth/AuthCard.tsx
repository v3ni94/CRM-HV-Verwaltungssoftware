import { getTranslations } from "next-intl/server";

/** Neutral sign-in frame of the portal (no tenant branding until V14 is released). */
export async function AuthCard({ title, children }: { title: string; children: React.ReactNode }) {
  const t = await getTranslations("Home");
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-sm flex-col justify-center gap-6 px-4 py-12">
      <div>
        <p className="mhvp-label">{t("productName")}</p>
        <h1 className="mhvp-title text-2xl font-semibold tracking-tight">{title}</h1>
      </div>
      <div className="rounded-xl border border-border bg-bg p-6 shadow-card">{children}</div>
      <p className="text-xs text-subtle">{t("intro")}</p>
    </main>
  );
}
