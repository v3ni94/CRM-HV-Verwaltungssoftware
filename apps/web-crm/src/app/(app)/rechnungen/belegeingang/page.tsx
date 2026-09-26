import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { ReceiptIntake, type ReceiptDraft } from "@/components/receipts/ReceiptIntake";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Belegeingang (M14): KI-Entwürfe von Eingangsrechnungen mit Feldprüfung. Es wird nichts
 *  gebucht; die Bestätigung legt nur einen offenen Rechnungsentwurf an (rule 0.1.6). */
export default async function ReceiptIntakePage({ searchParams }: { searchParams: Promise<{ entwurf?: string }> }) {
  const t = await getTranslations("Receipts");
  const { entwurf: initialDraftId } = await searchParams;
  const api = serverApi();
  const [drafts, ledgers] = await Promise.all([
    api.GET("/api/v1/receipts/drafts", { params: { query: { limit: 200 } } }),
    api.GET("/api/v1/accounting/ledgers"),
  ]);
  redirectIfUnauthenticated(drafts.response);
  const accounts: Record<string, { id: string; label: string }[]> = {};
  await Promise.all(
    (ledgers.data ?? []).map(async (l) => {
      const a = await api.GET("/api/v1/accounting/ledgers/{ledger_id}/accounts", { params: { path: { ledger_id: l.id } } });
      accounts[l.id] = ((a.data ?? []) as { id: string; number: string; name: string; category: string }[])
        .filter((x) => x.category === "cost")
        .map((x) => ({ id: x.id, label: `${x.number} ${x.name}` }));
    }),
  );
  return (
    <div className={ui.pageGap}>
      <PageHeader
        eyebrow={t("eyebrow")}
        title={t("title")}
        description={t("description")}
        breadcrumb={[{ href: "/rechnungen", label: t("eyebrow") }, { label: t("title") }]}
        action={
          <Link href="/rechnungen" className={ui.button}>
            {t("backToInvoices")}
          </Link>
        }
      />
      <p className={ui.notice}>{t("notice")}</p>
      <ReceiptIntake
        initialDrafts={((drafts.data?.items ?? []) as unknown) as ReceiptDraft[]}
        initialDraftId={initialDraftId ?? null}
        ledgers={(ledgers.data ?? []).map((l) => ({ id: l.id, label: l.name }))}
        accounts={accounts}
      />
    </div>
  );
}
