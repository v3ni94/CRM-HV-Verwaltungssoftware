import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { ReviewCenter, type CategoryOption } from "@/components/objektakte/ReviewCenter";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";

export const dynamic = "force-dynamic";

/** M35 Stufe 3 part 5: Objektakte-Menüpunkt, Review-Center-Oberfläche (Auftragsteil 3 der
 * Klassifikation, verlinkt Kandidaten und "KI fragen" aus Auftragsteil 2). */
export default async function ObjektaktePage() {
  const t = await getTranslations("Objektakte");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("documents:read")) notFound();

  const categoriesRes = await api.GET("/api/v1/document-categories");
  const categories = (categoriesRes.data ?? []) as CategoryOption[];

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      <ReviewCenter categories={categories} />
    </div>
  );
}
