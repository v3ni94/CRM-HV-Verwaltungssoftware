import { getTranslations } from "next-intl/server";

import { BrandMark, LegalLinks } from "@/components/shell/Branding";
import { LanguageSwitch } from "@/components/shell/LanguageSwitch";
import { fetchPortalBranding } from "@/lib/branding";

/** Sign-in frame of the portal: neutral, or with the tenant branding of the portal host
 *  (logo, name, imprint and privacy links; B26, M21-04). Empty branding stays neutral. */
export async function AuthCard({ title, children }: { title: string; children: React.ReactNode }) {
  const [t, branding] = await Promise.all([getTranslations("Home"), fetchPortalBranding()]);
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-sm flex-col justify-center gap-6 px-4 py-12">
      <div>
        <BrandMark branding={branding} fallback={t("productName")} />
        <h1 className="mhvp-title text-2xl font-semibold tracking-tight">{title}</h1>
      </div>
      <div className="rounded-xl border border-border bg-surface p-6 shadow-card">{children}</div>
      <p className="text-xs text-subtle">{t("intro")}</p>
      <LegalLinks branding={branding} />
      <LanguageSwitch persist={false} className="self-start" />
    </main>
  );
}
