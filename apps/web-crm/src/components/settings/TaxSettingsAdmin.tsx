"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Shapes of /api/v1/accounting/tax (M14-02, M14-03, M14-04). Local types, the generated
 *  api-client is regenerated centrally. Every value is a draft with the source status
 *  "zu prüfen durch Steuerberater"; the switches are off by default. */
export type ApprovalLimit = { role_code: string; limit_amount: string };

export type TaxSettings = {
  input_tax_enabled: boolean;
  input_tax_account_number: string | null;
  construction_withholding_enabled: boolean;
  construction_withholding_percent: string;
  section_35a_enabled: boolean;
  approval_limits_enabled: boolean;
  approval_limits: ApprovalLimit[];
};

export type PropertyTaxProfile = {
  property_id: string;
  vat_opted: boolean;
  revenue_key_percent: string | null;
  note: string | null;
};

export type SupplierTaxProfile = {
  contact_id: string;
  construction_services: boolean;
  reverse_charge: boolean;
  exemption_number: string | null;
  exemption_valid_from: string | null;
  exemption_valid_to: string | null;
  exemption_document_id: string | null;
  note: string | null;
  exemption_valid_today: boolean;
};

export type RoleOption = { code: string; name: string };
export type PropertyOption = { id: string; number: string; name: string };
export type ContactOption = { id: string; display_name: string };

const BASE = "/api/bff/accounting/tax";

function trimDecimal(value: string | null): string {
  if (value === null || value === undefined) return "";
  const n = Number(value);
  return Number.isFinite(n) ? String(n) : value;
}

export function TaxSettingsAdmin({
  initial,
  roles,
  properties,
  contacts,
  canManageSettings,
  canManageProfiles,
}: {
  initial: TaxSettings;
  roles: RoleOption[];
  properties: PropertyOption[];
  contacts: ContactOption[];
  canManageSettings: boolean;
  canManageProfiles: boolean;
}) {
  const t = useTranslations("TaxSettings");
  const [settings, setSettings] = useState<TaxSettings>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [propertyId, setPropertyId] = useState(properties[0]?.id ?? "");
  const [property, setProperty] = useState<PropertyTaxProfile | null>(null);
  const [contactId, setContactId] = useState(contacts[0]?.id ?? "");
  const [supplier, setSupplier] = useState<SupplierTaxProfile | null>(null);

  function limit(index: number, patch: Partial<ApprovalLimit>) {
    setSettings((s) => ({
      ...s,
      approval_limits: s.approval_limits.map((l, i) => (i === index ? { ...l, ...patch } : l)),
    }));
  }

  async function saveSettings(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<TaxSettings>(`${BASE}/settings`, {
      method: "PUT",
      body: JSON.stringify({
        ...settings,
        input_tax_account_number: settings.input_tax_account_number?.trim() || null,
        construction_withholding_percent: settings.construction_withholding_percent || "15.00",
        approval_limits: settings.approval_limits
          .filter((l) => l.role_code && l.limit_amount !== "")
          .map((l) => ({ role_code: l.role_code, limit_amount: l.limit_amount })),
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setSettings(res.data);
    setMessage(t("saved"));
  }

  async function loadProperty() {
    if (!propertyId) return;
    setError(null);
    const res = await bff<PropertyTaxProfile>(`${BASE}/properties/${propertyId}/profile`);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setProperty(res.data);
  }

  async function saveProperty(event: React.FormEvent) {
    event.preventDefault();
    if (!property) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<PropertyTaxProfile>(`${BASE}/properties/${property.property_id}/profile`, {
      method: "PUT",
      body: JSON.stringify({
        vat_opted: property.vat_opted,
        revenue_key_percent: property.revenue_key_percent?.trim() ? property.revenue_key_percent : null,
        note: property.note?.trim() || null,
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setProperty(res.data);
    setMessage(t("saved"));
  }

  async function loadSupplier() {
    if (!contactId) return;
    setError(null);
    const res = await bff<SupplierTaxProfile>(`${BASE}/suppliers/${contactId}/profile`);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setSupplier(res.data);
  }

  async function saveSupplier(event: React.FormEvent) {
    event.preventDefault();
    if (!supplier) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<SupplierTaxProfile>(`${BASE}/suppliers/${supplier.contact_id}/profile`, {
      method: "PUT",
      body: JSON.stringify({
        construction_services: supplier.construction_services,
        reverse_charge: supplier.reverse_charge,
        exemption_number: supplier.exemption_number?.trim() || null,
        exemption_valid_from: supplier.exemption_valid_from || null,
        exemption_valid_to: supplier.exemption_valid_to || null,
        exemption_document_id: supplier.exemption_document_id?.trim() || null,
        note: supplier.note?.trim() || null,
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setSupplier(res.data);
    setMessage(t("saved"));
  }

  return (
    <div className={ui.sectionGap}>
      <p className={ui.notice}>{t("notice")}</p>
      {error ? <p className={ui.alert}>{error}</p> : null}
      {message ? <p className={ui.success}>{message}</p> : null}

      <form onSubmit={saveSettings} className={ui.card}>
        <h2 id="tax-switches-title" className={ui.h2}>{t("switches.title")}</h2>
        <p className={ui.help}>{t("switches.help")}</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={settings.input_tax_enabled}
              disabled={!canManageSettings}
              onChange={(e) => setSettings({ ...settings, input_tax_enabled: e.target.checked })}
            />
            {t("switches.inputTax")}
          </label>
          <label className={ui.label}>
            {t("switches.inputTaxAccount")}
            <input
              className={ui.input}
              value={settings.input_tax_account_number ?? ""}
              disabled={!canManageSettings}
              placeholder="026000"
              maxLength={6}
              onChange={(e) => setSettings({ ...settings, input_tax_account_number: e.target.value })}
            />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={settings.construction_withholding_enabled}
              disabled={!canManageSettings}
              onChange={(e) => setSettings({ ...settings, construction_withholding_enabled: e.target.checked })}
            />
            {t("switches.withholding")}
          </label>
          <label className={ui.label}>
            {t("switches.withholdingPercent")}
            <input
              className={ui.input}
              value={trimDecimal(settings.construction_withholding_percent)}
              disabled={!canManageSettings}
              inputMode="decimal"
              onChange={(e) => setSettings({ ...settings, construction_withholding_percent: e.target.value })}
            />
            <span className={ui.help}>{t("switches.withholdingSource")}</span>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={settings.section_35a_enabled}
              disabled={!canManageSettings}
              onChange={(e) => setSettings({ ...settings, section_35a_enabled: e.target.checked })}
            />
            {t("switches.section35a")}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={settings.approval_limits_enabled}
              disabled={!canManageSettings}
              onChange={(e) => setSettings({ ...settings, approval_limits_enabled: e.target.checked })}
            />
            {t("switches.limits")}
          </label>
        </div>

        <h3 id="tax-limits-title" className={`${ui.h3} mt-4`}>{t("limits.title")}</h3>
        <p className={ui.help}>{t("limits.help")}</p>
        <table className={`${ui.table} mt-2`}>
          <thead>
            <tr>
              <th>{t("limits.role")}</th>
              <th>{t("limits.amount")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {settings.approval_limits.map((row, index) => (
              <tr key={index}>
                <td>
                  <select
                    className={ui.input}
                    aria-label={t("limits.role")}
                    value={row.role_code}
                    disabled={!canManageSettings}
                    onChange={(e) => limit(index, { role_code: e.target.value })}
                  >
                    <option value="">{t("limits.chooseRole")}</option>
                    {roles.map((r) => (
                      <option key={r.code} value={r.code}>
                        {r.name} ({r.code})
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    className={ui.input}
                    aria-label={t("limits.amount")}
                    value={row.limit_amount}
                    disabled={!canManageSettings}
                    inputMode="decimal"
                    onChange={(e) => limit(index, { limit_amount: e.target.value })}
                  />
                </td>
                <td>
                  {canManageSettings ? (
                    <button
                      type="button"
                      className={ui.buttonSm}
                      onClick={() =>
                        setSettings({ ...settings, approval_limits: settings.approval_limits.filter((_, i) => i !== index) })
                      }
                    >
                      {t("limits.remove")}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
            {settings.approval_limits.length === 0 ? (
              <tr>
                <td colSpan={3} className={ui.help}>
                  {t("limits.empty")}
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
        {canManageSettings ? (
          <div className={`${ui.formActions} mt-3`}>
            <button
              type="button"
              className={ui.button}
              onClick={() =>
                setSettings({ ...settings, approval_limits: [...settings.approval_limits, { role_code: "", limit_amount: "" }] })
              }
            >
              {t("limits.add")}
            </button>
            <button type="submit" className={ui.primary} disabled={busy}>
              {t("save")}
            </button>
          </div>
        ) : null}
      </form>

      <section className={ui.card}>
        <h2 id="tax-property-title" className={ui.h2}>{t("property.title")}</h2>
        <p className={ui.help}>{t("property.help")}</p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <select
            className={ui.input}
            aria-label={t("property.select")}
            value={propertyId}
            onChange={(e) => {
              setPropertyId(e.target.value);
              setProperty(null);
            }}
          >
            {properties.map((p) => (
              <option key={p.id} value={p.id}>
                {p.number} {p.name}
              </option>
            ))}
          </select>
          <button type="button" className={ui.button} onClick={loadProperty} disabled={!propertyId}>
            {t("load")}
          </button>
        </div>
        {property ? (
          <form onSubmit={saveProperty} className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={property.vat_opted}
                disabled={!canManageProfiles}
                onChange={(e) => setProperty({ ...property, vat_opted: e.target.checked })}
              />
              {t("property.opted")}
            </label>
            <label className={ui.label}>
              {t("property.revenueKey")}
              <input
                className={ui.input}
                value={property.revenue_key_percent ?? ""}
                disabled={!canManageProfiles}
                inputMode="decimal"
                onChange={(e) => setProperty({ ...property, revenue_key_percent: e.target.value })}
              />
            </label>
            <label className={`${ui.label} sm:col-span-2`}>
              {t("note")}
              <input
                className={ui.input}
                value={property.note ?? ""}
                disabled={!canManageProfiles}
                onChange={(e) => setProperty({ ...property, note: e.target.value })}
              />
            </label>
            {canManageProfiles ? (
              <div className={ui.formActions}>
                <button type="submit" className={ui.primary} disabled={busy}>
                  {t("property.save")}
                </button>
              </div>
            ) : null}
          </form>
        ) : null}
      </section>

      <section className={ui.card}>
        <h2 id="tax-supplier-title" className={ui.h2}>{t("supplier.title")}</h2>
        <p className={ui.help}>{t("supplier.help")}</p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <select
            className={ui.input}
            aria-label={t("supplier.select")}
            value={contactId}
            onChange={(e) => {
              setContactId(e.target.value);
              setSupplier(null);
            }}
          >
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.display_name}
              </option>
            ))}
          </select>
          <button type="button" className={ui.button} onClick={loadSupplier} disabled={!contactId}>
            {t("load")}
          </button>
        </div>
        {supplier ? (
          <form onSubmit={saveSupplier} className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={supplier.construction_services}
                disabled={!canManageProfiles}
                onChange={(e) => setSupplier({ ...supplier, construction_services: e.target.checked })}
              />
              {t("supplier.construction")}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={supplier.reverse_charge}
                disabled={!canManageProfiles}
                onChange={(e) => setSupplier({ ...supplier, reverse_charge: e.target.checked })}
              />
              {t("supplier.reverseCharge")}
            </label>
            <label className={ui.label}>
              {t("supplier.exemptionNumber")}
              <input
                className={ui.input}
                value={supplier.exemption_number ?? ""}
                disabled={!canManageProfiles}
                onChange={(e) => setSupplier({ ...supplier, exemption_number: e.target.value })}
              />
            </label>
            <label className={ui.label}>
              {t("supplier.exemptionDocument")}
              <input
                className={ui.input}
                value={supplier.exemption_document_id ?? ""}
                disabled={!canManageProfiles}
                onChange={(e) => setSupplier({ ...supplier, exemption_document_id: e.target.value })}
              />
            </label>
            <label className={ui.label}>
              {t("supplier.validFrom")}
              <input
                className={ui.input}
                type="date"
                value={supplier.exemption_valid_from ?? ""}
                disabled={!canManageProfiles}
                onChange={(e) => setSupplier({ ...supplier, exemption_valid_from: e.target.value })}
              />
            </label>
            <label className={ui.label}>
              {t("supplier.validTo")}
              <input
                className={ui.input}
                type="date"
                value={supplier.exemption_valid_to ?? ""}
                disabled={!canManageProfiles}
                onChange={(e) => setSupplier({ ...supplier, exemption_valid_to: e.target.value })}
              />
            </label>
            <p className={`${ui.help} sm:col-span-2`}>
              {supplier.exemption_valid_today ? t("supplier.validToday") : t("supplier.invalidToday")}
            </p>
            {canManageProfiles ? (
              <div className={ui.formActions}>
                <button type="submit" className={ui.primary} disabled={busy}>
                  {t("supplier.save")}
                </button>
              </div>
            ) : null}
          </form>
        ) : null}
      </section>
    </div>
  );
}
