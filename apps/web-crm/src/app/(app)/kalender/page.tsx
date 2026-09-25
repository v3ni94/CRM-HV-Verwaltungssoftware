import { getTranslations } from "next-intl/server";

import { CalendarView } from "@/components/workspace/CalendarView";
import { PageHeader } from "@/components/ui/PageHeader";

export default async function CalendarPage() {
  const t = await getTranslations("Workspace");
  const now = new Date();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("calendar")} />
      <CalendarView initialYear={now.getFullYear()} initialMonth={now.getMonth()} />
    </div>
  );
}
