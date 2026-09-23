import { notFound } from "next/navigation";

import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function loadContact(id: string) {
  if (!UUID.test(id)) notFound();
  const { data, response } = await serverApi().GET("/api/v1/contacts/{contact_id}", {
    params: { path: { contact_id: id } },
  });
  redirectIfUnauthenticated(response);
  if (response.status === 404 || !data) notFound();
  return data;
}
