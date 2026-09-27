"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDate, formatDateTime, formatDecimal } from "@/lib/format";
import {
  type Assignment,
  type BillingResult,
  bffList,
  buildQuery,
  capabilityFor,
  type ClearingItem,
  type ConsumptionValue,
  DATA_KINDS,
  type MeteringConnection,
  OCCUPANCY_STATUSES,
  type PropertyUnit,
  type SyncJob,
  type UnitAssignment,
} from "@/lib/metering";
import { ui } from "@/lib/ui";

import { AssignmentWizard } from "./AssignmentWizard";
import { AssignmentsTable, STATUS_VARIANT } from "./AssignmentsTable";
import { MeteringDisabledNotice } from "./MeteringDisabledNotice";

/** Object tab "Messdienstleister" (sections 5, 7, 10, 11): assignments of this property with
 *  HVM number, provider, account, external number, scope, validity, status and last successful
 *  fetch; the shared assignment wizard; unit assignments next to the internal units (floor,
 *  area, current occupants from the contract data, no second user file); "Jetzt abrufen" per
 *  data kind respecting the capability matrix; consumption and billing results with period
 *  filter; clearing items of the connection. */
type Property = { id: string; number: string; name: string; street?: string | null; house_number?: string | null; postal_code?: string | null; city?: string | null };

export function PropertyMeteringTab({ property, permissions }: { property: Property; permissions: string[] }) {
  const t = useTranslations("Metering");
  const canRead = permissions.includes("metering_data:read");
  const canUpdate = permissions.includes("metering_assignments:update");
  const canSync = permissions.includes("metering_sync:run");
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [connections, setConnections] = useState<MeteringConnection[]>([]);
  const [units, setUnits] = useState<PropertyUnit[]>([]);
  const [wizard, setWizard] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [selected, setSelected] = useState<Assignment | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!canRead) return;
    void (async () => {
      const [settings, conns, unitRes] = await Promise.all([
        bff<{ metering_module_enabled?: boolean }>("/api/bff/tenant/settings"),
        bff<MeteringConnection[]>("/api/bff/metering/connections"),
        bff<PropertyUnit[]>(`/api/bff/properties/${property.id}/units?with_occupants=true`),
      ]);
      setEnabled(settings.ok ? Boolean(settings.data?.metering_module_enabled) : true);
      if (conns.ok) setConnections(conns.data);
      else setError(conns.message);
      if (unitRes.ok) setUnits(unitRes.data);
    })();
  }, [canRead, property.id]);

  if (!canRead) return null;

  return (
    <section className="flex flex-col gap-4" id="messdienstleister" data-testid="metering-tab" aria-labelledby="metering-tab-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="metering-tab-title" className={ui.h2}>
          {t("tab.title")}
        </h2>
        <div className="flex flex-wrap gap-2">
          <Link href="/einstellungen/schnittstellen/messdienstleister" className={ui.buttonSm}>
            {t("tab.toSettings")}
          </Link>
          {canUpdate && enabled ? (
            <button type="button" className={ui.primary} onClick={() => setWizard(true)} disabled={connections.length === 0}>
              {t("assignment.new")}
            </button>
          ) : null}
        </div>
      </div>
      {enabled === false ? <MeteringDisabledNotice /> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {wizard ? (
        <AssignmentWizard
          connections={connections}
          property={property}
          onCreated={(a) => {
            setWizard(false);
            setSelected(a);
            setReloadKey((k) => k + 1);
          }}
          onCancel={() => setWizard(false)}
        />
      ) : null}
      <AssignmentsTable connections={connections} propertyId={property.id} canUpdate={canUpdate} reloadKey={reloadKey} onSelect={setSelected} selectedId={selected?.id} pageSize={20} />
      {selected ? (
        <AssignmentDetail
          key={selected.id}
          assignment={selected}
          connection={connections.find((c) => c.id === selected.connection_id)}
          units={units}
          canUpdate={canUpdate && enabled !== false}
          canSync={canSync && enabled !== false}
          onChanged={(a) => {
            setSelected(a);
            setReloadKey((k) => k + 1);
          }}
        />
      ) : null}
    </section>
  );
}

function AssignmentDetail({
  assignment,
  connection,
  units,
  canUpdate,
  canSync,
  onChanged,
}: {
  assignment: Assignment;
  connection: MeteringConnection | undefined;
  units: PropertyUnit[];
  canUpdate: boolean;
  canSync: boolean;
  onChanged: (a: Assignment) => void;
}) {
  const t = useTranslations("Metering");
  const [unitRows, setUnitRows] = useState<UnitAssignment[]>([]);
  const [jobs, setJobs] = useState<Record<string, SyncJob>>({});
  const [consumption, setConsumption] = useState<ConsumptionValue[]>([]);
  const [billing, setBilling] = useState<BillingResult[]>([]);
  const [clearing, setClearing] = useState<ClearingItem[]>([]);
  const [periodFrom, setPeriodFrom] = useState("");
  const [periodTo, setPeriodTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [basis, setBasis] = useState("");
  const [newUnit, setNewUnit] = useState({ unit_id: "", external_unit_number: "", valid_from: assignment.valid_from, occupancy_status: "unclear" });

  const loadUnits = useCallback(async () => {
    const res = await bff<UnitAssignment[]>(`/api/bff/metering/assignments/${assignment.id}/units`);
    if (res.ok) setUnitRows(res.data);
    else setError(res.message);
  }, [assignment.id]);

  const loadData = useCallback(async () => {
    const q = buildQuery({ period_from: periodFrom, period_to: periodTo });
    const [c, b] = await Promise.all([
      bff<ConsumptionValue[]>(`/api/bff/metering/assignments/${assignment.id}/consumption${q}`),
      bff<BillingResult[]>(`/api/bff/metering/assignments/${assignment.id}/billing-results${q}`),
    ]);
    if (c.ok) setConsumption(c.data);
    if (b.ok) setBilling(b.data);
  }, [assignment.id, periodFrom, periodTo]);

  const loadClearing = useCallback(async () => {
    const res = await bffList<ClearingItem>(`/api/bff/metering/clearing-items?status=open&connection_id=${assignment.connection_id}&page=1&page_size=50`);
    if (res.ok) setClearing(res.data);
  }, [assignment.connection_id]);

  useEffect(() => {
    void loadUnits();
    void loadClearing();
  }, [loadUnits, loadClearing]);
  useEffect(() => {
    void loadData();
  }, [loadData]);

  const unitById = (id: string) => units.find((u) => u.id === id);
  const occupancyInfo = (u: PropertyUnit | undefined) => {
    if (!u) return "";
    const parts: string[] = [];
    if (u.tenant) parts.push(`${t("unit.tenant")}: ${u.tenant.party_name} (${t("since")} ${formatDate(u.tenant.start_date)})`);
    if (u.owner) parts.push(`${t("unit.owner")}: ${u.owner.party_name}`);
    return parts.join(", ");
  };

  async function patchAssignment(body: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    const res = await bff<Assignment>(`/api/bff/metering/assignments/${assignment.id}`, {
      method: "PATCH",
      body: JSON.stringify({ version: assignment.version, ...body }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    onChanged(res.data);
  }

  async function remoteConfirm() {
    setBusy(true);
    setError(null);
    const res = await bff<Assignment>(`/api/bff/metering/assignments/${assignment.id}/remote-confirm`, {
      method: "POST",
      body: JSON.stringify({ version: assignment.version, verification_basis: basis.trim() }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    onChanged(res.data);
  }

  async function addUnit() {
    setBusy(true);
    setError(null);
    const res = await bff<UnitAssignment>(`/api/bff/metering/assignments/${assignment.id}/units`, {
      method: "POST",
      body: JSON.stringify({ ...newUnit, external_unit_number: newUnit.external_unit_number.trim() }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setNewUnit({ ...newUnit, unit_id: "", external_unit_number: "" });
    await loadUnits();
  }

  async function fetchNow(kind: string) {
    setBusy(true);
    setError(null);
    const res = await bff<SyncJob>("/api/bff/metering/sync-jobs", {
      method: "POST",
      body: JSON.stringify({ connection_id: assignment.connection_id, data_kind: kind, property_ids: [assignment.property_id] }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setJobs((prev) => ({ ...prev, [kind]: res.data }));
  }

  async function refreshJob(kind: string) {
    const job = jobs[kind];
    if (!job) return;
    const res = await bff<SyncJob>(`/api/bff/metering/sync-jobs/${job.id}`);
    if (res.ok) {
      setJobs((prev) => ({ ...prev, [kind]: res.data }));
      await loadData();
      await loadClearing();
    }
  }

  async function resolveClearing(item: ClearingItem, status: "resolved" | "dismissed") {
    const res = await bff<ClearingItem>(`/api/bff/metering/clearing-items/${item.id}/resolve`, {
      method: "POST",
      body: JSON.stringify({ status, property_assignment_id: status === "resolved" ? assignment.id : null }),
    });
    if (!res.ok) return setError(res.message);
    await loadClearing();
  }

  const fetchReason = (kind: string): string | null => {
    if (!connection) return t("fetch.noConnection");
    if (connection.status !== "active") return t("fetch.connectionPaused");
    if (assignment.status === "conflict") return t("fetch.conflict");
    const cap = capabilityFor(connection, kind);
    if (!cap) return t("fetch.unknownFunction");
    if (!cap.available) return cap.reason ?? t("capability.unavailable");
    return null;
  };

  const missingUnits = units.filter((u) => !unitRows.some((r) => r.unit_id === u.id && r.status !== "archived"));

  return (
    <div className="flex flex-col gap-4" data-testid="assignment-detail">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <section className={ui.card}>
        <h3 className={ui.subtitle}>{t("detail.title")}</h3>
        <dl className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <dt className="text-muted">{t("table.hvmNumber")}</dt>
          <dd className="font-mono">{assignment.property_number}</dd>
          <dt className="text-muted">{t("table.provider")}</dt>
          <dd>{assignment.provider_code}</dd>
          <dt className="text-muted">{t("detail.account")}</dt>
          <dd>
            {assignment.connection_name} ({t(`environment.${assignment.environment}`)})
          </dd>
          <dt className="text-muted">{t("table.externalNumber")}</dt>
          <dd className="font-mono">{assignment.external_number}</dd>
          <dt className="text-muted">{t("table.scope")}</dt>
          <dd>{t(`scope.${assignment.service_scope}`)}</dd>
          <dt className="text-muted">{t("table.validity")}</dt>
          <dd className="tabular-nums">
            {formatDate(assignment.valid_from)} {t("until")} {assignment.valid_to ? formatDate(assignment.valid_to) : t("openEnd")}
          </dd>
          <dt className="text-muted">{t("table.status")}</dt>
          <dd>
            <StatusPill variant={STATUS_VARIANT[assignment.status] ?? "neutral"} label={t(`status.${assignment.status}`)} />
            {assignment.remote_confirmed ? <span className={`${ui.badgeSuccess} ml-1`}>{t("assignment.remoteConfirmed")}</span> : null}
          </dd>
          <dt className="text-muted">{t("table.lastFetch")}</dt>
          <dd className="tabular-nums">{assignment.last_success_at ? formatDateTime(assignment.last_success_at) : t("none")}</dd>
        </dl>
        {assignment.conflict_reason ? <p className={`${ui.alert} mt-2`}>{assignment.conflict_reason}</p> : null}
        {assignment.verification_basis ? (
          <p className={`${ui.help} mt-2`}>
            {t("detail.basis")}: {assignment.verification_basis}
          </p>
        ) : null}
        {canUpdate ? (
          <div className="mt-3 flex flex-col gap-2">
            <div className="flex flex-wrap gap-2">
              <input className={ui.input} placeholder={t("detail.basisPlaceholder")} aria-label={t("detail.basis")} value={basis} onChange={(e) => setBasis(e.target.value)} />
            </div>
            <div className="flex flex-wrap gap-2">
              {assignment.status !== "confirmed" && assignment.status !== "archived" ? (
                <button type="button" className={ui.buttonSm} disabled={busy || !basis.trim()} onClick={() => patchAssignment({ status: "confirmed", verification_basis: basis.trim() })}>
                  {t("detail.confirmLocal")}
                </button>
              ) : null}
              {!assignment.remote_confirmed ? (
                <button type="button" className={ui.buttonSm} disabled={busy || !basis.trim()} onClick={remoteConfirm}>
                  {t("detail.confirmRemote")}
                </button>
              ) : null}
              {assignment.status !== "archived" ? (
                <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => patchAssignment({ status: "archived" })}>
                  {t("detail.archive")}
                </button>
              ) : null}
            </div>
            <p className={ui.help}>{t("detail.confirmHint")}</p>
          </div>
        ) : null}
      </section>

      <section className={ui.card} data-testid="fetch-actions">
        <h3 className={ui.subtitle}>{t("fetch.title")}</h3>
        <ul className="mt-2 flex flex-col gap-2 text-sm">
          {DATA_KINDS.map((kind) => {
            const reason = fetchReason(kind);
            const job = jobs[kind];
            return (
              <li key={kind} className="flex flex-wrap items-center gap-2">
                <span className="min-w-48">{t(`functions.${kind}`)}</span>
                <button type="button" className={ui.buttonSm} disabled={!canSync || busy || reason !== null} title={reason ?? undefined} onClick={() => fetchNow(kind)} data-testid={`fetch-${kind}`}>
                  {t("fetch.button")}
                </button>
                {reason ? <span className="text-xs text-muted">{reason}</span> : null}
                {job ? (
                  <>
                    <StatusPill variant={job.status === "succeeded" ? "success" : job.status === "failed" ? "danger" : "warning"} label={t(`jobStatus.${job.status}`)} />
                    {job.error_summary ? <span className="text-xs text-danger-fg">{job.error_summary}</span> : null}
                    <button type="button" className={ui.buttonSm} onClick={() => refreshJob(kind)}>
                      {t("fetch.refresh")}
                    </button>
                  </>
                ) : null}
              </li>
            );
          })}
        </ul>
        {!canSync ? <p className={`${ui.help} mt-2`}>{t("fetch.noPermission")}</p> : null}
      </section>

      <section className={ui.card} data-testid="unit-assignments">
        <h3 className={ui.subtitle}>{t("unit.title")}</h3>
        {missingUnits.length ? <p className={`${ui.notice} mt-2`}>{t("unit.missing", { count: missingUnits.length })}</p> : null}
        <div className="mt-2 overflow-x-auto">
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("unit.internalNumber")}</th>
                <th>{t("unit.externalNumber")}</th>
                <th>{t("unit.floor")}</th>
                <th>{t("unit.area")}</th>
                <th>{t("unit.occupancy")}</th>
                <th>{t("unit.currentOccupants")}</th>
                <th>{t("table.validity")}</th>
                <th>{t("table.status")}</th>
              </tr>
            </thead>
            <tbody>
              {unitRows.map((r) => {
                const u = unitById(r.unit_id);
                return (
                  <tr key={r.id} data-testid={`unit-assignment-${r.id}`}>
                    <td className="font-mono">{r.unit_number}</td>
                    <td className="font-mono">{r.external_unit_number}</td>
                    <td>{r.unit_floor ?? u?.floor ?? ""}</td>
                    <td className="tabular-nums">{u?.living_area_sqm ? formatDecimal(u.living_area_sqm, 2) : u?.total_area_sqm ? formatDecimal(u.total_area_sqm, 2) : ""}</td>
                    <td>{t(`occupancy.${r.occupancy_status}`)}</td>
                    <td className="text-xs">{occupancyInfo(u)}</td>
                    <td className="tabular-nums">
                      {formatDate(r.valid_from)} {t("until")} {r.valid_to ? formatDate(r.valid_to) : t("openEnd")}
                    </td>
                    <td>
                      <StatusPill variant={STATUS_VARIANT[r.status] ?? "neutral"} label={t(`status.${r.status}`)} />
                    </td>
                  </tr>
                );
              })}
              {unitRows.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-muted">
                    {t("unit.empty")}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        {canUpdate ? (
          <div className="mt-3 grid gap-2 md:grid-cols-5">
            <select className={ui.input} aria-label={t("unit.internalNumber")} value={newUnit.unit_id} onChange={(e) => setNewUnit({ ...newUnit, unit_id: e.target.value })}>
              <option value="">{t("assignment.choose")}</option>
              {units.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.number} {u.label ?? ""} {u.floor ? `(${u.floor})` : ""}
                </option>
              ))}
            </select>
            <input className={`${ui.input} font-mono`} aria-label={t("unit.externalNumber")} placeholder={t("unit.externalNumber")} value={newUnit.external_unit_number} onChange={(e) => setNewUnit({ ...newUnit, external_unit_number: e.target.value })} maxLength={64} />
            <input className={ui.input} type="date" aria-label={t("assignment.validFrom")} value={newUnit.valid_from} onChange={(e) => setNewUnit({ ...newUnit, valid_from: e.target.value })} />
            <select className={ui.input} aria-label={t("unit.occupancy")} value={newUnit.occupancy_status} onChange={(e) => setNewUnit({ ...newUnit, occupancy_status: e.target.value })}>
              {OCCUPANCY_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {t(`occupancy.${s}`)}
                </option>
              ))}
            </select>
            <button type="button" className={ui.primary} disabled={busy || !newUnit.unit_id || !newUnit.external_unit_number.trim() || !newUnit.valid_from} onClick={addUnit} data-testid="unit-add">
              {t("unit.add")}
            </button>
            <p className={`${ui.help} md:col-span-5`}>{t("unit.hint")}</p>
          </div>
        ) : null}
      </section>

      <section className={ui.card} data-testid="metering-data">
        <h3 className={ui.subtitle}>{t("data.title")}</h3>
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("data.periodFrom")}</span>
            <input className={ui.input} type="date" value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("data.periodTo")}</span>
            <input className={ui.input} type="date" value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} />
          </label>
        </div>
        <h4 className={`${ui.subtitle} mt-3`}>{t("data.consumption")}</h4>
        {consumption.length === 0 ? (
          <p className="text-sm text-muted">{t("data.empty")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("data.period")}</th>
                  <th>{t("unit.externalNumber")}</th>
                  <th>{t("data.kind")}</th>
                  <th>{t("data.value")}</th>
                  <th>{t("data.valueKind")}</th>
                  <th>{t("data.source")}</th>
                  <th>{t("data.version")}</th>
                </tr>
              </thead>
              <tbody>
                {consumption.map((v) => (
                  <tr key={v.id}>
                    <td className="tabular-nums">
                      {formatDate(v.period_from)} {t("until")} {formatDate(v.period_to)}
                    </td>
                    <td className="font-mono">{unitRows.find((r) => r.id === v.unit_assignment_id)?.external_unit_number ?? ""}</td>
                    <td>{v.kind}</td>
                    <td className="tabular-nums">{v.value === null ? t("data.missing") : `${formatDecimal(v.value, 3)} ${v.unit_of_measure}`}</td>
                    <td>{t(`valueKind.${v.value_kind}`)}</td>
                    <td>{v.source}</td>
                    <td className="tabular-nums">{v.version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <h4 className={`${ui.subtitle} mt-3`}>{t("data.billing")}</h4>
        <p className={ui.help}>{t("data.billingHint")}</p>
        {billing.length === 0 ? (
          <p className="text-sm text-muted">{t("data.empty")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("data.period")}</th>
                  <th>{t("unit.externalNumber")}</th>
                  <th>{t("data.amount")}</th>
                  <th>{t("data.documentRef")}</th>
                  <th>{t("data.review")}</th>
                  <th>{t("data.version")}</th>
                </tr>
              </thead>
              <tbody>
                {billing.map((b) => (
                  <tr key={b.id}>
                    <td className="tabular-nums">
                      {formatDate(b.period_from)} {t("until")} {formatDate(b.period_to)}
                    </td>
                    <td className="font-mono">{unitRows.find((r) => r.id === b.unit_assignment_id)?.external_unit_number ?? ""}</td>
                    <td className="tabular-nums">
                      {formatDecimal(b.amount, 2)} {b.currency}
                    </td>
                    <td className="font-mono">{b.external_document_ref}</td>
                    <td>{t(`reviewStatus.${b.review_status}`)}</td>
                    <td className="tabular-nums">{b.version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className={ui.card} data-testid="clearing-items">
        <h3 className={ui.subtitle}>{t("clearing.title")}</h3>
        <p className={ui.help}>{t("clearing.intro")}</p>
        {clearing.length === 0 ? (
          <p className="mt-2 text-sm text-muted">{t("clearing.empty")}</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-2 text-sm">
            {clearing.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center gap-2">
                <span className={ui.badge}>{item.entity_type}</span>
                <span className="font-mono">{item.external_identifier}</span>
                <span className="text-muted">{item.reason}</span>
                <span className="text-xs text-subtle">{formatDateTime(item.created_at)}</span>
                {canUpdate ? (
                  <>
                    <button type="button" className={ui.buttonSm} onClick={() => resolveClearing(item, "resolved")}>
                      {t("clearing.assignHere")}
                    </button>
                    <button type="button" className={ui.buttonSm} onClick={() => resolveClearing(item, "dismissed")}>
                      {t("clearing.dismiss")}
                    </button>
                  </>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
