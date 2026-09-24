import { getTranslations } from "next-intl/server";
import Image from "next/image";

export async function AuthCard({ title, children }: { title: string; children: React.ReactNode }) {
  const t = await getTranslations("Home");
  return (
    <main className="flex min-h-screen flex-col md:flex-row">
      <div className="hidden flex-col justify-between bg-surface px-10 py-12 md:flex md:w-[42%] md:min-w-[22rem] lg:w-[38%]">
        <div className="flex items-center gap-4">
          <Image src="/logo-mhag.png" alt="" width={64} height={55} unoptimized priority className="h-12 w-auto" />
          <div>
            <p className="mhvp-label">{t("productName")}</p>
          </div>
        </div>
        <div className="flex flex-col gap-3">
          <h2 className="mhvp-display font-semibold tracking-tight text-fg">{t("productName")}</h2>
          <p className="max-w-sm text-sm text-muted">{t("footer")}</p>
        </div>
        <div aria-hidden className="h-1 w-10 rounded-full bg-gold" />
      </div>
      <div className="flex flex-1 flex-col justify-center px-4 py-12 md:px-12">
        <div className="mx-auto flex w-full max-w-sm flex-col gap-6">
          <div className="flex items-center gap-4 md:hidden">
            <Image src="/logo-mhag.png" alt="" width={64} height={55} unoptimized priority className="h-14 w-auto" />
            <p className="mhvp-label">{t("productName")}</p>
          </div>
          <h1 className="mhvp-title text-2xl font-semibold tracking-tight">{title}</h1>
          <div className="rounded-xl border border-border bg-bg p-6 shadow-card">{children}</div>
          <p className="text-xs text-subtle md:hidden">{t("footer")}</p>
        </div>
      </div>
    </main>
  );
}
