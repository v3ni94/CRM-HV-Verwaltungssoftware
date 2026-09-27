import { getTranslations } from "next-intl/server";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AuthCard } from "@/components/auth/AuthCard";
import { MfaForm } from "@/components/auth/MfaForm";
import { COOKIE } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function MfaPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const [t, params, store] = await Promise.all([getTranslations("Auth"), searchParams, cookies()]);
  if (!store.get(COOKIE.mfa)) redirect("/anmelden");
  return (
    <AuthCard title={t("mfaTitle")}>
      <MfaForm {...(params.next ? { next: params.next } : {})} />
    </AuthCard>
  );
}
