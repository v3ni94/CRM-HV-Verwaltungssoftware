import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { AutoPostingReview } from "@/components/banking/AutoPostingReview";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Bank, Nachkontrolle (Regel M12-05): offene Nachkontrollen automatischer Buchungen mit
 *  Fälligkeit; In Ordnung mit accounting:review, Korrigieren als Storno plus Neubuchung. */
export default async function AutoPostingReviewPage() {
  const t = await getTranslations("Bank.review");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("description")} />
      <p className="text-sm">
        <Link href="/bank" className="font-medium hover:underline">
          {t("backToBank")}
        </Link>
      </p>
      <AutoPostingReview canReview={permissions.includes("accounting:review")} canBook={permissions.includes("accounting:create")} />
    </div>
  );
}
