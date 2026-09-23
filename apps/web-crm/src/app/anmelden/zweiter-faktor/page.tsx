import { getTranslations } from "next-intl/server";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { MfaForm } from "@/components/auth/MfaForm";
import { AuthCard } from "@/components/layout/AuthCard";
import { COOKIE } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function MfaPage({
  searchParams,
}: {
  searchParams: Promise<{ einrichten?: string; next?: string }>;
}) {
  const [t, params, store] = await Promise.all([getTranslations("Auth"), searchParams, cookies()]);
  if (!store.get(COOKIE.mfa)) redirect("/anmelden");
  const setup = params.einrichten === "1";
  return (
    <AuthCard title={setup ? t("mfaSetupTitle") : t("mfaTitle")}>
      <MfaForm setup={setup} {...(params.next ? { next: params.next } : {})} />
    </AuthCard>
  );
}
