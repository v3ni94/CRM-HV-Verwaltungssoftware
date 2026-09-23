import { serverApi } from "@/lib/api-server";

/** HOA context of a property: the community legal entity, its ledger and allocation keys. */
export async function hoaContext(propertyId: string) {
  const api = serverApi();
  const [prop, ledgers, keys] = await Promise.all([
    api.GET("/api/v1/properties/{property_id}", { params: { path: { property_id: propertyId } } }),
    api.GET("/api/v1/accounting/ledgers"),
    api.GET("/api/v1/properties/{property_id}/allocation-keys", { params: { path: { property_id: propertyId } } }),
  ]);
  const entity = prop.data?.legal_entities?.find((e) => e.kind === "hoa") ?? null;
  const ledger = entity ? (ledgers.data ?? []).find((l) => l.legal_entity_id === entity.id) ?? null : null;
  return {
    api,
    response: prop.response,
    property: prop.data ?? null,
    entity,
    ledger,
    keys: ((keys.data ?? []) as { id: string; code: string; name: string }[]).map((k) => ({ id: k.id, code: k.code, name: k.name })),
  };
}
