import { getTranslations } from "next-intl/server";

import {
  ForwardingSettings,
  type ForwardingConfig,
} from "@/components/mail/ForwardingSettings";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Forwarding of company invoices (M32): only invoices addressed to the company itself go to
 *  the invoicing mailbox; property invoices never leave the system automatically. */
export default async function ForwardingPage() {
  const t = await getTranslations("MailForwarding");
  const { data, response } = await serverApi().GET("/api/v1/mail/forwarding");
  redirectIfUnauthenticated(response);
  const config = (data ?? {
    enabled: false,
    address: "",
    mode: "suggest",
    senders: [],
  }) as ForwardingConfig;
  return (
    <div className="flex flex-col gap-5">
      <PageHeader eyebrow={t("eyebrow")} title={t("title")} description={t("intro")} />
      <p className={ui.notice}>{t("safetyNotice")}</p>
      <ForwardingSettings config={config} />
    </div>
  );
}
