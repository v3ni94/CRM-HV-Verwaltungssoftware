import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import {
  CustomFieldsAdmin,
  type CustomField,
  type FieldTypeOption,
} from "@/components/settings/CustomFieldsAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

async function getJson<T>(path: string, fallback: T): Promise<T> {
  const res = await serverFetch(path);
  if (!res.ok) return fallback;
  return (await res.json()) as T;
}

/** Einstellungen, benutzerdefinierte Felder (P1 AP4, 4.11): Definitionen je Entität mit den
 *  Feldtypen nach Anhang B.28. Lesen mit properties:read, Pflege mit tenant_settings:update. */
export default async function CustomFieldsSettingsPage() {
  const t = await getTranslations("Settings.customFields");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("properties:read")) notFound();
  const [fields, fieldTypes] = await Promise.all([
    getJson<CustomField[]>("/api/v1/custom-fields", []),
    getJson<FieldTypeOption[]>("/api/v1/catalogs/custom_field_type", []),
  ]);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      <CustomFieldsAdmin
        fields={fields}
        fieldTypes={fieldTypes}
        canManage={permissions.includes("tenant_settings:update")}
      />
    </div>
  );
}
