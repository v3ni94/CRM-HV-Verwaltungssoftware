"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type ScaleTrigger = { key: string; kind: string; title: string; detail: string; value: number; threshold: number };
type TableRow = { table: string; rows: number; bytes: number; exact: boolean; rows_percent: number; size_percent: number };
type LatencyRow = { key: string; samples: number; p95_ms: number | null; threshold_ms: number };
export type ScaleSettings = {
  rows_threshold: number;
  size_gb_threshold: number;
  p95_ms_threshold: number;
  p95_deep_ms_threshold: number;
  p95_weeks: number;
  restore_seconds_threshold: number;
  tenants_review_threshold: number;
  alarm_enabled: boolean;
  version: number;
};
type HistoryRow = {
  iso_week: string;
  source: string;
  tables: Record<string, { rows: number; bytes: number }>;
  latency: Record<string, { p95_ms: number | null }>;
  triggers: string[];
};
export type ScaleView = {
  settings: ScaleSettings;
  tables: TableRow[];
  latency: LatencyRow[];
  min_samples: number;
  restore: { seconds: number | null; threshold_seconds: number };
  tenants: { productive: number; demo: number; review_threshold: number };
  triggers: ScaleTrigger[];
  history: HistoryRow[];
};

const GIB = 1024 ** 3;
const MIB = 1024 ** 2;

/** Whole numbers with German thousands separators. */
export function formatCount(value: number): string {
  return value.toLocaleString("de-DE");
}

/** Table size for display (GB from one gibibyte on, else MB), one decimal place. */
export function formatBytes(bytes: number): string {
  if (bytes >= GIB) return `${(bytes / GIB).toLocaleString("de-DE", { maximumFractionDigits: 1 })} GB`;
  return `${(bytes / MIB).toLocaleString("de-DE", { maximumFractionDigits: 1 })} MB`;
}

/** P95 for display; no figure while the sample basis is too small. */
export function formatMs(value: number | null): string {
  return value === null ? "-" : `${value.toLocaleString("de-DE", { maximumFractionDigits: 0 })} ms`;
}

/** Share of the threshold in percent for display (one decimal place, German comma). */
export function formatPercent(value: number): string {
  return `${value.toLocaleString("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`;
}

type FormState = Record<Exclude<keyof ScaleSettings, "alarm_enabled" | "version">, string> & { alarm_enabled: boolean };

function toForm(settings: ScaleSettings): FormState {
  return {
    rows_threshold: String(settings.rows_threshold),
    size_gb_threshold: String(settings.size_gb_threshold),
    p95_ms_threshold: String(settings.p95_ms_threshold),
    p95_deep_ms_threshold: String(settings.p95_deep_ms_threshold),
    p95_weeks: String(settings.p95_weeks),
    restore_seconds_threshold: String(settings.restore_seconds_threshold),
    tenants_review_threshold: String(settings.tenants_review_threshold),
    alarm_enabled: settings.alarm_enabled,
  };
}

/** Body of the settings change: only the fields that differ from the stored ones. */
export function changedSettings(form: FormState, settings: ScaleSettings): Record<string, number | boolean> {
  const out: Record<string, number | boolean> = {};
  for (const key of Object.keys(form) as (keyof FormState)[]) {
    if (key === "alarm_enabled") {
      if (form.alarm_enabled !== settings.alarm_enabled) out.alarm_enabled = form.alarm_enabled;
      continue;
    }
    const value = Number(form[key]);
    if (Number.isFinite(value) && value !== settings[key]) out[key] = value;
  }
  return out;
}

/** AE36 (AC09-01, ADR 0021): triggers of the yearly partitioning as platform figures. The page
 *  only reports; nothing is rebuilt, moved or deleted. */
export function ScaleMonitor() {
  const t = useTranslations("AE36");
  const [view, setView] = useState<ScaleView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const res = await bff<ScaleView>("/api/bff/platform/ops/scale");
    if (res.ok) {
      setView(res.data);
      setForm(toForm(res.data.settings));
      setError(null);
    } else setError(res.message);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!view || !form) return;
    const body = changedSettings(form, view.settings);
    if (Object.keys(body).length === 0) {
      setMessage(t("nothingChanged"));
      return;
    }
    setBusy(true);
    const res = await bff("/api/bff/platform/ops/scale/settings", { method: "PATCH", body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) {
      setMessage(t("saved"));
      await load();
    } else setError(res.message);
  }

  async function snapshot() {
    setBusy(true);
    const res = await bff<{ iso_week: string; new_triggers: string[] }>("/api/bff/platform/ops/scale/snapshot", { method: "POST" });
    setBusy(false);
    if (res.ok) {
      setMessage(t("snapshotDone", { week: res.data.iso_week, count: res.data.new_triggers.length }));
      await load();
    } else setError(res.message);
  }

  const kindLabel = (kind: string) => (kind === "measure_again" ? t("kind.measure_again") : t("kind.partition_review"));
  const latencyLabel = (key: string) => t(`latency.${key}`);
  const field = (key: keyof FormState, label: string, help?: string) =>
    form ? (
      <label className="block" key={key}>
        <span className={ui.label}>{label}</span>
        <input
          className={ui.input}
          inputMode="numeric"
          value={String(form[key])}
          onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        />
        {help ? <span className={ui.help}>{help}</span> : null}
      </label>
    ) : null;

  return (
    <section className={ui.pageGap} aria-labelledby="ae36-title">
      <h2 id="ae36-title" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className={ui.notice}>{t("intro")}</p>
      {error ? <p className={ui.alert}>{error}</p> : null}
      {message ? (
        <p className={ui.success} role="status">
          {message}
        </p>
      ) : null}
      {view ? (
        <>
          <div className={ui.sectionGap}>
            <h3 className="text-base font-semibold">{t("triggersTitle")}</h3>
            {view.triggers.length === 0 ? (
              <p className={ui.info}>{t("noTrigger")}</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {view.triggers.map((trigger) => (
                  <li key={trigger.key} className={ui.warning}>
                    <span className={ui.badgeWarning}>{kindLabel(trigger.kind)}</span> <strong>{trigger.title}</strong>
                    <span className="block">{trigger.detail}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className={ui.sectionGap}>
            <h3 className="text-base font-semibold">{t("tablesTitle")}</h3>
            <div className={ui.tableScroll}>
              <table className={ui.table}>
                <thead>
                  <tr>
                    <th>{t("table")}</th>
                    <th>{t("rows")}</th>
                    <th>{t("rowsShare", { limit: formatCount(view.settings.rows_threshold) })}</th>
                    <th>{t("size")}</th>
                    <th>{t("sizeShare", { limit: view.settings.size_gb_threshold })}</th>
                    <th>{t("basis")}</th>
                  </tr>
                </thead>
                <tbody>
                  {view.tables.map((row) => (
                    <tr key={row.table}>
                      <td>{row.table}</td>
                      <td>{formatCount(row.rows)}</td>
                      <td>{formatPercent(row.rows_percent)}</td>
                      <td>{formatBytes(row.bytes)}</td>
                      <td>{formatPercent(row.size_percent)}</td>
                      <td>{row.exact ? t("exact") : t("estimate")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className={ui.sectionGap}>
            <h3 className="text-base font-semibold">{t("latencyTitle")}</h3>
            <p className={ui.help}>{t("latencyHelp", { min: view.min_samples })}</p>
            <div className={ui.tableScroll}>
              <table className={ui.table}>
                <thead>
                  <tr>
                    <th>{t("list")}</th>
                    <th>{t("samples")}</th>
                    <th>{t("p95")}</th>
                    <th>{t("limit")}</th>
                  </tr>
                </thead>
                <tbody>
                  {view.latency.map((row) => (
                    <tr key={row.key}>
                      <td>{latencyLabel(row.key)}</td>
                      <td>{formatCount(row.samples)}</td>
                      <td>{row.p95_ms === null ? t("tooFew") : formatMs(row.p95_ms)}</td>
                      <td>{formatMs(row.threshold_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              {t("restore", {
                value: view.restore.seconds === null ? t("noRestore") : `${formatCount(view.restore.seconds)} s`,
                limit: formatCount(view.restore.threshold_seconds),
              })}
            </p>
            <p>{t("tenants", { productive: view.tenants.productive, demo: view.tenants.demo, limit: view.tenants.review_threshold })}</p>
          </div>

          <div className={ui.sectionGap}>
            <h3 className="text-base font-semibold">{t("historyTitle")}</h3>
            {view.history.length === 0 ? (
              <p className={ui.help}>{t("noHistory")}</p>
            ) : (
              <div className={ui.tableScroll}>
                <table className={ui.table}>
                  <thead>
                    <tr>
                      <th>{t("week")}</th>
                      <th>journal_line</th>
                      <th>bank_transaction</th>
                      <th>{latencyLabel("journal_list")}</th>
                      <th>{latencyLabel("bank_list")}</th>
                      <th>{t("triggersTitle")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {view.history.map((row) => (
                      <tr key={row.iso_week}>
                        <td>{row.iso_week}</td>
                        <td>{formatCount(row.tables.journal_line?.rows ?? 0)}</td>
                        <td>{formatCount(row.tables.bank_transaction?.rows ?? 0)}</td>
                        <td>{formatMs(row.latency.journal_list?.p95_ms ?? null)}</td>
                        <td>{formatMs(row.latency.bank_list?.p95_ms ?? null)}</td>
                        <td>{row.triggers.length === 0 ? "-" : row.triggers.join(", ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div>
              <button type="button" className={ui.secondary} disabled={busy} onClick={() => void snapshot()}>
                {t("snapshot")}
              </button>
              <p className={ui.help}>{t("snapshotHelp")}</p>
            </div>
          </div>

          {form ? (
            <form onSubmit={(e) => void save(e)} className={`${ui.card} grid gap-3 sm:grid-cols-2`}>
              <h3 className="text-base font-semibold sm:col-span-2">{t("settingsTitle")}</h3>
              <p className={`${ui.help} sm:col-span-2`}>{t("settingsHelp")}</p>
              {field("rows_threshold", t("fields.rows"))}
              {field("size_gb_threshold", t("fields.size"))}
              {field("p95_ms_threshold", t("fields.p95"))}
              {field("p95_deep_ms_threshold", t("fields.p95Deep"))}
              {field("p95_weeks", t("fields.weeks"))}
              {field("restore_seconds_threshold", t("fields.restore"), t("fields.restoreHelp"))}
              {field("tenants_review_threshold", t("fields.tenants"))}
              <label className="flex items-center gap-2 sm:col-span-2">
                <input
                  type="checkbox"
                  checked={form.alarm_enabled}
                  onChange={(e) => setForm({ ...form, alarm_enabled: e.target.checked })}
                />
                <span>{t("fields.alarm")}</span>
              </label>
              <div className="sm:col-span-2">
                <button type="submit" className={ui.primary} disabled={busy}>
                  {t("save")}
                </button>
              </div>
            </form>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
