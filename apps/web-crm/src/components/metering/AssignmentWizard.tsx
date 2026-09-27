"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { type Assignment, type MeteringConnection, SERVICE_SCOPES } from "@/lib/metering";
import { ui } from "@/lib/ui";

/** Assignment wizard (section 6), identical in the object tab and centrally: connection,
 *  property (fixed in the tab, searched centrally), external billing unit by manual entry (no
 *  adapter lists billing units in stage 1), scope, validity. Internal and external data are
 *  shown side by side before saving. */
type PropertyOption = { id: string; number: string; name: string; street?: string | null; house_number?: string | null; postal_code?: string | null; city?: string | null };

export function AssignmentWizard({
  connections,
  property,
  onCreated,
  onCancel,
}: {
  connections: MeteringConnection[];
  property?: PropertyOption;
  onCreated: (assignment: Assignment) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("Metering");
  const [connectionId, setConnectionId] = useState(connections[0]?.id ?? "");
  const [selected, setSelected] = useState<PropertyOption | null>(property ?? null);
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<PropertyOption[]>([]);
  const [externalNumber, setExternalNumber] = useState("");
  const [externalName, setExternalName] = useState("");
  const [externalAddress, setExternalAddress] = useState("");
  const [scope, setScope] = useState<string>("heating");
  const [validFrom, setValidFrom] = useState("");
  const [validTo, setValidTo] = useState("");
  const [primary, setPrimary] = useState(true);
  const [expectedUnits, setExpectedUnits] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const connection = connections.find((c) => c.id === connectionId);

  async function search() {
    const res = await bff<PropertyOption[]>(`/api/bff/properties?q=${encodeURIComponent(query)}&limit=20`);
    if (res.ok) setOptions(res.data);
    else setError(res.message);
  }

  async function save() {
    if (!selected || !connection) return;
    setBusy(true);
    setError(null);
    const res = await bff<Assignment>("/api/bff/metering/assignments", {
      method: "POST",
      body: JSON.stringify({
        connection_id: connection.id,
        property_id: selected.id,
        external_number: externalNumber.trim(),
        external_name: externalName.trim() || null,
        external_address: externalAddress.trim() || null,
        service_scope: scope,
        valid_from: validFrom,
        valid_to: validTo || null,
        is_primary: primary,
        expected_unit_count: expectedUnits.trim() ? Number(expectedUnits) : null,
        note: note.trim() || null,
      }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    onCreated(res.data);
  }

  const address = selected
    ? [[selected.street, selected.house_number].filter(Boolean).join(" "), [selected.postal_code, selected.city].filter(Boolean).join(" ")].filter(Boolean).join(", ")
    : "";
  const canSave = Boolean(selected && connection && externalNumber.trim() && validFrom);

  return (
    <section className={ui.card} data-testid="metering-assignment-wizard" aria-label={t("assignment.wizardTitle")}>
      <h3 className={ui.subtitle}>{t("assignment.wizardTitle")}</h3>
      {error ? (
        <p role="alert" className={`${ui.alert} my-2`}>
          {error}
        </p>
      ) : null}
      {connections.length === 0 ? <p className={`${ui.notice} my-2`}>{t("assignment.noConnections")}</p> : null}
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("assignment.connection")}</span>
          <select className={ui.input} value={connectionId} onChange={(e) => setConnectionId(e.target.value)}>
            {connections.map((c) => (
              <option key={c.id} value={c.id}>
                {c.display_name} ({t(`environment.${c.environment}`)})
              </option>
            ))}
          </select>
        </label>
        {property ? null : (
          <div className="flex flex-col gap-1">
            <span className={ui.label}>{t("assignment.property")}</span>
            <div className="flex gap-2">
              <input className={ui.input} value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("assignment.propertySearch")} aria-label={t("assignment.propertySearch")} />
              <button type="button" className={ui.button} onClick={search}>
                {t("search")}
              </button>
            </div>
            {options.length ? (
              <select className={ui.input} value={selected?.id ?? ""} onChange={(e) => setSelected(options.find((o) => o.id === e.target.value) ?? null)} aria-label={t("assignment.property")}>
                <option value="">{t("assignment.choose")}</option>
                {options.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.number} {o.name}
                  </option>
                ))}
              </select>
            ) : null}
          </div>
        )}
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div className={ui.notice} data-testid="assignment-internal">
          <p className={ui.subtitle}>{t("assignment.internal")}</p>
          <p className="mt-1 text-sm">
            {t("assignment.hvmNumber")}: <span className="font-mono">{selected?.number ?? "..."}</span>
          </p>
          <p className="text-sm">{selected?.name ?? ""}</p>
          <p className="text-xs text-muted">{address}</p>
        </div>
        <div className={ui.notice} data-testid="assignment-external">
          <p className={ui.subtitle}>{t("assignment.external")}</p>
          <p className="mt-1 text-xs text-muted">{t("assignment.manualEntryHint")}</p>
          <label className="mt-2 flex flex-col gap-1">
            <span className={ui.label}>{t("assignment.externalNumber")}</span>
            <input className={`${ui.input} font-mono`} value={externalNumber} onChange={(e) => setExternalNumber(e.target.value)} maxLength={64} inputMode="text" />
            <span className={ui.help}>{t("assignment.externalNumberHint")}</span>
          </label>
          <label className="mt-2 flex flex-col gap-1">
            <span className={ui.label}>{t("assignment.externalName")}</span>
            <input className={ui.input} value={externalName} onChange={(e) => setExternalName(e.target.value)} maxLength={200} />
          </label>
          <label className="mt-2 flex flex-col gap-1">
            <span className={ui.label}>{t("assignment.externalAddress")}</span>
            <input className={ui.input} value={externalAddress} onChange={(e) => setExternalAddress(e.target.value)} maxLength={400} />
          </label>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("assignment.scope")}</span>
          <select className={ui.input} value={scope} onChange={(e) => setScope(e.target.value)}>
            {SERVICE_SCOPES.map((s) => (
              <option key={s} value={s}>
                {t(`scope.${s}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("assignment.validFrom")}</span>
          <input className={ui.input} type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("assignment.validTo")}</span>
          <input className={ui.input} type="date" value={validTo} onChange={(e) => setValidTo(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("assignment.expectedUnits")}</span>
          <input className={ui.input} type="number" min={0} value={expectedUnits} onChange={(e) => setExpectedUnits(e.target.value)} />
        </label>
        <label className="flex items-center gap-2 text-sm md:mt-5">
          <input type="checkbox" checked={primary} onChange={(e) => setPrimary(e.target.checked)} />
          {t("assignment.primary")}
        </label>
        <label className="flex flex-col gap-1 md:col-span-3">
          <span className={ui.label}>{t("assignment.note")}</span>
          <textarea className={ui.input} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
      </div>
      <p className={`${ui.help} mt-2`}>{t("assignment.confirmHint")}</p>
      <div className={`${ui.formActions} mt-3`}>
        <button type="button" className={ui.primary} disabled={!canSave || busy} onClick={save} data-testid="assignment-save">
          {t("assignment.save")}
        </button>
        <button type="button" className={ui.button} onClick={onCancel}>
          {t("cancel")}
        </button>
      </div>
    </section>
  );
}
