import { StatusBadge } from "@mhvp/ui";
import { getTranslations } from "next-intl/server";

import { getApiStatus } from "@/lib/api-status";

export async function ApiStatusLine() {
  const [t, status] = await Promise.all([getTranslations("Home"), getApiStatus()]);
  const ready = status === "ready";
  return (
    <p className="flex items-center gap-2 text-sm text-muted">
      <span>{t("apiStatusLabel")}:</span>
      <StatusBadge state={ready ? "ok" : "fail"} label={ready ? t("apiReady") : t("apiUnavailable")} />
    </p>
  );
}
