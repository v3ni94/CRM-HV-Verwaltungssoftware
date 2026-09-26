import { getTranslations } from "next-intl/server";

import { AuthCard } from "@/components/auth/AuthCard";
import { InvitationForm } from "@/components/auth/InvitationForm";

export const dynamic = "force-dynamic";

/** Einladung annehmen (A56): Ziel des Einladungslinks (Text oder QR-Code) aus dem CRM. Der
 *  Code kann auch von Hand eingegeben werden. */
export default async function InvitationPage({ searchParams }: { searchParams: Promise<{ code?: string }> }) {
  const [t, { code }] = await Promise.all([getTranslations("Invitation"), searchParams]);
  return (
    <AuthCard title={t("title")}>
      <InvitationForm {...(code ? { code } : {})} />
    </AuthCard>
  );
}
