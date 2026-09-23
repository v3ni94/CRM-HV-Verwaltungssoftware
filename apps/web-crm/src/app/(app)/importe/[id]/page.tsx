import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ImportResult } from "@/components/ai/ImportResult";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function ImportDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [{ id }, t] = await Promise.all([params, getTranslations("Imports")]);
  const api = serverApi();
  const [{ data, error, response }, me] = await Promise.all([
    api.GET("/api/v1/imports/{import_id}", { params: { path: { import_id: id } } }),
    api.GET("/api/v1/auth/me"),
  ]);
  redirectIfUnauthenticated(response);
  if (response.status === 404 || response.status === 422) notFound();
  return (
    <div className="flex flex-col gap-4">
      <Link href="/importe" className="text-sm underline">
        {t("back")}
      </Link>
      <h1 className="text-xl font-semibold">{t("detailTitle")}</h1>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : (
        <ImportResult importRun={data} canUndo={me.data?.permissions.includes("ai:delete") ?? false} />
      )}
    </div>
  );
}
