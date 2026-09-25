import { getTranslations } from "next-intl/server";

import { PageHeader } from "@/components/ui/PageHeader";
import { CHANGELOG } from "@/lib/changelog";
import { appBuild, appVersion } from "@/lib/version";

export const dynamic = "force-dynamic";

/** Versionsverlauf: was wurde in welcher Version geändert. */
export default async function VersionPage() {
  const t = await getTranslations("Version");
  const build = appBuild();
  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("description")} />
      <p className="text-sm text-muted">
        {t("current", { version: appVersion() })}
        {build ? ` · Build ${build}` : ""}
      </p>
      <p className="text-xs text-subtle">{t("scheme")}</p>
      <div className="space-y-6">
        {CHANGELOG.map((entry) => (
          <section key={entry.version} className="rounded-lg border border-border-soft p-4">
            <h2 className="text-base font-semibold">
              {entry.version} · {entry.title}
            </h2>
            <p className="text-xs text-subtle">{entry.date}</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
              {entry.changes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
