import type { ContractOut } from "@/components/contracts/ContractForm";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";

/** Loads a contract with the display names of party, property and unit for the detail and
 *  edit pages (server side, per request). */
export async function loadContractContext(id: string) {
  const response = await serverFetch(`/api/v1/contracts/${id}`);
  redirectIfUnauthenticated(response);
  if (!response.ok) return null;
  const contract = (await response.json()) as ContractOut;
  const [party, property, units] = await Promise.all([
    serverFetch(`/api/v1/contacts/${contract.party_id}/name`),
    serverFetch(`/api/v1/properties/${contract.property_id}`),
    serverFetch(`/api/v1/properties/${contract.property_id}/units`),
  ]);
  const partyName = party.ok ? ((await party.json()) as { display_name: string }).display_name : contract.party_id;
  const prop = property.ok ? ((await property.json()) as { number: string; name: string }) : null;
  const unit = units.ok ? ((await units.json()) as { id: string; number: string; label: string | null }[]).find((u) => u.id === contract.unit_id) : undefined;
  return {
    contract,
    partyName,
    propertyLabel: prop ? `${prop.number} ${prop.name}` : contract.property_id,
    unitLabel: unit ? `${unit.number}${unit.label ? ` ${unit.label}` : ""}` : contract.unit_id,
  };
}
