import { getTranslations } from "next-intl/server";

import { NotificationPreferences } from "@/components/settings/NotificationPreferences";
import { NotificationMailContent } from "@/components/settings/NotificationMailContent";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

/** Eigene Benachrichtigungseinstellungen (M23-04): Kanal je Art und Stummschaltung. */
export default async function NotificationSettingsPage() {
  const t = await getTranslations("NotificationSettings");
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      <NotificationPreferences />
      <NotificationMailContent />
    </div>
  );
}
