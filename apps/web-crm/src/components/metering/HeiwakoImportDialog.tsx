"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { type HeiwakoPreview, type MeteringConnection } from "@/lib/metering";
import { ui } from "@/lib/ui";

/** Providers whose connections use the bved 3.10 file exchange (HeiwakoFileAdapter). */
const FILE_EXCHANGE_PROVIDERS = new Set(["techem", "brunata_minol", "brunata_metrona"]);

export function isHeiwakoConnection(connection: MeteringConnection): boolean {
  return FILE_EXCHANGE_PROVIDERS.has(connection.provider_code);
}

/** Upload dialog for bved 3.10 Austauschdateien (M40-02): up to 10 files, optional
 *  period_from, preview only, nothing is stored. */
export function HeiwakoImportDialog({ connection, onClose }: { connection: MeteringConnection; onClose: () => void }) {
  const t = useTranslations("Metering.heiwako");
  const [files, setFiles] = useState<File[]>([]);
  const [periodFrom, setPeriodFrom] = useState("");
  const [preview, setPreview] = useState<HeiwakoPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    if (files.length === 0) return;
    if (files.length > 10) {
      setError(t("tooMany"));
      return;
    }
    setBusy(true);
    setError(null);
    const body = new FormData();
    for (const file of files) body.append("files", file);
    const query = periodFrom ? `?period_from=${encodeURIComponent(periodFrom)}` : "";
    const res = await bff<HeiwakoPreview>(`/api/bff/metering/connections/${connection.id}/heiwako-import/preview${query}`, {
      method: "POST",
      body,
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setPreview(res.data);
  }

  return (
    <div className={ui.card} data-testid="heiwako-import-dialog">
      <div className="flex items-center justify-between gap-2">
        <h3 className={ui.subtitle}>{t("title", { name: connection.display_name })}</h3>
        <button type="button" className={ui.buttonSm} onClick={onClose}>
          {t("close")}
        </button>
      </div>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      <div className="mt-3 flex flex-col gap-2">
        <input
          type="file"
          multiple
          accept=".txt,.dat,.csv"
          aria-label={t("files")}
          onChange={(e) => {
            setFiles(Array.from(e.target.files ?? []));
            setPreview(null);
            setError(null);
          }}
        />
        <label className="flex flex-col gap-1 text-sm">
          {t("periodFrom")}
          <input
            type="date"
            className={ui.input}
            value={periodFrom}
            onChange={(e) => setPeriodFrom(e.target.value)}
            aria-label={t("periodFrom")}
          />
        </label>
        <div>
          <button
            type="button"
            className={ui.primary}
            disabled={files.length === 0 || busy}
            onClick={run}
            data-testid="heiwako-preview-run"
          >
            {t("run")}
          </button>
        </div>
      </div>
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
      {preview ? (
        <div className="mt-3 flex flex-col gap-4" data-testid="heiwako-preview-report">
          <p className="text-sm">
            {t("summary", {
              properties: preview.property_count,
              references: preview.reference_count,
              billingResults: preview.billing_results.length,
              users: preview.users.length,
            })}
          </p>
          {preview.errors.length > 0 ? (
            <ul className="text-sm text-danger-fg">
              {preview.errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          ) : null}
          <div className="overflow-x-auto">
            <table className={ui.table} data-testid="heiwako-files-table">
              <thead>
                <tr>
                  <th>{t("file")}</th>
                  <th>{t("kind")}</th>
                  <th>{t("recordCounts")}</th>
                  <th>{t("errors")}</th>
                </tr>
              </thead>
              <tbody>
                {preview.files.map((f) => (
                  <tr key={f.name} data-testid={`heiwako-file-${f.name}`}>
                    <td className="font-mono text-xs">{f.name}</td>
                    <td>{f.kind ?? t("kindUnknown")}</td>
                    <td className="text-xs">
                      {Object.entries(f.record_counts)
                        .map(([k, v]) => `${k}=${v}`)
                        .join(" ")}
                    </td>
                    <td className="text-xs text-danger-fg">{f.errors.join("; ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="overflow-x-auto">
            <table className={ui.table} data-testid="heiwako-billing-table">
              <thead>
                <tr>
                  <th>{t("unit")}</th>
                  <th>{t("period")}</th>
                  <th>{t("amount")}</th>
                  <th>{t("balance")}</th>
                  <th>{t("prepayment")}</th>
                </tr>
              </thead>
              <tbody>
                {preview.billing_results.map((b, i) => (
                  <tr key={i} data-testid={`heiwako-billing-${i}`}>
                    <td className="font-mono text-xs">
                      {b.external_billing_unit}
                      {b.external_unit_number ? `/${b.external_unit_number}` : ""}
                    </td>
                    <td className="tabular-nums text-xs">
                      {b.period_from}–{b.period_to}
                    </td>
                    <td className="tabular-nums">
                      {b.amount} {b.currency}
                    </td>
                    <td className="tabular-nums">{b.balance_gross ?? "–"}</td>
                    <td className="tabular-nums">{b.prepayment_gross ?? "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
