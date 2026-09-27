import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { PostalOutbox } from "@/components/mail/PostalOutbox";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Postausgang (M23-01): Postaufträge je Zustellung mit Anbieterstatus, manuelle Erfassung von
 *  Druck, Versand und Zugang, Statusabruf beim Postdienst, Anbietereinstellung des Mandanten. */
export default async function MailPostausgangPage() {
  const t = await getTranslations("PostalOutbox");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("communication:read")) notFound();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("title")}
        description={t("intro")}
        breadcrumb={[{ href: "/mail", label: "Mail" }, { label: t("title") }]}
      />
      <PostalOutbox
        canWrite={permissions.includes("communication:update")}
        canSettings={permissions.includes("tenant_settings:update")}
      />
      <Link href="/mail" className="text-sm hover:underline">
        {t("backToMail")}
      </Link>
    </div>
  );
}
