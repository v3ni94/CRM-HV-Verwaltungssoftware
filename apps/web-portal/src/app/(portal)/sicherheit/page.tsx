import { getTranslations } from "next-intl/server";

import { SecuritySettings } from "@/components/portal/SecuritySettings";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Sicherheit (operator 26.09.2026, M2-01): optional second factor and remembered devices of
 *  the own portal account. */
export default async function SecurityPage() {
  const api = serverApi();
  const [t, me, devices] = await Promise.all([
    getTranslations("Security"),
    api.GET("/api/v1/auth/me"),
    api.GET("/api/v1/auth/trusted-devices"),
  ]);
  redirectIfUnauthenticated(me.response);
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <p className={ui.notice}>{t("intro")}</p>
      <SecuritySettings totpEnabled={me.data?.totp_enabled ?? false} initialDevices={devices.data ?? []} />
    </div>
  );
}
