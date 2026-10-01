import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { AdminFeePostingConfigForm, type PostingConfig } from "@/components/accounting/AdminFeePostingConfigForm";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

type LedgerRow = { id: string; name: string; legal_entity_id: string };
type EntityRow = { id: string; kind: string };

async function getJson<T>(path: string, fallback: T): Promise<T> {
  const res = await serverFetch(path);
  if (!res.ok) return fallback;
  return ((await res.json()) as T | null) ?? fallback;
}

/** Einstellungen, Buchhaltung, Honorarbuchung (M13-07, T04-Rest): Kontenzuordnung des Honorars
 *  je Mandant, `GET/PUT /accounting/admin-fee-posting-config`. Lesen mit accounting:read,
 *  Speichern mit accounting:approve. Die Auswahl der Buchungskreise zeigt nur Verwalter-
 *  Rechtsträger, sofern die Rechtsträgerliste lesbar ist (members:read); sonst prüft die API. */
export default async function AdminFeePostingConfigPage() {
  const t = await getTranslations("AdminFeePostingConfig");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("accounting:read")) notFound();
  const [ledgers, entities, config] = await Promise.all([
    getJson<LedgerRow[]>("/api/v1/accounting/ledgers", []),
    getJson<EntityRow[]>("/api/v1/tenant/legal-entities", []),
    getJson<PostingConfig | null>("/api/v1/accounting/admin-fee-posting-config", null),
  ]);
  const managerIds = new Set(entities.filter((e) => e.kind === "manager").map((e) => e.id));
  const filtered = managerIds.size > 0 ? ledgers.filter((l) => managerIds.has(l.legal_entity_id)) : ledgers;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("pageTitle")} description={t("pageDescription")} />
      <AdminFeePostingConfigForm
        ledgers={filtered.map((l) => ({ id: l.id, label: l.name }))}
        initial={config}
        canUpdate={permissions.includes("accounting:approve")}
      />
    </div>
  );
}
