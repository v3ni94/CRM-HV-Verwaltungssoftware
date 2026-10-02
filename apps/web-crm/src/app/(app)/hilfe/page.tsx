import { getTranslations } from "next-intl/server";

import { HelpSearch } from "@/components/hilfe/HelpSearch";
import { PageHeader } from "@/components/ui/PageHeader";

/** Handbuch im Produkt: Kapitel aus docs/handbuch (scripts/build_handbook.py), Suche im Browser. */
export default async function HilfePage() {
  const t = await getTranslations("Hilfe");
  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("description")} />
      <HelpSearch placeholder={t("searchPlaceholder")} empty={t("noHits")} />
    </div>
  );
}
