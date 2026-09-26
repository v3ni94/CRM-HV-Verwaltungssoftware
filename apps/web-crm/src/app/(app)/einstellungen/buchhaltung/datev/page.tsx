import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { DatevMappingsAdmin, type DatevMapping, type LedgerOption } from "@/components/settings/DatevMappingsAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

async function getJson<T>(path: string, fallback: T): Promise<T> {
  const res = await serverFetch(path);
  if (!res.ok) return fallback;
  return (await res.json()) as T;
}

/** Einstellungen, Buchhaltung, DATEV (A36, M18-01): Kontenzuordnung CRM-Konto zu DATEV-Sachkonto
 *  je Mandant, CSV-Import mit Vorschau und Prüfbericht nicht zugeordneter Konten. Pflege nur mit
 *  accounting:update, Bericht mit accounting:read. */
export default async function DatevMappingsPage() {
  const t = await getTranslations("DatevMappings");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("accounting:read")) notFound();
  const canManage = permissions.includes("accounting:update");
  const [mappings, ledgers] = await Promise.all([
    getJson<DatevMapping[]>("/api/v1/accounting/datev-mappings?include_inactive=true", []),
    getJson<LedgerOption[]>("/api/v1/accounting/ledgers", []),
  ]);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("description")} />
      <DatevMappingsAdmin
        initial={mappings}
        ledgers={ledgers.map((l) => ({ id: l.id, name: l.name }))}
        canManage={canManage}
      />
    </div>
  );
}
