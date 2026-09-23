import { getTranslations } from "next-intl/server";

export async function AuthCard({ title, children }: { title: string; children: React.ReactNode }) {
  const t = await getTranslations("Home");
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-4 py-12">
      <div>
        <p className="text-sm text-muted">{t("productName")}</p>
        <h1 className="text-2xl font-semibold">{title}</h1>
      </div>
      <div className="rounded border border-border bg-surface p-5">{children}</div>
    </main>
  );
}
