import { getTranslations } from "next-intl/server";

import { CalendarView } from "@/components/workspace/CalendarView";
import { ui } from "@/lib/ui";

export default async function CalendarPage() {
  const t = await getTranslations("Workspace");
  const now = new Date();
  return (
    <div className="flex flex-col gap-4">
      <h1 className={ui.title}>{t("calendar")}</h1>
      <CalendarView initialYear={now.getFullYear()} initialMonth={now.getMonth()} />
    </div>
  );
}
