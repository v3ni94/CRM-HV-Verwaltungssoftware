import type { ContractOut } from "@/components/contracts/ContractForm";
import type { DepositOut, DepositSettlementOut } from "@/components/contracts/DepositPanel";
import type { ReferenceRate } from "@/components/settings/DepositInterestRatesAdmin";
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
  // Kautionen (M5-02): only tenancies carry deposits; drafts and the reference rate table
  // feed the settlement form.
  let deposits: DepositOut[] = [];
  let rates: ReferenceRate[] = [];
  const settlements: Record<string, DepositSettlementOut[]> = {};
  if (contract.kind === "tenancy") {
    const [depositsRes, ratesRes] = await Promise.all([serverFetch(`/api/v1/contracts/${id}/deposits`), serverFetch("/api/v1/deposit-interest-rates")]);
    deposits = depositsRes.ok ? ((await depositsRes.json()) as DepositOut[]) : [];
    rates = ratesRes.ok ? ((await ratesRes.json()) as ReferenceRate[]) : [];
    await Promise.all(
      deposits.map(async (d) => {
        const res = await serverFetch(`/api/v1/deposits/${d.id}/settlements`);
        settlements[d.id] = res.ok ? ((await res.json()) as DepositSettlementOut[]) : [];
      }),
    );
  }
  return {
    contract,
    deposits,
    settlements,
    rates,
    partyName,
    propertyLabel: prop ? `${prop.number} ${prop.name}` : contract.property_id,
    unitLabel: unit ? `${unit.number}${unit.label ? ` ${unit.label}` : ""}` : contract.unit_id,
  };
}
