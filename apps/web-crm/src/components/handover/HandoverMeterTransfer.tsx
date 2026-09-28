"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import type { Item, MeterTransferResult } from "./types";

/** "Zählerstände übernehmen" (Package F, handbook Mieterwechsel step 2): after a confirmation
 *  the readings of the protocol become meter readings of the unit's meters, once per row. The
 *  server matches by meter or meter number and reports created, skipped and already taken
 *  over rows; nothing is created twice. */
export function HandoverMeterTransfer({
  base,
  meters,
  hasUnit,
  cancelled,
  onChanged,
  onError,
}: {
  base: string;
  meters: Item[];
  hasUnit: boolean;
  cancelled: boolean;
  onChanged: () => Promise<void>;
  onError: (m: string | null) => void;
}) {
  const t = useTranslations("Handover.meterTransfer");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<MeterTransferResult | null>(null);
  const open = meters.filter((m) => !m.meter_reading_id).length;
  const done = meters.length - open;

  async function transfer() {
    if (!window.confirm(t("confirm", { count: open }))) return;
    setBusy(true);
    onError(null);
    setResult(null);
    const res = await bff<MeterTransferResult>(`${base}/meters/transfer`, {
      method: "POST",
      body: JSON.stringify({ confirm: true }),
    });
    setBusy(false);
    if (!res.ok) {
      onError(res.message);
      return;
    }
    setResult(res.data);
    await onChanged();
  }

  const label = (x: { number: string | null; meter_type: string }) => [x.meter_type, x.number ? `Nr. ${x.number}` : null].filter(Boolean).join(", ");

  return (
    <section className={`${ui.card} flex flex-col gap-2`} aria-label={t("title")} data-testid="handover-meter-transfer">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="text-sm text-muted">{t("help")}</p>
      <p className="text-sm">{t("state", { open, done })}</p>
      {!hasUnit ? <p className={ui.notice}>{t("needsUnit")}</p> : null}
      {cancelled ? <p className={ui.notice}>{t("cancelled")}</p> : null}
      <div>
        <button type="button" className={ui.button} disabled={busy || !hasUnit || cancelled || open === 0} onClick={() => void transfer()}>
          {t("action")}
        </button>
      </div>
      {result ? (
        <div className={ui.success} data-testid="handover-meter-transfer-result">
          <p>{t("result", { created: result.created.length, skipped: result.skipped.length, already: result.already_transferred.length })}</p>
          {result.created.length ? (
            <ul className="mt-1 list-disc pl-5">
              {result.created.map((x) => (
                <li key={x.item_id}>
                  {label(x)}: {x.value} {t("on")} {formatDate(x.read_at)} ({t("meter")} {x.meter_number})
                </li>
              ))}
            </ul>
          ) : null}
          {result.skipped.length ? (
            <ul className="mt-1 list-disc pl-5">
              {result.skipped.map((x) => (
                <li key={x.item_id}>
                  {label(x) || t("row")}: {t(`reasons.${x.reason}`)}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
