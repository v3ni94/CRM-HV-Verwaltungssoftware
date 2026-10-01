import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { RetentionSettings, type DocumentCategory, type RetentionProfile } from "@/components/documents/RetentionSettings";
import { TrashSettings, type TrashSettingsData } from "@/components/documents/TrashSettings";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Einstellungen, Aufbewahrung (M6-04, V17): Profile je Unterlagenklasse bearbeiten und im
 *  Vier-Augen-Prinzip freigeben, Dokumentkategorien einem Profil zuordnen. Die Fristen sind
 *  Entwürfe des Betreibers; die Prüfung durch die Steuerberatung ist offen. */
export default async function RetentionSettingsPage() {
  const t = await getTranslations("RetentionSettings");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("tenant_settings:update")) notFound();
  const [profilesRes, categoriesRes, trashRes] = await Promise.all([
    serverFetch("/api/v1/retention-profiles"),
    serverFetch("/api/v1/document-categories"),
    serverFetch("/api/v1/documents/trash-settings"),
  ]);
  const trash = trashRes.ok ? ((await trashRes.json()) as TrashSettingsData) : null;
  const profiles = profilesRes.ok ? ((await profilesRes.json()) as RetentionProfile[]) : [];
  const categories = categoriesRes.ok ? ((await categoriesRes.json()) as DocumentCategory[]) : [];
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/einstellungen", label: t("breadcrumb") }]} title={t("title")} description={t("intro")} />
      <RetentionSettings profiles={profiles} categories={categories} userId={me.data?.user_id ?? null} />
      {trash ? <TrashSettings initial={trash} canEdit={true} /> : null}
    </div>
  );
}
