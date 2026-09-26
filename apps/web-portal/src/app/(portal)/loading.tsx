import { getTranslations } from "next-intl/server";

/** Loading state of the signed-in area (server components fetch on every request): a short
 *  live region and neutral placeholders instead of an empty screen on slow connections. */
export default async function PortalLoading() {
  const t = await getTranslations("Portal");
  return (
    <div className="flex flex-col gap-6" role="status" aria-live="polite" aria-busy="true" data-testid="portal-loading">
      <span className="sr-only">{t("loading")}</span>
      <div aria-hidden="true" className="h-8 w-48 max-w-full animate-pulse rounded-md bg-surface" />
      <div aria-hidden="true" className="flex flex-col gap-3">
        <div className="h-20 animate-pulse rounded-xl border border-border bg-surface" />
        <div className="h-20 animate-pulse rounded-xl border border-border bg-surface" />
        <div className="h-20 animate-pulse rounded-xl border border-border bg-surface" />
      </div>
    </div>
  );
}
