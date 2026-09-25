import { getTranslations } from "next-intl/server";

import { InviteForm } from "@/components/auth/InviteForm";
import { AuthCard } from "@/components/layout/AuthCard";

export const dynamic = "force-dynamic";

export default async function InvitePage() {
  const t = await getTranslations("Auth");
  return (
    <AuthCard title={t("inviteTitle")}>
      <InviteForm />
    </AuthCard>
  );
}
