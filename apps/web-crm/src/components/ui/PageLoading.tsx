import { getTranslations } from "next-intl/server";

/** Ladezustand einer Seite (Next.js `loading.tsx`): Platzhalter für Titel, Hinweis und Tabelle,
 *  mit Statustext für Screenreader. Rein darstellend. */
export async function PageLoading() {
  const t = await getTranslations("Shell");
  return (
    <div className="flex flex-col gap-4" role="status" aria-live="polite" data-testid="page-loading">
      <span className="sr-only">{t("loading")}</span>
      <div aria-hidden="true" className="flex flex-col gap-4">
        <div className="h-8 w-56 max-w-full animate-pulse rounded-md bg-surface" />
        <div className="h-12 w-full animate-pulse rounded-md bg-surface" />
        <div className="h-40 w-full animate-pulse rounded-xl bg-surface" />
      </div>
    </div>
  );
}
