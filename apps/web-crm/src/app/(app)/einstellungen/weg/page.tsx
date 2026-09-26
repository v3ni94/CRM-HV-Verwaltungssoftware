import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { MajorityRulesAdmin, type HoaEntity, type SubjectRule } from "@/components/settings/MajorityRulesAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

async function getJson<T>(path: string, fallback: T): Promise<T> {
  const res = await serverFetch(path);
  if (!res.ok) return fallback;
  return (await res.json()) as T;
}

/** Einstellungen, WEG (M25-01): Mehrheitsregeln je Beschlussgegenstand. Bearbeiten nur mit
 *  accounting:approve, sonst schreibgeschützt. */
export default async function HoaSettingsPage() {
  const t = await getTranslations("MajorityRules");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("accounting:read")) notFound();
  const [rules, entities] = await Promise.all([
    getJson<SubjectRule[]>("/api/v1/hoa/majority-rules/subject-rules", []),
    getJson<(HoaEntity & { kind: string })[]>("/api/v1/tenant/legal-entities", []),
  ]);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      <MajorityRulesAdmin
        rules={rules}
        entities={entities.filter((e) => e.kind === "hoa").map((e) => ({ id: e.id, name: e.name }))}
        canManage={permissions.includes("accounting:approve")}
      />
    </div>
  );
}
