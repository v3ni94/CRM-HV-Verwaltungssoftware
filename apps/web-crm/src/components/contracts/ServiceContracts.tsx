"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Row of GET /api/v1/service-contracts (M9-06). */
export type ServiceContract = {
  id: string;
  provider_contact_id: string;
  property_id: string | null;
  title: string;
  starts_at: string;
  ends_at: string | null;
  notice_period_days: number;
  notice_period_unit: "days" | "months";
  auto_renewal_months: number | null;
  cancelled_at: string | null;
  notes: string | null;
  status: string;
  next_possible_end: string | null;
  latest_notice_date: string | null;
  orientation_only: boolean;
};

type Option = { id: string; label: string };

type FormState = {
  provider_contact_id: string;
  property_id: string;
  title: string;
  starts_at: string;
  ends_at: string;
  notice_period_days: string;
  notice_period_unit: "days" | "months";
  auto_renewal_months: string;
  cancelled_at: string;
  notes: string;
};

const EMPTY: FormState = {
  provider_contact_id: "",
  property_id: "",
  title: "",
  starts_at: "",
  ends_at: "",
  notice_period_days: "3",
  notice_period_unit: "months",
  auto_renewal_months: "",
  cancelled_at: "",
  notes: "",
};

function toForm(row: ServiceContract): FormState {
  return {
    provider_contact_id: row.provider_contact_id,
    property_id: row.property_id ?? "",
    title: row.title,
    starts_at: row.starts_at,
    ends_at: row.ends_at ?? "",
    notice_period_days: String(row.notice_period_days),
    notice_period_unit: row.notice_period_unit,
    auto_renewal_months:
      row.auto_renewal_months === null ? "" : String(row.auto_renewal_months),
    cancelled_at: row.cancelled_at ?? "",
    notes: row.notes ?? "",
  };
}

function toBody(f: FormState) {
  return {
    provider_contact_id: f.provider_contact_id,
    property_id: f.property_id || null,
    title: f.title.trim(),
    starts_at: f.starts_at,
    ends_at: f.ends_at || null,
    notice_period_days: Number(f.notice_period_days),
    notice_period_unit: f.notice_period_unit,
    auto_renewal_months: f.auto_renewal_months
      ? Number(f.auto_renewal_months)
      : null,
    cancelled_at: f.cancelled_at || null,
    notes: f.notes.trim() || null,
  };
}

export function ServiceContracts({
  initial,
  providers,
  properties,
  canCreate,
  canUpdate,
  canDelete,
}: {
  initial: ServiceContract[];
  providers: Option[];
  properties: Option[];
  canCreate: boolean;
  canUpdate: boolean;
  canDelete: boolean;
}) {
  const t = useTranslations("ServiceContracts");
  const [rows, setRows] = useState(initial);
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const providerName = new Map(providers.map((p) => [p.id, p.label]));
  const propertyName = new Map(properties.map((p) => [p.id, p.label]));
  const showForm = editing === null ? canCreate : canUpdate;

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  /** Client side plausibility (review 26.09.2026, contracts V5); the API validates again. */
  function validate(f: FormState): string | null {
    if (f.ends_at && f.ends_at < f.starts_at) return t("dateOrder");
    if (f.cancelled_at && f.cancelled_at < f.starts_at)
      return t("cancelledBeforeStart");
    return null;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaved(false);
    const invalid = validate(form);
    if (invalid) {
      setError(invalid);
      return;
    }
    setBusy(true);
    const path = editing
      ? `/api/bff/service-contracts/${editing}`
      : "/api/bff/service-contracts";
    const result = await bff<ServiceContract>(path, {
      method: editing ? "PATCH" : "POST",
      body: JSON.stringify(toBody(form)),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message ?? t("saveError"));
      return;
    }
    setError(null);
    setSaved(true);
    setRows((list) =>
      editing
        ? list.map((r) => (r.id === editing ? result.data : r))
        : [...list, result.data],
    );
    setEditing(null);
    setForm(EMPTY);
  }

  async function remove(id: string) {
    if (!window.confirm(t("confirmDelete"))) return;
    const result = await bff<null>(`/api/bff/service-contracts/${id}`, {
      method: "DELETE",
    });
    if (result.ok) setRows((list) => list.filter((r) => r.id !== id));
    else setError(result.message ?? t("saveError"));
  }

  const notice = (row: ServiceContract) =>
    `${row.notice_period_days} ${t(`unit.${row.notice_period_unit}`, { count: row.notice_period_days })}`;
  const term = (row: ServiceContract) =>
    `${formatDate(row.starts_at)} ${row.ends_at ? `${t("until")} ${formatDate(row.ends_at)}` : t("openEnded")}`;
  const renewal = (row: ServiceContract) =>
    row.auto_renewal_months
      ? t("renewal", { count: row.auto_renewal_months })
      : t("noRenewal");
  const statusLabel = (row: ServiceContract) =>
    t.has(`status.${row.status}`) ? t(`status.${row.status}`) : row.status;
  const toCheck = (row: ServiceContract) =>
    row.orientation_only ? (
      <span className={ui.badge}>{t("toCheck")}</span>
    ) : null;
  // In the table a plain line keeps the columns narrow enough for 1280 px without scrolling.
  const toCheckLine = (row: ServiceContract) =>
    row.orientation_only ? (
      <span className="block text-xs text-muted">{t("toCheck")}</span>
    ) : null;
  const startEdit = (row: ServiceContract) => {
    setSaved(false);
    setError(null);
    setEditing(row.id);
    setForm(toForm(row));
  };
  const actions = (row: ServiceContract) =>
    canUpdate || canDelete ? (
      <div className="flex flex-wrap gap-2">
        {canUpdate ? (
          <button
            type="button"
            className={ui.buttonSm}
            onClick={() => startEdit(row)}
          >
            {t("edit")}
          </button>
        ) : null}
        {canDelete ? (
          <button
            type="button"
            className={ui.buttonSm}
            onClick={() => remove(row.id)}
          >
            {t("delete")}
          </button>
        ) : null}
      </div>
    ) : null;

  return (
    <div className={ui.pageGap}>
      {saved ? (
        <p role="status" className={ui.success}>
          {t("saved")}
        </p>
      ) : null}
      {rows.length === 0 ? (
        <p className={`${ui.card} text-sm text-muted`}>{t("empty")}</p>
      ) : (
        <>
          <p className={ui.notice}>{t("computedHint")}</p>
          {/* Phone width: one card per contract with every field, the table stays for sm and up
            (review 26.09.2026, contracts V1). */}
          <ul
            className="flex flex-col gap-2 sm:hidden"
            data-testid="service-contracts-cards"
          >
            {rows.map((row) => (
              <li
                key={row.id}
                className={`${ui.card} flex flex-col gap-1 text-sm`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{row.title}</span>
                  <span className={ui.badge}>{statusLabel(row)}</span>
                </div>
                <span className="text-muted">
                  {providerName.get(row.provider_contact_id) ?? t("unknown")}
                </span>
                {row.property_id ? (
                  <span className="text-muted">
                    {propertyName.get(row.property_id) ?? t("unknown")}
                  </span>
                ) : null}
                <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                  <dt className="text-muted">{t("field.term")}</dt>
                  <dd className="tabular-nums">{term(row)}</dd>
                  <dt className="text-muted">{t("field.renewal")}</dt>
                  <dd>{renewal(row)}</dd>
                  <dt className="text-muted">{t("field.notice")}</dt>
                  <dd className="tabular-nums">{notice(row)}</dd>
                  {row.next_possible_end ? (
                    <>
                      <dt className="text-muted">{t("field.nextEnd")}</dt>
                      <dd className="tabular-nums">
                        {formatDate(row.next_possible_end)} {toCheck(row)}
                      </dd>
                    </>
                  ) : null}
                  {row.latest_notice_date ? (
                    <>
                      <dt className="text-muted">{t("field.noticeDate")}</dt>
                      <dd className="tabular-nums">
                        {formatDate(row.latest_notice_date)} {toCheck(row)}
                      </dd>
                    </>
                  ) : null}
                  {row.cancelled_at ? (
                    <>
                      <dt className="text-muted">{t("field.cancelledAt")}</dt>
                      <dd className="tabular-nums">
                        {formatDate(row.cancelled_at)}
                      </dd>
                    </>
                  ) : null}
                </dl>
                {actions(row) ? (
                  <div className="mt-2">{actions(row)}</div>
                ) : null}
              </li>
            ))}
          </ul>
          <div className="hidden overflow-x-auto sm:block">
            <table className={ui.table} data-testid="service-contracts-table">
              <thead>
                <tr>
                  <th scope="col">{t("field.title")}</th>
                  <th scope="col">{t("field.provider")}</th>
                  <th scope="col">{t("field.property")}</th>
                  <th scope="col">{t("field.term")}</th>
                  <th scope="col">{t("field.notice")}</th>
                  <th scope="col">{t("field.nextEnd")}</th>
                  <th scope="col">{t("field.noticeDate")}</th>
                  <th scope="col">{t("field.status")}</th>
                  <th scope="col">
                    <span className="sr-only">{t("actions")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.title}</td>
                    <td>
                      {providerName.get(row.provider_contact_id) ??
                        t("unknown")}
                    </td>
                    <td>
                      {row.property_id
                        ? (propertyName.get(row.property_id) ?? t("unknown"))
                        : ""}
                    </td>
                    <td className="tabular-nums">
                      {term(row)}
                      {row.auto_renewal_months ? (
                        <span className="block text-xs text-muted">
                          {renewal(row)}
                        </span>
                      ) : null}
                    </td>
                    <td className="tabular-nums">{notice(row)}</td>
                    <td className="tabular-nums">
                      {row.next_possible_end ? (
                        <>
                          {formatDate(row.next_possible_end)} {toCheckLine(row)}
                        </>
                      ) : null}
                    </td>
                    <td className="tabular-nums">
                      {row.latest_notice_date ? (
                        <>
                          {formatDate(row.latest_notice_date)}{" "}
                          {toCheckLine(row)}
                        </>
                      ) : null}
                    </td>
                    <td>{statusLabel(row)}</td>
                    <td className="whitespace-nowrap">{actions(row)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {showForm ? (
        <form
          onSubmit={submit}
          className={`${ui.card} grid grid-cols-1 gap-3 md:grid-cols-2`}
          aria-labelledby="service-contract-form-title"
        >
          <h2
            id="service-contract-form-title"
            className={`${ui.h2} md:col-span-2`}
          >
            {editing ? t("editTitle") : t("createTitle")}
          </h2>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("field.title")}</span>
            <input
              className={ui.input}
              required
              maxLength={300}
              value={form.title}
              onChange={(e) => set("title", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("field.provider")}</span>
            <select
              className={ui.input}
              required
              value={form.provider_contact_id}
              onChange={(e) => set("provider_contact_id", e.target.value)}
            >
              <option value="">{t("choose")}</option>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("field.property")}</span>
            <select
              className={ui.input}
              value={form.property_id}
              onChange={(e) => set("property_id", e.target.value)}
            >
              <option value="">{t("noProperty")}</option>
              {properties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("field.startsAt")}</span>
            <input
              className={ui.input}
              type="date"
              required
              value={form.starts_at}
              onChange={(e) => set("starts_at", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("field.endsAt")}</span>
            <input
              className={ui.input}
              type="date"
              value={form.ends_at}
              onChange={(e) => set("ends_at", e.target.value)}
            />
          </label>
          <div className="flex gap-2">
            <label className="flex flex-1 flex-col gap-1">
              <span className={ui.label}>{t("field.notice")}</span>
              <input
                className={ui.input}
                type="number"
                min={0}
                max={3650}
                required
                value={form.notice_period_days}
                onChange={(e) => set("notice_period_days", e.target.value)}
              />
              <span className={ui.help}>{t("noticeExample")}</span>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("field.unit")}</span>
              <select
                className={ui.input}
                value={form.notice_period_unit}
                onChange={(e) =>
                  set("notice_period_unit", e.target.value as "days" | "months")
                }
              >
                <option value="months">{t("unit.months", { count: 2 })}</option>
                <option value="days">{t("unit.days", { count: 2 })}</option>
              </select>
            </label>
          </div>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("field.autoRenewal")}</span>
            <input
              className={ui.input}
              type="number"
              min={1}
              max={120}
              value={form.auto_renewal_months}
              onChange={(e) => set("auto_renewal_months", e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("field.cancelledAt")}</span>
            <input
              className={ui.input}
              type="date"
              value={form.cancelled_at}
              onChange={(e) => set("cancelled_at", e.target.value)}
            />
            <span className={ui.help}>{t("cancelledAtHelp")}</span>
          </label>
          <label className="flex flex-col gap-1 md:col-span-2">
            <span className={ui.label}>{t("field.notes")}</span>
            <textarea
              className={ui.input}
              maxLength={5000}
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
            />
          </label>
          <p className="text-sm text-muted md:col-span-2">{t("hint")}</p>
          <div className={`${ui.formActions} md:col-span-2`}>
            <button type="submit" className={ui.primary} disabled={busy}>
              {t("save")}
            </button>
            {editing ? (
              <button
                type="button"
                className={ui.button}
                onClick={() => {
                  setEditing(null);
                  setError(null);
                  setForm(EMPTY);
                }}
              >
                {t("cancel")}
              </button>
            ) : null}
          </div>
          {error ? (
            <p role="alert" className={`${ui.alert} md:col-span-2`}>
              {error}
            </p>
          ) : null}
        </form>
      ) : null}
    </div>
  );
}
