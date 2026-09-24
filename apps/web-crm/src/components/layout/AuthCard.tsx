import { getTranslations } from "next-intl/server";
import Image from "next/image";

export async function AuthCard({ title, children }: { title: string; children: React.ReactNode }) {
  const t = await getTranslations("Home");
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-4 py-12">
      <div className="flex items-center gap-4">
        <Image src="/logo-mhag.png" alt="" width={64} height={55} unoptimized priority className="h-14 w-auto" />
        <div>
          <p className="mhvp-label">{t("productName")}</p>
          <h1 className="mhvp-title text-2xl font-semibold tracking-tight">{title}</h1>
        </div>
      </div>
      <div className="rounded-lg border border-border bg-bg p-6 shadow-card">{children}</div>
      <p className="text-xs text-subtle">{t("footer")}</p>
    </main>
  );
}
