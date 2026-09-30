import { getTranslations } from "next-intl/server";

import { AccountsManager, type ManagedAccount } from "@/components/accounting/AccountsManager";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Kontenplan des Buchungskreises (M10-03): ergänzen, ändern, deaktivieren, Kontenblatt. */
export default async function LedgerAccountsPage({ params }: { params: Promise<{ id: string }> }) {
  const [t, ta, { id }] = await Promise.all([getTranslations("Bookkeeping"), getTranslations("Accounting"), params]);
  const api = serverApi();
  const [ledger, accounts, me] = await Promise.all([
    api.GET("/api/v1/accounting/ledgers/{ledger_id}", { params: { path: { ledger_id: id } } }),
    api.GET("/api/v1/accounting/ledgers/{ledger_id}/accounts", { params: { path: { ledger_id: id } } }),
    getMe(),
  ]);
  redirectIfUnauthenticated(ledger.response);
  if (!ledger.data) {
    return (
      <p role="alert" className={ui.alert}>
        {problemMessage(ledger.error as Problem | undefined, ledger.response.status)}
      </p>
    );
  }
  const perms = me.data?.permissions ?? [];
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[
          { href: "/buchhaltung", label: ta("title") },
          { href: `/buchhaltung/${id}`, label: ledger.data.name },
        ]}
        title={t("accounts.title")}
        description={t("accounts.description")}
      />
      <AccountsManager
        ledgerId={id}
        accounts={(accounts.data ?? []) as unknown as ManagedAccount[]}
        canCreate={perms.includes("accounting:create")}
        canUpdate={perms.includes("accounting:update")}
      />
    </div>
  );
}
