import { getTranslations } from "next-intl/server";

import { MeterReadingForm } from "@/components/portal/MeterReadingForm";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function MeterPage() {
  const t = await getTranslations("Meter");
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <MeterReadingForm />
    </div>
  );
}
