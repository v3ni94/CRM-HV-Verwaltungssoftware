"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { type Transmission } from "@/lib/metering";
import { ui } from "@/lib/ui";

/** Central overview of the controlled transmissions (master prompt Messdienstleister
 *  sections 6 and 12): every kind with its status, the Ordnungsbegriffsabgleich with its
 *  asynchronous provider processing ("waiting_provider" until the result is fetched). The
 *  overview offers the read only status fetch; checks, releases and orders stay in the object
 *  tab where the data set is shown in full. */

const STATUS_VARIANT: Record<string, "success" | "danger" | "warning" | "neutral"> = {
  checked: "neutral",
  invalid: "danger",
  released: "warning",
  superseded: "neutral",
  ordered: "success",
  rejected: "danger",
  unclear: "warning",
  failed: "danger",
  waiting_provider: "warning",
  completed: "success",
};

export function TransmissionsOverview({ canPoll, reloadKey = 0 }: { canPoll: boolean; reloadKey?: number }) {
  const t = useTranslations("Metering");
  const [rows, setRows] = useState<Transmission[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const res = await bff<Transmission[]>("/api/bff/metering/transmissions?limit=50");
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }, []);

  useEffect(() => {
    void load();
  }, [load, reloadKey]);

  async function poll(row: Transmission) {
    setBusy(true);
    setError(null);
    const res = await bff<Transmission>(`/api/bff/metering/transmissions/${row.id}/poll`, { method: "POST" });
    setBusy(false);
    if (!res.ok) setError(res.message);
    await load();
  }

  return (
    <section className="flex flex-col gap-3" data-testid="transmissions-overview">
      <h2 className={ui.h2}>{t("transmission.overviewTitle")}</h2>
      <p className={ui.help}>{t("transmission.overviewIntro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{t("transmission.overviewEmpty")}</p>
      ) : (
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("transmission.overviewKind")}</th>
              <th>{t("transmission.overviewAssignment")}</th>
              <th>{t("transmission.overviewCreated")}</th>
              <th>{t("table.status")}</th>
              <th>{t("transmission.transaction")}</th>
              {canPoll ? <th /> : null}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} data-testid={`overview-${row.kind}-${row.status}`}>
                <td>{t(`transmission.kind.${row.kind}`)}</td>
                <td className="font-mono text-xs">
                  {String(row.payload.billingunit ?? "")} <span className="text-muted">{row.property_assignment_id.slice(0, 8)}</span>
                </td>
                <td className="tabular-nums">{formatDateTime(row.created_at)}</td>
                <td>
                  <StatusPill variant={STATUS_VARIANT[row.status] ?? "neutral"} label={t(`transmission.status.${row.status}`)} />
                </td>
                <td className="font-mono text-xs">{row.provider_transaction_id ?? ""}</td>
                {canPoll ? (
                  <td>
                    {row.kind === "billing_unit_setup" && row.status === "waiting_provider" ? (
                      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => poll(row)} data-testid={`overview-poll-${row.id}`}>
                        {t("transmission.poll")}
                      </button>
                    ) : null}
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
