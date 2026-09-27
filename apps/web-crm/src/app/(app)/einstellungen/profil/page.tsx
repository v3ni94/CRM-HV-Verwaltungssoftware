import { getTranslations } from "next-intl/server";

import { ProfileSettings } from "@/components/settings/ProfileSettings";
import type { SignaturePreviewData, SignatureProfileData } from "@/components/settings/SignatureProfile";
import { redirectIfUnauthenticated, serverApi, serverFetch, sessionContext } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

export default async function ProfilePage() {
  const t = await getTranslations("Profile");
  const api = serverApi();
  const [me, sessions, devices, ctx, signatureProfile, signaturePreview] = await Promise.all([
    getMe(),
    api.GET("/api/v1/auth/sessions"),
    api.GET("/api/v1/auth/trusted-devices"),
    sessionContext(),
    // E-Mail-Signatur (operator 27.09.2026): eigene Position und Vorschau, serverseitig gerendert.
    serverFetch("/api/v1/mail/signature/profile").then(async (r) => (r.ok ? ((await r.json()) as SignatureProfileData) : null)),
    serverFetch("/api/v1/mail/signature/preview").then(async (r) => (r.ok ? ((await r.json()) as SignaturePreviewData) : null)),
  ]);
  redirectIfUnauthenticated(me.response);
  const tenantName = ctx.tenants.find((tenant) => tenant.id === ctx.tenantId)?.name ?? "";
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <ProfileSettings
        displayName={me.data?.display_name ?? ""}
        email={me.data?.email ?? ""}
        roles={me.data?.roles ?? []}
        tenantName={tenantName}
        initialSessions={sessions.data ?? []}
        initialDevices={devices.data ?? []}
        totpEnabled={me.data?.totp_enabled ?? false}
        signatureProfile={signatureProfile}
        signaturePreview={signaturePreview}
      />
    </div>
  );
}
