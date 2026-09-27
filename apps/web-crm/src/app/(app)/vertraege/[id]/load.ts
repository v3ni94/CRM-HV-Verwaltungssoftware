import type { AllocationKeyOption, AllocationValueOut } from "@/components/contracts/ContractAllocationValues";
import type { TerminationReadingOut } from "@/components/contracts/ContractDebtorAccount";
import type { ContractOut, MeterOption } from "@/components/contracts/ContractForm";
import type { MandateOut } from "@/components/contracts/ContractMandates";
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
  const [party, property, units, valuesRes, keysRes, mandatesRes, ledgersRes, metersRes, readingsRes] = await Promise.all([
    serverFetch(`/api/v1/contacts/${contract.party_id}/name`),
    serverFetch(`/api/v1/properties/${contract.property_id}`),
    serverFetch(`/api/v1/properties/${contract.property_id}/units`),
    // P1 (4.5): Eigenschaften, Mandate, Debitorenkonto und Zählerstände der Beendigung.
    serverFetch(`/api/v1/contracts/${id}/allocation-values`),
    serverFetch(`/api/v1/properties/${contract.property_id}/allocation-keys`),
    serverFetch(`/api/v1/sepa-mandates?party_id=${contract.party_id}&limit=200`),
    serverFetch("/api/v1/accounting/ledgers"),
    serverFetch(`/api/v1/properties/${contract.property_id}/meters`),
    serverFetch(`/api/v1/contracts/${id}/termination-readings`),
  ]);
  const allocationValues = valuesRes.ok ? ((await valuesRes.json()) as AllocationValueOut[]) : [];
  const allocationKeys = keysRes.ok ? ((await keysRes.json()) as AllocationKeyOption[]) : [];
  const mandates = mandatesRes.ok ? ((await mandatesRes.json()) as MandateOut[]) : [];
  const ledgers = ledgersRes.ok ? ((await ledgersRes.json()) as { id: string; legal_entity_id: string; name: string }[]) : [];
  const ledger = ledgers.find((l) => l.legal_entity_id === contract.legal_entity_id) ?? null;
  const allMeters = metersRes.ok ? ((await metersRes.json()) as MeterOption[]) : [];
  // Zähler der Einheit und gemeinsame Zähler ohne Einheit (Beendigung mit Zählerständen).
  const meters = allMeters.filter((m) => m.unit_id === contract.unit_id || m.unit_id === null);
  const meterLabels = Object.fromEntries(allMeters.map((m) => [m.id, `${m.number} (${m.meter_type_code})`]));
  const terminationReadings = readingsRes.ok ? ((await readingsRes.json()) as TerminationReadingOut[]) : [];
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
    allocationValues,
    allocationKeys,
    mandates,
    ledger,
    meters,
    meterLabels,
    terminationReadings,
    deposits,
    settlements,
    rates,
    partyName,
    propertyLabel: prop ? `${prop.number} ${prop.name}` : contract.property_id,
    unitLabel: unit ? `${unit.number}${unit.label ? ` ${unit.label}` : ""}` : contract.unit_id,
  };
}
