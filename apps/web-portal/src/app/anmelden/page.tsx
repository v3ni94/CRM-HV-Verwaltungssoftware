import { getTranslations } from "next-intl/server";

import { LoginForm } from "@/components/auth/LoginForm";
import { AuthCard } from "@/components/layout/AuthCard";

export const dynamic = "force-dynamic";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const [t, { next }] = await Promise.all([getTranslations("Auth"), searchParams]);
  return (
    <AuthCard title={t("loginTitle")}>
      <LoginForm {...(next ? { next } : {})} />
    </AuthCard>
  );
}
