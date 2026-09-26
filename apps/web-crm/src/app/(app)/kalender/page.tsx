import { getTranslations } from "next-intl/server";

import { CalendarView } from "@/components/workspace/CalendarView";
import { PageHeader } from "@/components/ui/PageHeader";

export default async function CalendarPage({
  searchParams,
}: {
  searchParams: Promise<{ datum?: string | string[] }>;
}) {
  const t = await getTranslations("Workspace");
  const { datum } = await searchParams;
  // ?datum=JJJJ-MM-TT (link from a created appointment, e.g. handover protocol) opens that month.
  const match = typeof datum === "string" ? /^(\d{4})-(\d{2})-\d{2}$/.exec(datum) : null;
  const now = match ? new Date(Number(match[1]), Number(match[2]) - 1, 1) : new Date();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("calendar")} />
      <CalendarView initialYear={now.getFullYear()} initialMonth={now.getMonth()} />
    </div>
  );
}
