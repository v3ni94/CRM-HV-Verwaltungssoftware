import { getTranslations } from "next-intl/server";

import { AuthCard } from "@/components/auth/AuthCard";
import { MagicLinkConsume } from "@/components/auth/MagicLinkConsume";

export const dynamic = "force-dynamic";

/** M21-01: target of the mailed login link (?token=<mandant>.<geheimnis>). */
export default async function MagicLinkPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const [t, { token }] = await Promise.all([getTranslations("Auth"), searchParams]);
  return (
    <AuthCard title={t("magicLink.title")}>
      <MagicLinkConsume token={token} />
    </AuthCard>
  );
}
