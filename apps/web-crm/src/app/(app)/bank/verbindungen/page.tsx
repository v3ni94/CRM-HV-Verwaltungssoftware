import { getTranslations } from "next-intl/server";
import Link from "next/link";

import {
  FinapiConnections,
  type FetchRun,
  type FinapiConnection,
  type InternalAccountOption,
} from "@/components/banking/FinapiConnections";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function FinapiPage() {
  const t = await getTranslations("BankFinapi");
  const api = serverApi();
  const status = await api.GET("/api/v1/banking/finapi/status");
  redirectIfUnauthenticated(status.response);
  const configured = Boolean(
    (status.data as { configured?: boolean } | undefined)?.configured ?? false,
  );

  let connections: FinapiConnection[] = [];
  let awaitingRuns: FetchRun[] = [];
  const accountOptions: InternalAccountOption[] = [];
  if (configured) {
    const [connectionsRes, runsRes, propertiesRes] = await Promise.all([
      api.GET("/api/v1/banking/connections"),
      api.GET("/api/v1/banking/finapi/runs", { params: { query: { limit: 20 } } }),
      api.GET("/api/v1/properties", { params: { query: { page_size: 200 } } }),
    ]);
    connections = ((connectionsRes.data ?? []) as FinapiConnection[]).filter(
      (c) => (c as { connector?: string }).connector === "aggregator_finapi",
    );
    awaitingRuns = ((runsRes.data ?? []) as unknown as FetchRun[]).filter(
      (r) => r.fetch_status === "awaiting_authorization",
    );
    const properties = propertiesRes.data?.items ?? [];
    const accountLists = await Promise.all(
      properties.map((p) =>
        api.GET("/api/v1/properties/{property_id}/bank-accounts", {
          params: { path: { property_id: p.id } },
        }),
      ),
    );
    properties.forEach((p, index) => {
      for (const account of (accountLists[index]?.data ?? []) as {
        id: string;
        iban_masked: string;
        kind: string;
        holder: string;
      }[]) {
        accountOptions.push({
          id: account.id,
          label: `${p.number} ${p.name} · ${account.iban_masked} (${account.kind})`,
        });
      }
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className={ui.title}>{t("title")}</h1>
      <p className={ui.notice}>{t("notice")}</p>
      <p className="text-sm">
        <Link href="/bank/abrufe" className="font-medium hover:underline">
          {t("logsLink")}
        </Link>
      </p>
      <FinapiConnections
        configured={configured}
        connections={connections}
        awaitingRuns={awaitingRuns}
        accountOptions={accountOptions}
      />
    </div>
  );
}
