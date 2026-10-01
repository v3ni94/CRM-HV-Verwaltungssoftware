"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import {
  StatementStatusActions,
  type StatementStatusValue,
  type StatusLogEntry,
} from "@/components/billing/StatementStatusActions";
import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type ReserveStatement = {
  id: string;
  ledger_id: string;
  hoa_statement_id: string;
  year: number;
  status: StatementStatusValue;
  snapshot: {
    reserve?: Record<string, unknown>;
    positions?: { reserve_id: string; name: string; planned_change?: string }[];
  } | null;
  source_snapshot_hash: string | null;
  status_log?: StatusLogEntry[];
};

const BASE = "/api/bff/hoa/reserve-statements";
const AMOUNTS = [
  "opening",
  "contributions_resolved",
  "contributions_paid",
  "withdrawals",
  "interest",
  "closing",
  "bank_balance",
] as const;

/** Rücklagenabrechnung je Jahr (S69-01): eigenes Abrechnungsobjekt mit dem einheitlichen
 *  Statusmodell, erzeugt aus den Rücklagendaten der berechneten Hausgeldabrechnung. */
export function ReserveStatementPanel({
  ledgerId,
  hoaStatementId,
}: {
  ledgerId: string;
  hoaStatementId: string | null;
}) {
  const t = useTranslations("HoaReserveStatement");
  const ts = useTranslations("StatementStatus");
  const [list, setList] = useState<ReserveStatement[]>([]);
  const [selected, setSelected] = useState<ReserveStatement | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<ReserveStatement[]>(`${BASE}?ledger_id=${ledgerId}`);
    if (res.ok) {
      setList(res.data);
      setSelected(
        (cur) => res.data.find((r) => r.id === cur?.id) ?? res.data[0] ?? null,
      );
    } else setError(res.message);
  }, [ledgerId]);
  useEffect(() => {
    void load();
  }, [load]);

  const call = async (path: string, body?: unknown) => {
    setBusy(true);
    setError(null);
    const res = await bff<ReserveStatement>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
    setBusy(false);
    if (res.ok) {
      setSelected(res.data);
      await load();
    } else setError(res.message);
  };

  const reserve = selected?.snapshot?.reserve ?? null;
  return (
    <section className="flex flex-col gap-2" aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.help}>{t("hint")}</p>
      {hoaStatementId ? (
        <div>
          <button
            type="button"
            className={ui.secondary}
            disabled={busy}
            onClick={() => call(BASE, { hoa_statement_id: hoaStatementId })}
          >
            {t("create")}
          </button>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {list.length === 0 ? (
        <p className="text-sm text-muted">{t("none")}</p>
      ) : null}
      {list.length > 1 ? (
        <ul className="flex flex-wrap gap-2 text-sm">
          {list.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                className="hover:underline"
                onClick={() => setSelected(r)}
              >
                {r.year}, {ts(`status.${r.status}`)}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {selected ? (
        <div className={ui.card} data-testid="reserve-statement">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className={ui.subtitle}>
              {t("detail", { year: selected.year })}
            </h3>
            <span className={ui.badge}>{ts(`status.${selected.status}`)}</span>
          </div>
          {selected.status === "draft" || selected.status === "calculated" ? (
            <button
              type="button"
              className={`${ui.secondary} mt-2`}
              disabled={busy}
              onClick={() => call(`${BASE}/${selected.id}/calculate`)}
            >
              {t("calculate")}
            </button>
          ) : null}
          {reserve ? (
            <div className={ui.tableScroll}>
              <table className="mhvp-table mt-2">
                <tbody>
                  {AMOUNTS.filter((k) => typeof reserve[k] === "string").map(
                    (k) => (
                      <tr key={k}>
                        <td>{t(`amounts.${k}`)}</td>
                        <td className="num">
                          {formatEur(reserve[k] as string)}
                        </td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="mt-2 text-sm text-muted">{t("notCalculated")}</p>
          )}
          {selected.status !== "draft" ? (
            <StatementStatusActions<ReserveStatement>
              url={`${BASE}/${selected.id}`}
              status={selected.status}
              hoa
              gate="G4"
              log={selected.status_log ?? []}
              onChanged={(data) => {
                setSelected(data);
                void load();
              }}
            />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
