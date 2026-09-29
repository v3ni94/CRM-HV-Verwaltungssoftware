"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { type Assignment, capabilityFor, type MeteringConnection, type SetupUnitRow, type Transmission } from "@/lib/metering";
import { ui } from "@/lib/ui";

/** Controlled write workflows (master prompt Messdienstleister section 12): user and role
 *  submission (On-Site Roles 2.0, complete data set per unit) and billing input. The buttons
 *  "Daten prüfen", "Freigeben" and "Abrechnung verbindlich beauftragen" (or "Nutzer und Rollen
 *  verbindlich übermitteln") are separate actions against separate endpoints; the release and the
 *  order carry the fingerprint of the checked payload, so any change in between is refused by the
 *  API (MHVP-METR-0012) and the user has to check again. Warnings are never skipped silently.
 *  The Ordnungsbegriffsabgleich (billing_unit_setup, Q8) is asynchronous: after the send the row
 *  stays "waiting_provider" until "Status abrufen" fetches the provider result; only that result
 *  confirms the assignment, never the acceptance alone. */

type CostRow = { key: string; allocation_key: string; gross_amount: string; invoice_date: string };

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

const KIND_FUNCTION: Record<Transmission["kind"], string> = {
  roles: "roles",
  billing_input: "billing_input",
  billing_unit_setup: "billing_unit_data",
};

export function TransmissionWorkflow({
  assignment,
  connection,
  canSubmitUsers,
  canOrderBilling,
  canSetupUnits = false,
  onOrdered,
}: {
  assignment: Assignment;
  connection: MeteringConnection | undefined;
  canSubmitUsers: boolean;
  canOrderBilling: boolean;
  /** metering_assignments:update: the Ordnungsbegriffsabgleich (billing_unit_setup). */
  canSetupUnits?: boolean;
  onOrdered?: () => void;
}) {
  const t = useTranslations("Metering");
  const [rows, setRows] = useState<Transmission[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [periodFrom, setPeriodFrom] = useState("");
  const [periodTo, setPeriodTo] = useState("");
  const [costs, setCosts] = useState<CostRow[]>([{ key: "", allocation_key: "", gross_amount: "", invoice_date: "" }]);
  const [ack, setAck] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    const res = await bff<Transmission[]>(`/api/bff/metering/transmissions?assignment_id=${assignment.id}&limit=20`);
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }, [assignment.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const current = (kind: Transmission["kind"]) => rows.find((r) => r.kind === kind) ?? null;

  async function check(kind: Transmission["kind"]) {
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = { assignment_id: assignment.id, kind };
    if (kind === "billing_input") {
      body.period_from = periodFrom;
      body.period_to = periodTo;
      body.inputs = {
        ancillary_invoices: costs
          .filter((c) => c.key.trim() || c.gross_amount.trim())
          .map((c) => ({
            key: c.key.trim(),
            allocation_key: c.allocation_key.trim(),
            gross_amount: c.gross_amount.trim().replace(",", "."),
            ...(c.invoice_date ? { invoice_date: c.invoice_date } : {}),
          })),
      };
    }
    const res = await bff<Transmission>("/api/bff/metering/transmissions/check", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    await load();
  }

  async function step(row: Transmission, action: "release" | "order" | "poll") {
    if (action === "order" && !window.confirm(t("transmission.orderConfirm"))) return;
    setBusy(true);
    setError(null);
    const res = await bff<Transmission>(`/api/bff/metering/transmissions/${row.id}/${action}`, {
      method: "POST",
      ...(action === "poll" ? {} : { body: JSON.stringify({ version: row.version, fingerprint: row.fingerprint, acknowledge_warnings: Boolean(ack[row.id]) }) }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      await load(); // a superseded row is shown as such
      return;
    }
    await load();
    if (action === "order") onOrdered?.();
  }

  const availability = (kind: Transmission["kind"], row?: Transmission | null): string | null => {
    const cap = capabilityFor(connection, KIND_FUNCTION[kind]);
    if (!connection) return t("fetch.noConnection");
    if (!cap) return t("fetch.unknownFunction");
    if (!cap.available) return cap.reason ?? t("capability.unavailable");
    // billing_unit_setup: the API additionally needs the documented submission and the write release
    if (kind === "billing_unit_setup" && row && row.validation.function_available === false) return row.validation.function_reason ?? t("capability.unavailable");
    return null;
  };

  function renderSetupPreview(row: Transmission) {
    const units = (row.summary.units as SetupUnitRow[] | undefined) ?? [];
    const internal = (row.summary.internal ?? {}) as Record<string, string | null>;
    const external = (row.summary.external ?? {}) as Record<string, unknown>;
    const unmatched = (row.summary.unmatched as string[] | undefined) ?? [];
    const additional = (row.summary.additional as string[] | undefined) ?? [];
    const setupstatus = row.summary.setupstatus ? String(row.summary.setupstatus) : null;
    return (
      <div className="flex flex-col gap-2" data-testid="setup-preview">
        <div className="grid gap-2 text-xs md:grid-cols-2">
          <div>
            <span className={ui.label}>{t("transmission.setupInternal")}</span>
            <p>
              {internal.property_number ?? ""} {internal.property_name ?? ""}
            </p>
          </div>
          <div>
            <span className={ui.label}>{t("transmission.setupExternal")}</span>
            <p>
              <span className="font-mono">{String(external.external_number ?? "")}</span> {external.external_name ? String(external.external_name) : ""}
              {external.setupstatus ? ` (${t("transmission.setupProviderStatus")}: ${String(external.setupstatus)})` : ""}
            </p>
          </div>
        </div>
        <div className={ui.tableScroll}>
          <table className={ui.table} data-testid="setup-units">
            <thead>
              <tr>
                <th>{t("transmission.setupUnitInternal")}</th>
                <th>{t("transmission.setupUnitExternal")}</th>
                <th>{t("transmission.setupOccupancy")}</th>
                <th>{t("transmission.setupKnown")}</th>
                <th>{t("transmission.setupMatched")}</th>
              </tr>
            </thead>
            <tbody>
              {units.map((u) => (
                <tr key={u.external_unit_number}>
                  <td>
                    {u.unit_number}
                    {u.unit_label ? ` (${u.unit_label})` : ""}
                  </td>
                  <td className="font-mono">{u.external_unit_number}</td>
                  <td>{t(`occupancy.${u.occupancy_status}`)}</td>
                  <td>{u.known_at_provider ? t("transmission.setupKnownYes") : t("transmission.setupKnownNo")}</td>
                  <td>{u.matched === null ? t("transmission.setupPending") : u.matched ? t("transmission.setupMatchedYes") : t("transmission.setupMatchedNo")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {row.status === "waiting_provider" ? <p className={ui.notice}>{t("transmission.waitingHint")}</p> : null}
        {row.status === "completed" ? (
          <p className={row.summary.remote_confirmed ? ui.notice : ui.alert} data-testid="setup-result">
            {row.summary.remote_confirmed
              ? t("transmission.setupConfirmed", { count: units.length })
              : t("transmission.setupUnmatched", { units: unmatched.join(", ") || "?" })}
            {additional.length ? ` ${t("transmission.setupAdditional", { units: additional.join(", ") })}` : ""}
            {setupstatus ? ` (${t("transmission.setupProviderStatus")}: ${setupstatus})` : ""}
          </p>
        ) : null}
      </div>
    );
  }

  function renderRow(row: Transmission, kind: Transmission["kind"]) {
    const errors = row.validation.errors ?? [];
    const warnings = row.validation.warnings ?? [];
    const provider = (row.validation.provider ?? {}) as Record<string, unknown>;
    const can = kind === "roles" ? canSubmitUsers : kind === "billing_input" ? canOrderBilling : canSetupUnits;
    const reason = availability(kind, row);
    const diff = row.diff ?? {};
    const diffEmpty = !(diff.added?.length || diff.removed?.length || diff.changed?.length);
    return (
      <div className="mt-3 flex flex-col gap-2 text-sm" data-testid={`transmission-${kind}`}>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill variant={STATUS_VARIANT[row.status] ?? "neutral"} label={t(`transmission.status.${row.status}`)} />
          <span className="text-xs text-muted">
            {t("transmission.fingerprint")}: <span className="font-mono">{row.fingerprint.slice(0, 12)}</span> ({row.assignment_version})
          </span>
          {row.period_from ? (
            <span className="text-xs tabular-nums">
              {formatDate(row.period_from)} {t("until")} {formatDate(row.period_to)}
            </span>
          ) : null}
          {row.provider_transaction_id ? (
            <span className="text-xs">
              {t("transmission.transaction")}: <span className="font-mono">{row.provider_transaction_id}</span>
            </span>
          ) : null}
        </div>
        <p className="text-xs text-muted">
          {kind === "roles" || kind === "billing_unit_setup"
            ? t("transmission.summaryUnits", { count: ((row.summary.units as unknown[]) ?? []).length })
            : `${t("transmission.summaryRecipients", { count: Number(row.summary.billing_recipients ?? 0) })}, ${t("transmission.summaryCosts", {
                count: Number(row.summary.ancillary_invoices ?? 0) + Number(row.summary.heating_system_invoices ?? 0) + Number(row.summary.energy_sources ?? 0),
              })}`}
        </p>
        {kind === "billing_unit_setup" ? renderSetupPreview(row) : null}
        {kind === "roles" && Array.isArray(row.summary.units) ? (
          <ul className="flex flex-wrap gap-1 text-xs">
            {(row.summary.units as { external_unit_number: string; unit_number: string; occupancy_status: string; terminate_all: boolean }[]).map((u) => (
              <li key={u.external_unit_number} className={ui.badge}>
                {u.unit_number} / {u.external_unit_number}: {t(`occupancy.${u.occupancy_status}`)}
                {u.terminate_all ? ` (${t("transmission.terminate")})` : ""}
              </li>
            ))}
          </ul>
        ) : null}
        <div>
          <span className={ui.label}>{t("transmission.diff")}</span>
          {diff.first_transmission ? (
            <p className="text-xs text-muted">{t("transmission.diffFirst")}</p>
          ) : diffEmpty ? (
            <p className="text-xs text-muted">{t("transmission.diffNone")}</p>
          ) : (
            <ul className="text-xs">
              {diff.added?.length ? <li>{t("transmission.diffAdded")}: {diff.added.join(", ")}</li> : null}
              {diff.removed?.length ? <li>{t("transmission.diffRemoved")}: {diff.removed.join(", ")}</li> : null}
              {diff.changed?.length ? <li>{t("transmission.diffChanged")}: {diff.changed.join(", ")}</li> : null}
            </ul>
          )}
        </div>
        {errors.length ? (
          <div role="alert" className={ui.alert}>
            <strong>{t("transmission.errors")}</strong>
            <ul className="list-disc pl-4">
              {errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {warnings.length ? (
          <div className={ui.notice}>
            <strong>{t("transmission.warnings")}</strong>
            <ul className="list-disc pl-4">
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {provider.skipped ? <p className="text-xs text-muted">{t("transmission.providerSkipped", { reason: String(provider.skipped) })}</p> : null}
        {provider.called ? (
          <p className="text-xs text-muted">
            {t("transmission.providerValidation")}: {String(provider.outcome ?? "")} {provider.detail ? `(${String(provider.detail)})` : ""}
          </p>
        ) : null}
        {row.status === "unclear" ? <p className={ui.alert}>{t("transmission.unclearHint")}</p> : null}
        {row.status === "checked" && can ? (
          <div className="flex flex-col gap-2">
            {warnings.length ? (
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={Boolean(ack[row.id])} onChange={(e) => setAck((prev) => ({ ...prev, [row.id]: e.target.checked }))} />
                {t("transmission.acknowledgeWarnings")}
              </label>
            ) : null}
            <div>
              <button type="button" className={ui.buttonSm} disabled={busy || (warnings.length > 0 && !ack[row.id])} onClick={() => step(row, "release")} data-testid={`release-${kind}`}>
                {t("transmission.release")}
              </button>
            </div>
          </div>
        ) : null}
        {row.status === "released" && can ? (
          <div className="flex flex-col gap-1">
            {reason ? <p className="text-xs text-warning-fg">{t("transmission.notAvailable", { reason })}</p> : null}
            <div>
              <button type="button" className={ui.danger} disabled={busy || reason !== null} onClick={() => step(row, "order")} data-testid={`order-${kind}`}>
                {kind === "roles" ? t("transmission.submitRoles") : kind === "billing_input" ? t("transmission.orderBilling") : t("transmission.submitSetup")}
              </button>
            </div>
          </div>
        ) : null}
        {row.status === "waiting_provider" && can ? (
          <div>
            <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => step(row, "poll")} data-testid={`poll-${kind}`}>
              {t("transmission.poll")}
            </button>
          </div>
        ) : null}
        {row.log.length ? (
          <details className="text-xs">
            <summary>{t("transmission.log")}</summary>
            <ul>
              {row.log.map((entry, i) => (
                <li key={i}>
                  {t("transmission.logEntry", { action: String(entry.action), at: formatDateTime(String(entry.at)) })}
                  {entry.user_id ? ` (${String(entry.user_id).slice(0, 8)})` : ""}
                  {entry.reason ? `: ${String(entry.reason)}` : ""}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>
    );
  }

  const roles = current("roles");
  const billing = current("billing_input");
  const setup = current("billing_unit_setup");

  return (
    <section className={ui.card} data-testid="transmissions">
      <h3 className={ui.subtitle}>{t("transmission.title")}</h3>
      <p className={ui.help}>{t("transmission.intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}

      <div className="mt-3 rounded-md border border-border p-3">
        <h4 className="text-sm font-semibold">{t("transmission.setup")}</h4>
        <p className={ui.help}>{t("transmission.setupHint")}</p>
        {canSetupUnits ? (
          <div className="mt-2">
            <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => check("billing_unit_setup")} data-testid="check-billing_unit_setup">
              {t("transmission.setupCheck")}
            </button>
          </div>
        ) : (
          <p className={ui.help}>{t("transmission.noPermissionSetup")}</p>
        )}
        {setup ? renderRow(setup, "billing_unit_setup") : <p className="mt-2 text-xs text-muted">{t("transmission.none")}</p>}
      </div>

      <div className="mt-3 rounded-md border border-border p-3">
        <h4 className="text-sm font-semibold">{t("transmission.roles")}</h4>
        <p className={ui.help}>{t("transmission.rolesHint")}</p>
        {canSubmitUsers ? (
          <div className="mt-2">
            <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => check("roles")} data-testid="check-roles">
              {t("transmission.check")}
            </button>
          </div>
        ) : (
          <p className={ui.help}>{t("transmission.noPermissionRoles")}</p>
        )}
        {roles ? renderRow(roles, "roles") : <p className="mt-2 text-xs text-muted">{t("transmission.none")}</p>}
      </div>

      <div className="mt-3 rounded-md border border-border p-3">
        <h4 className="text-sm font-semibold">{t("transmission.billing")}</h4>
        <p className={ui.help}>{t("transmission.billingHint")}</p>
        {canOrderBilling ? (
          <div className="mt-2 flex flex-col gap-2">
            <div className="flex flex-wrap items-end gap-2">
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("transmission.periodFrom")}</span>
                <input className={ui.input} type="date" value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} />
              </label>
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("transmission.periodTo")}</span>
                <input className={ui.input} type="date" value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} />
              </label>
            </div>
            <span className={ui.label}>{t("transmission.costs")}</span>
            {costs.map((c, i) => (
              <div key={i} className="grid gap-2 md:grid-cols-4">
                <input className={`${ui.input} font-mono`} aria-label={t("transmission.costKey")} placeholder={t("transmission.costKey")} value={c.key} onChange={(e) => setCosts(costs.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)))} />
                <input className={`${ui.input} font-mono`} aria-label={t("transmission.allocationKey")} placeholder={t("transmission.allocationKey")} value={c.allocation_key} onChange={(e) => setCosts(costs.map((x, j) => (j === i ? { ...x, allocation_key: e.target.value } : x)))} />
                <input className={`${ui.input} tabular-nums`} aria-label={t("transmission.grossAmount")} placeholder={t("transmission.grossAmount")} inputMode="decimal" value={c.gross_amount} onChange={(e) => setCosts(costs.map((x, j) => (j === i ? { ...x, gross_amount: e.target.value } : x)))} />
                <input className={ui.input} type="date" aria-label={t("transmission.invoiceDate")} value={c.invoice_date} onChange={(e) => setCosts(costs.map((x, j) => (j === i ? { ...x, invoice_date: e.target.value } : x)))} />
              </div>
            ))}
            <div className="flex flex-wrap gap-2">
              <button type="button" className={ui.buttonSm} onClick={() => setCosts([...costs, { key: "", allocation_key: "", gross_amount: "", invoice_date: "" }])}>
                {t("transmission.addCost")}
              </button>
              <button type="button" className={ui.buttonSm} disabled={busy || !periodFrom || !periodTo} onClick={() => check("billing_input")} data-testid="check-billing_input">
                {t("transmission.check")}
              </button>
            </div>
          </div>
        ) : (
          <p className={ui.help}>{t("transmission.noPermissionBilling")}</p>
        )}
        {billing ? renderRow(billing, "billing_input") : <p className="mt-2 text-xs text-muted">{t("transmission.none")}</p>}
      </div>
    </section>
  );
}
