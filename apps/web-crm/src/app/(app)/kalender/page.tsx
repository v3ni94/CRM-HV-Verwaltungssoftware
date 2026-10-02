import { getTranslations } from "next-intl/server";

import { CalendarFeedPanel } from "@/components/calendar/CalendarFeedPanel";
import { CalendarView } from "@/components/workspace/CalendarView";
import { PageHeader } from "@/components/ui/PageHeader";
import { serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export default async function CalendarPage({
  searchParams,
}: {
  searchParams: Promise<{ datum?: string | string[]; termin?: string | string[] }>;
}) {
  const t = await getTranslations("Workspace");
  const { datum, termin } = await searchParams;
  // ?datum=JJJJ-MM-TT (link from a created appointment, e.g. handover protocol) opens that month;
  // ?termin=<id> (link from a notification, operator 26.09.2026) opens that entry's details.
  const match = typeof datum === "string" ? /^(\d{4})-(\d{2})-\d{2}$/.exec(datum) : null;
  const now = match ? new Date(Number(match[1]), Number(match[2]) - 1, 1) : new Date();
  const feed = await serverFetch("/api/v1/workspace/calendar-feed/token");
  const feedActive = feed?.ok ? Boolean(((await feed.json()) as { active?: boolean }).active) : null;
  const me = await getMe();
  const canDownload = (me.data?.permissions ?? []).includes("tenant_settings:read");
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("calendar")} />
      <CalendarView initialYear={now.getFullYear()} initialMonth={now.getMonth()} focusId={typeof termin === "string" ? termin : null} />
      {feedActive !== null ? <CalendarFeedPanel initialActive={feedActive} canDownload={canDownload} /> : null}
    </div>
  );
}
