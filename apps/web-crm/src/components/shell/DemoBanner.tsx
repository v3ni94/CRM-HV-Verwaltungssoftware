import { getTranslations } from "next-intl/server";

/** Notice band for users of a demo tenant (AE36, AF19): invented data only, no productive
 *  use. Rendered above the header row of the app shell. */
export async function DemoBanner({ isDemo }: { isDemo: boolean }) {
  if (!isDemo) return null;
  const t = await getTranslations("AF19");
  return (
    <div role="note" data-testid="demo-banner" className="border-b border-border-soft bg-surface-2 px-4 py-1 text-center text-xs font-medium text-muted sm:px-6 lg:px-8">
      {t("demo.banner")}
    </div>
  );
}
