import { getTranslations } from "next-intl/server";
import Image from "next/image";

/** Shared frame of every login step (Anmeldung, zweiter Faktor, Mandantenwahl): a calm split
 *  screen with the product identity on the left and the step's own card on the right. Only
 *  existing design tokens are used, no new colours (operator 27.09.2026). */
export async function AuthCard({
  title,
  helpText,
  children,
}: {
  title: string;
  helpText?: string;
  children: React.ReactNode;
}) {
  const t = await getTranslations("Home");
  const a = await getTranslations("Auth");
  return (
    <main className="flex min-h-screen flex-col md:flex-row">
      <div className="hidden flex-col justify-between border-r border-card-line bg-surface px-10 py-12 md:flex md:w-[42%] md:min-w-[22rem] lg:w-[38%]">
        <div className="flex items-center gap-4">
          <Image src="/logo-mhag.png" alt="" width={64} height={55} unoptimized priority className="mhvp-logo h-12 w-auto" />
          <p className="mhvp-label">{t("productName")}</p>
        </div>
        <div className="flex max-w-sm flex-col gap-4">
          <h2 className="mhvp-display font-semibold tracking-tight text-fg">{t("productName")}</h2>
          <div aria-hidden className="h-px w-12 bg-gold" />
          <p className="text-base text-muted">{a("claim")}</p>
        </div>
        <p className="max-w-sm text-xs text-subtle">{t("footer")}</p>
      </div>
      <div className="flex flex-1 flex-col justify-center px-4 py-12 md:px-12">
        <div className="mx-auto flex w-full max-w-sm flex-col gap-6">
          <div className="flex items-center gap-4 md:hidden">
            <Image src="/logo-mhag.png" alt="" width={64} height={55} unoptimized priority className="mhvp-logo h-14 w-auto" />
            <p className="mhvp-label">{t("productName")}</p>
          </div>
          <h1 className="mhvp-title text-2xl font-semibold tracking-tight text-fg">{title}</h1>
          <div className="rounded-lg border border-card-line bg-surface p-6 shadow-card">{children}</div>
          {helpText ? <p className="text-center text-xs text-subtle">{helpText}</p> : null}
          <p className="text-xs text-subtle md:hidden">{t("footer")}</p>
        </div>
      </div>
    </main>
  );
}
