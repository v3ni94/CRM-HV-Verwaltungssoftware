import { getTranslations } from "next-intl/server";

import { SerialDispatchForm } from "@/components/contacts/SerialDispatchForm";
import { PageHeader } from "@/components/ui/PageHeader";
import { serverFetch } from "@/lib/api-server";
import { problemMessage } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Template = { id: string; name: string; active?: boolean };

export default async function SerialDispatchPage() {
  const t = await getTranslations("SerialDispatchPage");
  const res = await serverFetch("/api/v1/document-templates");
  const templates: Template[] = res.ok ? ((await res.json()) as Template[]).filter((x) => x.active !== false) : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className="text-sm text-muted">{t("intro")}</p>
      {!res.ok ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(null, res.status)}
        </p>
      ) : (
        <SerialDispatchForm templates={templates.map((x) => ({ id: x.id, name: x.name }))} />
      )}
    </div>
  );
}
