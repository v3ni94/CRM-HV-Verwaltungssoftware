import type { RetentionProfileOption } from "@/components/contacts/ContactForm";
import { serverApi } from "@/lib/api-server";

/** Released retention profiles of the tenant for the deletion reservation on a contact (4.1).
 *  Drafts are not offered; the API rejects them anyway. */
export async function loadRetentionProfiles(): Promise<RetentionProfileOption[]> {
  const { data } = await serverApi().GET("/api/v1/retention-profiles");
  return (data ?? [])
    .filter((p) => p.status === "freigegeben")
    .map((p) => ({ id: p.id, document_class: p.document_class, legal_entity_kind: p.legal_entity_kind ?? null }));
}
