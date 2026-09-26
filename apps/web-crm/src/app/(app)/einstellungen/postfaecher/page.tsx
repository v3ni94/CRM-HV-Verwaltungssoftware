import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { CallAssistantSettings, type CallAssistant } from "@/components/mail/CallAssistantSettings";
import { InvoiceForwardingSettings, type InvoiceForwarding } from "@/components/mail/InvoiceForwardingSettings";
import { MailboxSettings, type Mailbox, type Member, type OAuthStatus } from "@/components/mail/MailboxSettings";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

/** Mailboxes (M20-01): Google OAuth client per tenant, consent flow, default mailbox and
 *  per user access. The OAuth callback lands here with ?connected= or ?oauth_error=. */
export default async function MailboxSettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ connected?: string; oauth_error?: string }>;
}) {
  const t = await getTranslations("MailSettings");
  const params = await searchParams;
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("tenant_settings:update")) notFound();
  const [oauth, mailboxes, members, invoiceForwarding] = await Promise.all([
    api.GET("/api/v1/mail/oauth/google"),
    api.GET("/api/v1/mail/mailboxes"),
    api.GET("/api/v1/tenant/members"),
    api.GET("/api/v1/mail/invoice-forwarding"),
  ]);
  const callAssistant = await api.GET("/api/v1/mail/call-assistant");
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className="text-sm text-muted">{t("intro")}</p>
      {params.connected ? <p className={ui.notice}>{t("connected", { address: params.connected })}</p> : null}
      {params.oauth_error ? (
        <p role="alert" className={ui.alert}>
          {t("oauthFailed", { reason: params.oauth_error })}
        </p>
      ) : null}
      <MailboxSettings
        oauth={(oauth.data ?? { client_id: null, configured: false, source: null, redirect_uri: "" }) as OAuthStatus}
        mailboxes={(mailboxes.data ?? []) as Mailbox[]}
        members={(members.data ?? []) as Member[]}
      />
      <InvoiceForwardingSettings
        initial={
          (invoiceForwarding.data ?? {
            enabled: false,
            forward_address: null,
            sender_allowlist: [],
            learning_list: [],
          }) as InvoiceForwarding
        }
      />
      <CallAssistantSettings
        initial={
          (callAssistant.data ?? {
            enabled: true,
            sender_patterns: [],
            keywords: [],
          }) as CallAssistant
        }
      />
    </div>
  );
}
