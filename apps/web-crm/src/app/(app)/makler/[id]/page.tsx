import { notFound } from "next/navigation";

import { ListingDetail, type Listing } from "@/components/letting/ListingDetail";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function ListingDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const api = serverApi();
  const { data, error, response } = await api.GET("/api/v1/letting/listings/{listing_id}", {
    params: { path: { listing_id: id } },
  });
  redirectIfUnauthenticated(response);
  if (response.status === 404) notFound();
  if (!data) throw new Error(String(error));
  return (
    <div className="flex flex-col gap-5">
      <h1 className={ui.title}>{(data as unknown as Listing).title}</h1>
      <ListingDetail listing={data as unknown as Listing} />
    </div>
  );
}
