"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ASSIGNMENT_STATUSES, type Assignment, bffList, buildQuery, type MeteringConnection, SERVICE_SCOPES } from "@/lib/metering";
import { ui } from "@/lib/ui";

/** Assignment table (section 6), shared by the central overview and the object tab
 *  (`propertyId` set). Search, filters and pagination run server side (X-Total-Count). The
 *  bulk release shows a preview of the selected assignments in status "proposed" and confirms
 *  them one by one with their version (409 is reported per row). */
export const STATUS_VARIANT: Record<string, StatusPillVariant> = {
  open: "neutral",
  proposed: "warning",
  confirmed: "success",
  conflict: "danger",
  archived: "neutral",
};

export function AssignmentsTable({
  connections,
  propertyId,
  canUpdate,
  pageSize = 25,
  reloadKey = 0,
  onSelect,
  selectedId,
}: {
  connections: MeteringConnection[];
  propertyId?: string;
  canUpdate: boolean;
  pageSize?: number;
  reloadKey?: number;
  onSelect?: (assignment: Assignment) => void;
  selectedId?: string | null;
}) {
  const t = useTranslations("Metering");
  const [rows, setRows] = useState<Assignment[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [scope, setScope] = useState("");
  const [connectionId, setConnectionId] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [preview, setPreview] = useState<Assignment[] | null>(null);
  const [releaseReport, setReleaseReport] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const res = await bffList<Assignment>(
      `/api/bff/metering/assignments${buildQuery({
        property_id: propertyId,
        connection_id: connectionId,
        status,
        service_scope: scope,
        search,
        include_archived: includeArchived ? "true" : "",
        page,
        page_size: pageSize,
      })}`,
    );
    setLoading(false);
    if (!res.ok) return setError(res.message);
    setError(null);
    setRows(res.data);
    setTotal(res.total);
  }, [propertyId, connectionId, status, scope, search, includeArchived, page, pageSize]);

  useEffect(() => {
    void load();
  }, [load, reloadKey]);

  const pages = Math.max(1, Math.ceil(total / pageSize));

  function openPreview() {
    setReleaseReport([]);
    setPreview(rows.filter((r) => checked.has(r.id)));
  }

  async function applyRelease() {
    if (!preview) return;
    setBusy(true);
    const report: string[] = [];
    for (const a of preview.filter((r) => r.status === "proposed")) {
      const res = await bff<Assignment>(`/api/bff/metering/assignments/${a.id}`, {
        method: "PATCH",
        body: JSON.stringify({ version: a.version, status: "confirmed", verification_basis: "Sammelfreigabe zentrale Übersicht" }),
      });
      report.push(res.ok ? t("release.rowOk", { number: a.property_number }) : t("release.rowFailed", { number: a.property_number, message: res.message }));
    }
    setBusy(false);
    setReleaseReport(report);
    setPreview(null);
    setChecked(new Set());
    await load();
  }

  const validity = (a: Assignment) => `${formatDate(a.valid_from)} ${t("until")} ${a.valid_to ? formatDate(a.valid_to) : t("openEnd")}`;

  return (
    <div className="flex flex-col gap-3" data-testid="metering-assignments">
      <form
        className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5"
        onSubmit={(e) => {
          e.preventDefault();
          setPage(1);
          void load();
        }}
      >
        <input className={ui.input} placeholder={t("table.search")} aria-label={t("table.search")} value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className={ui.input} aria-label={t("table.status")} value={status} onChange={(e) => (setStatus(e.target.value), setPage(1))}>
          <option value="">{t("table.allStatus")}</option>
          {ASSIGNMENT_STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`status.${s}`)}
            </option>
          ))}
        </select>
        <select className={ui.input} aria-label={t("table.scope")} value={scope} onChange={(e) => (setScope(e.target.value), setPage(1))}>
          <option value="">{t("table.allScopes")}</option>
          {SERVICE_SCOPES.map((s) => (
            <option key={s} value={s}>
              {t(`scope.${s}`)}
            </option>
          ))}
        </select>
        <select className={ui.input} aria-label={t("table.connection")} value={connectionId} onChange={(e) => (setConnectionId(e.target.value), setPage(1))}>
          <option value="">{t("table.allConnections")}</option>
          {connections.map((c) => (
            <option key={c.id} value={c.id}>
              {c.display_name}
            </option>
          ))}
        </select>
        <div className="flex items-center gap-2">
          <button type="submit" className={ui.button}>
            {t("search")}
          </button>
          <label className="flex items-center gap-1 text-xs">
            <input type="checkbox" checked={includeArchived} onChange={(e) => (setIncludeArchived(e.target.checked), setPage(1))} />
            {t("table.includeArchived")}
          </label>
        </div>
      </form>

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {releaseReport.length ? (
        <ul className={ui.notice} data-testid="release-report">
          {releaseReport.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      ) : null}

      {canUpdate && !propertyId ? (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <button type="button" className={ui.buttonSm} disabled={checked.size === 0} onClick={openPreview} data-testid="release-preview-button">
            {t("release.button", { count: checked.size })}
          </button>
          <span className={ui.help}>{t("release.hint")}</span>
        </div>
      ) : null}

      {preview ? (
        <div className={ui.card} role="dialog" aria-label={t("release.previewTitle")} data-testid="release-preview">
          <h3 className={ui.subtitle}>{t("release.previewTitle")}</h3>
          <ul className="mt-2 flex flex-col gap-1 text-sm">
            {preview.map((a) => (
              <li key={a.id} className="flex flex-wrap gap-2">
                <span className="font-mono">{a.property_number}</span>
                <span className="font-mono">{a.external_number}</span>
                <span>{t(`scope.${a.service_scope}`)}</span>
                {a.status === "proposed" ? (
                  <StatusPill variant="success" label={t("release.willConfirm")} />
                ) : (
                  <StatusPill variant="warning" label={t("release.skipped", { status: t(`status.${a.status}`) })} />
                )}
              </li>
            ))}
          </ul>
          <div className={`${ui.formActions} mt-3`}>
            <button type="button" className={ui.primary} disabled={busy || !preview.some((a) => a.status === "proposed")} onClick={applyRelease} data-testid="release-apply">
              {t("release.apply")}
            </button>
            <button type="button" className={ui.button} onClick={() => setPreview(null)}>
              {t("cancel")}
            </button>
          </div>
        </div>
      ) : null}

      <div className="overflow-x-auto">
        <table className={ui.table} data-testid="assignments-table">
          <thead>
            <tr>
              {canUpdate && !propertyId ? <th /> : null}
              <th>{t("table.hvmNumber")}</th>
              <th>{t("table.address")}</th>
              <th>{t("table.provider")}</th>
              <th>{t("table.connection")}</th>
              <th>{t("table.externalNumber")}</th>
              <th>{t("table.scope")}</th>
              <th>{t("table.validity")}</th>
              <th>{t("table.units")}</th>
              <th>{t("table.status")}</th>
              <th>{t("table.lastFetch")}</th>
              <th>{t("table.errorHint")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.id} data-testid={`assignment-${a.id}`} className={selectedId === a.id ? "bg-surface" : undefined}>
                {canUpdate && !propertyId ? (
                  <td>
                    <input
                      type="checkbox"
                      aria-label={t("release.select")}
                      checked={checked.has(a.id)}
                      onChange={(e) =>
                        setChecked((prev) => {
                          const next = new Set(prev);
                          if (e.target.checked) next.add(a.id);
                          else next.delete(a.id);
                          return next;
                        })
                      }
                    />
                  </td>
                ) : null}
                <td className="font-mono">
                  {propertyId ? a.property_number : (
                    <Link href={`/objekte/${a.property_id}`} className="hover:underline">
                      {a.property_number}
                    </Link>
                  )}
                </td>
                <td>{a.property_address ?? a.property_name}</td>
                <td>{a.provider_code}</td>
                <td>{a.connection_name}</td>
                <td className="font-mono">
                  {a.external_number}
                  {a.is_primary ? <span className={`${ui.badgeGold} ml-1`}>{t("assignment.primaryShort")}</span> : null}
                </td>
                <td>{t(`scope.${a.service_scope}`)}</td>
                <td className="tabular-nums">{validity(a)}</td>
                <td className="tabular-nums">
                  {a.assigned_unit_count}/{a.expected_unit_count ?? "?"}
                </td>
                <td>
                  <StatusPill variant={STATUS_VARIANT[a.status] ?? "neutral"} label={t(`status.${a.status}`)} />
                  {a.remote_confirmed ? <span className={`${ui.badgeSuccess} ml-1`}>{t("assignment.remoteConfirmed")}</span> : null}
                </td>
                <td className="tabular-nums">{a.last_success_at ? formatDateTime(a.last_success_at) : t("none")}</td>
                <td className="text-danger-fg">
                  {a.conflict_reason ?? a.error_hint ?? ""}
                  {onSelect ? (
                    <button type="button" className={`${ui.buttonSm} ml-1`} onClick={() => onSelect(a)}>
                      {t("table.open")}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
            {!loading && rows.length === 0 ? (
              <tr>
                <td colSpan={12} className="text-muted">
                  {t("table.empty")}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <nav className="flex items-center gap-3 text-sm" aria-label={t("table.pagination")} data-testid="assignments-pagination">
        <span className="text-muted">{t("table.total", { total })}</span>
        <span className="ml-auto">{t("table.page", { page, pages })}</span>
        <button type="button" className={ui.buttonSm} disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          {t("table.prev")}
        </button>
        <button type="button" className={ui.buttonSm} disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
          {t("table.next")}
        </button>
      </nav>
    </div>
  );
}
