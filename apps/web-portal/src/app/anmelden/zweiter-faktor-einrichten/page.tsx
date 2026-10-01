import { getTranslations } from "next-intl/server";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AuthCard } from "@/components/auth/AuthCard";
import { MfaSetupForm } from "@/components/auth/MfaSetupForm";
import { COOKIE } from "@/lib/session";

export const dynamic = "force-dynamic";

/** M2-04: TOTP setup inside the login flow when the tenant policy covers portal accounts. */
export default async function MfaSetupPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const [t, params, store] = await Promise.all([getTranslations("Auth"), searchParams, cookies()]);
  if (!store.get(COOKIE.mfaSetup)) redirect("/anmelden");
  return (
    <AuthCard title={t("mfaSetupTitle")}>
      <MfaSetupForm {...(params.next ? { next: params.next } : {})} />
    </AuthCard>
  );
}
