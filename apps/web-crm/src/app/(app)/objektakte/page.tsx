import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { AiCostSummary } from "@/components/objektakte/AiCostSummary";
import { ObjektakteLists, type PropertyOption } from "@/components/objektakte/ObjektakteLists";
import { ReviewCenter, type CategoryOption } from "@/components/objektakte/ReviewCenter";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";

export const dynamic = "force-dynamic";

/** M35 Stufe 3 part 5: Objektakte-Menüpunkt, Review-Center-Oberfläche (Auftragsteil 3 der
 * Klassifikation, verlinkt Kandidaten und "KI fragen" aus Auftragsteil 2). Stufe 4: darunter die
 * Listengenerierung (Anforderungslisten, Dokumentenübersicht, CSV) und die Kostenauswertung des
 * übernommenen KI-Protokolls je Objekt und Monat. */
export default async function ObjektaktePage() {
  const t = await getTranslations("Objektakte");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("objektakte:read")) notFound();

  const [categoriesRes, propertiesRes] = await Promise.all([
    api.GET("/api/v1/document-categories"),
    api.GET("/api/v1/properties", { params: { query: { page_size: 200 } } }),
  ]);
  const categories = (categoriesRes.data ?? []) as CategoryOption[];
  const properties: PropertyOption[] = (propertiesRes.data?.items ?? []).map((p) => ({
    id: p.id,
    number: p.number,
    name: p.name,
  }));

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      <ReviewCenter categories={categories} />
      <ObjektakteLists properties={properties} />
      <AiCostSummary properties={properties} />
    </div>
  );
}
