import { ProviderInfo, type AvailabilityWindow, type FrameworkContract } from "@/components/portal/ProviderInfo";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";

export const dynamic = "force-dynamic";

/** Rahmenverträge und Verfügbarkeitskalender (GA11-04, Dienstleister, nur lesend). */
export default async function FrameworkContractsPage() {
  const api = serverApi();
  const [contracts, windows] = await Promise.all([
    api.GET("/api/v1/portal/provider/framework-contracts"),
    api.GET("/api/v1/portal/provider/availability"),
  ]);
  redirectIfUnauthenticated(contracts.response);
  redirectIfUnauthenticated(windows.response);
  if (!contracts.data || !windows.data) throw new Error(String(contracts.error ?? windows.error));
  return (
    <ProviderInfo
      contracts={contracts.data as FrameworkContract[]}
      windows={windows.data as AvailabilityWindow[]}
    />
  );
}
