"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";

export type PeriodLockSettings = {
  lock_mode: "ledger_only" | "object_period";
  auto_lock_on_close: boolean;
  reopen_enabled: boolean;
};

export type PeriodLockRow = {
  id: string;
  ledger_id: string;
  property_id: string;
  period_from: string;
  period_to: string;
  source: "manual" | "statement" | "owner_statement";
  reason: string | null;
  active: boolean;
  release_requested_by: string | null;
  release_request_reason: string | null;
};

const BASE = "/api/bff/accounting/period-locks";

function formatDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
}

/** Periodensperren je Objekt und Zeitraum mit Schaltern (P06-02). Standard: nur Buchungskreis,
 *  keine automatische Sperre, keine Aufhebung. */
export function PeriodLockPanel({
  initialSettings,
  initialRows,
  canApprove,
  canSettings,
}: {
  initialSettings: PeriodLockSettings | null;
  initialRows: PeriodLockRow[];
  canApprove: boolean;
  canSettings: boolean;
}) {
  const t = useTranslations("PeriodLocks");
  const [settings, setSettings] = useState<PeriodLockSettings>(
    initialSettings ?? { lock_mode: "ledger_only", auto_lock_on_close: false, reopen_enabled: false },
  );
  const [rows, setRows] = useState<PeriodLockRow[]>(initialRows);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState({ ledger_id: "", property_id: "", period_from: "", period_to: "", reason: "" });
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function reload() {
    const res = await bff<PeriodLockRow[]>(BASE);
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }

  async function saveSettings(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    const res = await bff<PeriodLockSettings>(`${BASE}/settings`, { method: "PUT", body: JSON.stringify(settings) });
    setBusy(false);
    if (res.ok) {
      setSettings(res.data);
      setMessage(t("saved"));
    } else setError(res.message);
  }

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    const res = await bff<PeriodLockRow>(BASE, { method: "POST", body: JSON.stringify(form) });
    setBusy(false);
    if (res.ok) {
      setMessage(t("created"));
      await reload();
    } else setError(res.message);
  }

  async function act(id: string, action: "release-request" | "release") {
    if (busy) return;
    setBusy(true);
    setError(null);
    const res = await bff<PeriodLockRow>(`${BASE}/${id}/${action}`, {
      method: "POST",
      body: JSON.stringify({ reason: reasons[id] ?? "" }),
    });
    setBusy(false);
    if (res.ok) {
      setMessage(t("done"));
      await reload();
    } else setError(res.message);
  }

  const sourceLabel = (s: PeriodLockRow["source"]) =>
    s === "manual" ? t("sourceManual") : s === "statement" ? t("sourceStatement") : t("sourceOwnerStatement");

  return (
    <div className="flex flex-col gap-6">
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      {message ? <p role="status" className="text-sm">{message}</p> : null}

      <form onSubmit={saveSettings} className="flex flex-col gap-3">
        <h2 className="text-base font-medium">{t("settingsTitle")}</h2>
        <label className="flex flex-col gap-1 text-sm">
          {t("lockMode")}
          <select
            value={settings.lock_mode}
            disabled={!canSettings}
            onChange={(e) => setSettings({ ...settings, lock_mode: e.target.value as PeriodLockSettings["lock_mode"] })}
          >
            <option value="ledger_only">{t("modeLedger")}</option>
            <option value="object_period">{t("modeObject")}</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={settings.auto_lock_on_close}
            disabled={!canSettings}
            onChange={(e) => setSettings({ ...settings, auto_lock_on_close: e.target.checked })}
          />
          {t("autoLock")}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={settings.reopen_enabled}
            disabled={!canSettings}
            onChange={(e) => setSettings({ ...settings, reopen_enabled: e.target.checked })}
          />
          {t("reopen")}
        </label>
        {canSettings ? <button type="submit" disabled={busy}>{t("save")}</button> : null}
      </form>

      {canApprove ? (
        <form onSubmit={create} className="flex flex-col gap-2">
          <h2 className="text-base font-medium">{t("create")}</h2>
          {(["ledger_id", "property_id"] as const).map((key) => (
            <label key={key} className="flex flex-col gap-1 text-sm">
              {key === "ledger_id" ? t("ledger") : t("property")}
              <input value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} required />
            </label>
          ))}
          <label className="flex flex-col gap-1 text-sm">
            {t("from")}
            <input type="date" value={form.period_from} onChange={(e) => setForm({ ...form, period_from: e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t("to")}
            <input type="date" value={form.period_to} onChange={(e) => setForm({ ...form, period_to: e.target.value })} required />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t("reason")}
            <input value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} required minLength={3} />
          </label>
          <button type="submit" disabled={busy}>{t("create")}</button>
        </form>
      ) : null}

      <section className="flex flex-col gap-2">
        <h2 className="text-base font-medium">{t("listTitle")}</h2>
        {rows.length === 0 ? <p className="text-sm">{t("empty")}</p> : null}
        <ul className="flex flex-col gap-2">
          {rows.map((row) => (
            <li key={row.id} className="rounded border p-3 text-sm">
              <div>
                {formatDate(row.period_from)} bis {formatDate(row.period_to)} ({row.active ? t("statusActive") : t("statusReleased")})
              </div>
              <div>
                {t("source")}: {sourceLabel(row.source)}
              </div>
              {row.reason ? <div>{row.reason}</div> : null}
              {row.release_requested_by ? (
                <div>
                  {t("requested")}: {row.release_request_reason} ({t("requestedHint")})
                </div>
              ) : null}
              {row.active && canApprove && settings.reopen_enabled ? (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <input
                    aria-label={t("reason")}
                    value={reasons[row.id] ?? ""}
                    onChange={(e) => setReasons({ ...reasons, [row.id]: e.target.value })}
                  />
                  {row.release_requested_by ? (
                    <button type="button" disabled={busy} onClick={() => act(row.id, "release")}>
                      {t("release")}
                    </button>
                  ) : (
                    <button type="button" disabled={busy} onClick={() => act(row.id, "release-request")}>
                      {t("requestRelease")}
                    </button>
                  )}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
