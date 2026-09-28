"use client";
/** Zähler des Objekts (C2, Stammdaten in der Oberfläche): Nummer, Art (Katalog `meter_type`),
 *  Einheit, Standort, Gültigkeit, Eichfrist. Anlegen über POST /properties/{id}/meters
 *  (`properties:create`), Ändern über PATCH /meters/{id} (`properties:update`, ohne Nummer),
 *  Zählerwechsel über POST /meters/{id}/changes mit Endstand alt und Anfangsstand neu; der
 *  Zählersatz behält seine Historie, die Nummer wechselt nur über den Wechselsatz. */
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import { loadCatalogOptions, todayIso } from "./ContactPersonsPicker";

export type MeterRow = {
  id: string;
  unit_id: string | null;
  meter_type_code: string;
  number: string;
  malo_id?: string | null;
  name?: string | null;
  connection: string;
  location: string | null;
  calibration_due_date: string | null;
  remote_readable: boolean;
  valid_from: string;
  valid_to: string | null;
  notes?: string | null;
};

export type UnitOption = { id: string; number: string; label?: string | null };

type Draft = {
  number: string;
  meter_type_code: string;
  unit_id: string;
  location: string;
  connection: string;
  calibration_due_date: string;
  valid_from: string;
  valid_to: string;
  remote_readable: boolean;
};

type ChangeDraft = { changed_on: string; old_final_value: string; new_initial_value: string; new_number: string };

const EMPTY: Draft = { number: "", meter_type_code: "", unit_id: "", location: "", connection: "sub", calibration_due_date: "", valid_from: todayIso(), valid_to: "", remote_readable: false };

function draftOf(row: MeterRow): Draft {
  return {
    number: row.number,
    meter_type_code: row.meter_type_code,
    unit_id: row.unit_id ?? "",
    location: row.location ?? "",
    connection: row.connection,
    calibration_due_date: row.calibration_due_date ?? "",
    valid_from: row.valid_from,
    valid_to: row.valid_to ?? "",
    remote_readable: row.remote_readable,
  };
}

const DECIMAL = /^\d{1,12}([.,]\d{1,8})?$/;

export function MetersPanel({ propertyId, rows, units, canEdit, canCreate }: { propertyId: string; rows: MeterRow[]; units: UnitOption[]; canEdit: boolean; canCreate: boolean }) {
  const t = useTranslations("Properties.metersPanel");
  const router = useRouter();
  const [types, setTypes] = useState<{ code: string; label: string }[]>([]);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [editing, setEditing] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<Draft | null>(null);
  const [changing, setChanging] = useState<string | null>(null);
  const [change, setChange] = useState<ChangeDraft>({ changed_on: todayIso(), old_final_value: "", new_initial_value: "", new_number: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void loadCatalogOptions("meter_type").then((options) => {
      if (active) setTypes(options);
    });
    return () => {
      active = false;
    };
  }, []);

  const typeLabel = (code: string) => types.find((c) => c.code === code)?.label ?? code;
  const unitLabel = (id: string | null) => {
    if (!id) return t("wholeProperty");
    const unit = units.find((u) => u.id === id);
    return unit ? [unit.number, unit.label].filter(Boolean).join(" ") : id;
  };

  const run = async (path: string, method: "POST" | "PATCH", payload: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    const res = await bff(path, { method, body: JSON.stringify(payload) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return false;
    }
    router.refresh();
    return true;
  };

  const common = (d: Draft) => ({
    meter_type_code: d.meter_type_code,
    unit_id: d.unit_id || null,
    location: d.location.trim() || null,
    connection: d.connection,
    calibration_due_date: d.calibration_due_date || null,
    valid_from: d.valid_from,
    valid_to: d.valid_to || null,
    remote_readable: d.remote_readable,
  });

  const add = async () => {
    if (await run(`/api/bff/properties/${propertyId}/meters`, "POST", { number: draft.number.trim(), ...common(draft) })) {
      setAdding(false);
      setDraft(EMPTY);
    }
  };

  const save = async (id: string) => {
    if (!editDraft) return;
    if (await run(`/api/bff/meters/${id}`, "PATCH", common(editDraft))) {
      setEditing(null);
      setEditDraft(null);
    }
  };

  const replace = async (id: string) => {
    const payload: Record<string, unknown> = {
      changed_on: change.changed_on,
      old_final_value: change.old_final_value.trim().replace(",", "."),
      new_initial_value: change.new_initial_value.trim().replace(",", "."),
    };
    if (change.new_number.trim()) payload.new_number = change.new_number.trim();
    if (await run(`/api/bff/meters/${id}/changes`, "POST", payload)) {
      setChanging(null);
      setChange({ changed_on: todayIso(), old_final_value: "", new_initial_value: "", new_number: "" });
    }
  };

  const changeValid = change.changed_on !== "" && DECIMAL.test(change.old_final_value.trim()) && DECIMAL.test(change.new_initial_value.trim());
  const draftValid = (d: Draft) => d.meter_type_code !== "" && d.valid_from !== "";

  const form = (d: Draft, set: (d: Draft) => void, withNumber: boolean) => (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {withNumber ? (
        <label className={ui.label}>
          {t("number")}
          <input className={ui.input} value={d.number} onChange={(e) => set({ ...d, number: e.target.value })} maxLength={100} required />
        </label>
      ) : null}
      <label className={ui.label}>
        {t("type")}
        <select className={ui.input} value={d.meter_type_code} onChange={(e) => set({ ...d, meter_type_code: e.target.value })} required>
          <option value="">{t("chooseType")}</option>
          {types.map((c) => (
            <option key={c.code} value={c.code}>
              {c.label}
            </option>
          ))}
        </select>
      </label>
      <label className={ui.label}>
        {t("unit")}
        <select className={ui.input} value={d.unit_id} onChange={(e) => set({ ...d, unit_id: e.target.value })}>
          <option value="">{t("wholeProperty")}</option>
          {units.map((u) => (
            <option key={u.id} value={u.id}>
              {[u.number, u.label].filter(Boolean).join(" ")}
            </option>
          ))}
        </select>
      </label>
      <label className={ui.label}>
        {t("location")}
        <input className={ui.input} value={d.location} onChange={(e) => set({ ...d, location: e.target.value })} maxLength={200} />
      </label>
      <label className={ui.label}>
        {t("connection")}
        <select className={ui.input} value={d.connection} onChange={(e) => set({ ...d, connection: e.target.value })}>
          <option value="main">{t("connections.main")}</option>
          <option value="sub">{t("connections.sub")}</option>
        </select>
      </label>
      <label className={ui.label}>
        {t("validFrom")}
        <input type="date" className={ui.input} value={d.valid_from} onChange={(e) => set({ ...d, valid_from: e.target.value })} required />
      </label>
      <label className={ui.label}>
        {t("validTo")}
        <input type="date" className={ui.input} value={d.valid_to} onChange={(e) => set({ ...d, valid_to: e.target.value })} />
      </label>
      <label className={ui.label}>
        {t("calibrationDue")}
        <input type="date" className={ui.input} value={d.calibration_due_date} onChange={(e) => set({ ...d, calibration_due_date: e.target.value })} />
      </label>
      <label className="inline-flex items-center gap-2 self-end text-sm">
        <input type="checkbox" checked={d.remote_readable} onChange={(e) => set({ ...d, remote_readable: e.target.checked })} />
        {t("remoteReadable")}
      </label>
    </div>
  );

  return (
    <section id="zaehler" className={ui.card} data-testid="property-meters" aria-label={t("title")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={ui.subtitle}>{t("title")}</h2>
        {canCreate && !adding ? (
          <button type="button" className={ui.buttonSm} onClick={() => setAdding(true)}>
            {t("add")}
          </button>
        ) : null}
      </div>
      <p className={`${ui.help} mt-1`}>{t("hint")}</p>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("number")}</th>
                <th>{t("type")}</th>
                <th>{t("unit")}</th>
                <th>{t("location")}</th>
                <th>{t("validity")}</th>
                <th>{t("calibrationDue")}</th>
                {canEdit ? <th /> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className={row.valid_to && row.valid_to < todayIso() ? "text-muted" : undefined}>
                  <td>
                    <span className={`${ui.mono} font-medium`}>{row.number}</span>
                    {editing === row.id && editDraft ? (
                      <div className="mt-2 flex flex-col gap-3 border-t border-border pt-3" data-testid="meter-edit">
                        {form(editDraft, setEditDraft, false)}
                        <div className={ui.formActions}>
                          <button type="button" className={ui.primary} disabled={busy || !draftValid(editDraft)} onClick={() => void save(row.id)}>
                            {t("save")}
                          </button>
                          <button type="button" className={ui.button} onClick={() => setEditing(null)}>
                            {t("cancel")}
                          </button>
                        </div>
                      </div>
                    ) : null}
                    {changing === row.id ? (
                      <div className="mt-2 flex flex-col gap-3 border-t border-border pt-3" data-testid="meter-change">
                        <p className="text-sm">{t("changeHint", { number: row.number })}</p>
                        <div className="grid gap-3 sm:grid-cols-2">
                          <label className={ui.label}>
                            {t("changedOn")}
                            <input type="date" className={ui.input} value={change.changed_on} onChange={(e) => setChange({ ...change, changed_on: e.target.value })} required />
                          </label>
                          <label className={ui.label}>
                            {t("newNumber")}
                            <input className={ui.input} value={change.new_number} onChange={(e) => setChange({ ...change, new_number: e.target.value })} maxLength={100} />
                          </label>
                          <label className={ui.label}>
                            {t("oldFinalValue")}
                            <input className={ui.input} inputMode="decimal" value={change.old_final_value} onChange={(e) => setChange({ ...change, old_final_value: e.target.value })} required />
                          </label>
                          <label className={ui.label}>
                            {t("newInitialValue")}
                            <input className={ui.input} inputMode="decimal" value={change.new_initial_value} onChange={(e) => setChange({ ...change, new_initial_value: e.target.value })} required />
                          </label>
                        </div>
                        <div className={ui.formActions}>
                          <button type="button" className={ui.primary} disabled={busy || !changeValid} onClick={() => void replace(row.id)}>
                            {t("recordChange")}
                          </button>
                          <button type="button" className={ui.button} onClick={() => setChanging(null)}>
                            {t("cancel")}
                          </button>
                        </div>
                      </div>
                    ) : null}
                  </td>
                  <td>{typeLabel(row.meter_type_code)}</td>
                  <td>{unitLabel(row.unit_id)}</td>
                  <td>{row.location ?? ""}</td>
                  <td className="whitespace-nowrap">
                    {formatDate(row.valid_from)}
                    {row.valid_to ? ` ${t("until")} ${formatDate(row.valid_to)}` : ""}
                  </td>
                  <td className="whitespace-nowrap">{row.calibration_due_date ? formatDate(row.calibration_due_date) : ""}</td>
                  {canEdit ? (
                    <td className="whitespace-nowrap">
                      <div className="flex gap-1">
                        <button
                          type="button"
                          className={ui.buttonSm}
                          onClick={() => {
                            setChanging(null);
                            setEditing(row.id);
                            setEditDraft(draftOf(row));
                          }}
                        >
                          {t("edit")}
                        </button>
                        <button
                          type="button"
                          className={ui.buttonSm}
                          onClick={() => {
                            setEditing(null);
                            setChanging(row.id);
                          }}
                        >
                          {t("change")}
                        </button>
                      </div>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {adding ? (
        <div role="dialog" aria-modal="false" aria-label={t("add")} className="mt-3 flex flex-col gap-3 border-t border-border pt-3" data-testid="meter-add">
          {form(draft, setDraft, true)}
          <div className={ui.formActions}>
            <button type="button" className={ui.primary} disabled={busy || !draft.number.trim() || !draftValid(draft)} onClick={() => void add()}>
              {t("create")}
            </button>
            <button type="button" className={ui.button} onClick={() => setAdding(false)}>
              {t("cancel")}
            </button>
          </div>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
