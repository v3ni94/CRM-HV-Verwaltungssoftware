"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { contractLabel, type ContractOption } from "./HandoverContractLink";
import type { Kind } from "./types";

type Option = { id: string; label: string };

/** Übergabeprotokoll anlegen (M30): kind plus optional property, unit and contract (Package F);
 *  the address is prefilled on the server and stays editable in the protocol. */
export function HandoverCreate({ properties }: { properties: Option[] }) {
  const t = useTranslations("Handover.create");
  const router = useRouter();
  const [kind, setKind] = useState<Kind>("rental");
  const [propertyId, setPropertyId] = useState("");
  const [units, setUnits] = useState<Option[]>([]);
  const [unitId, setUnitId] = useState("");
  const [contracts, setContracts] = useState<ContractOption[]>([]);
  const [contractId, setContractId] = useState("");
  const [manual, setManual] = useState(false);
  const [manualFields, setManualFields] = useState({
    street: "",
    house_number: "",
    postal_code: "",
    city: "",
    floor: "",
    unit_label: "",
    external_object_number: "",
    owner_name: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setManualField(key: keyof typeof manualFields, value: string) {
    setManualFields((prev) => ({ ...prev, [key]: value }));
  }

  useEffect(() => {
    setUnitId("");
    setUnits([]);
    if (!propertyId) return;
    let active = true;
    bff<{ id: string; number: string; label: string | null }[]>(
      `/api/bff/properties/${propertyId}/units`,
    ).then((res) => {
      if (active && res.ok)
        setUnits(
          res.data.map((u) => ({
            id: u.id,
            label: u.label ? `${u.number} (${u.label})` : u.number,
          })),
        );
    });
    return () => {
      active = false;
    };
  }, [propertyId]);

  useEffect(() => {
    setContractId("");
    setContracts([]);
    if (!unitId) return;
    let active = true;
    bff<ContractOption[]>(
      `/api/bff/contracts?unit_id=${encodeURIComponent(unitId)}&limit=200`,
    ).then((res) => {
      if (active && res.ok) setContracts(res.data);
    });
    return () => {
      active = false;
    };
  }, [unitId]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = { kind };
    if (!manual && unitId) body.unit_id = unitId;
    if (!manual && unitId && contractId) body.contract_id = contractId;
    const res = await bff<{ id: string }>("/api/bff/handover/protocols", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      setBusy(false);
      setError(res.message);
      return;
    }
    if (manual) {
      const patch: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(manualFields)) {
        if (value.trim()) patch[key] = value.trim();
      }
      if (Object.keys(patch).length) {
        const patched = await bff(`/api/bff/handover/protocols/${res.data.id}`, {
          method: "PATCH",
          body: JSON.stringify(patch),
        });
        if (!patched.ok) {
          setBusy(false);
          setError(patched.message);
          return;
        }
      }
    }
    setBusy(false);
    router.push(`/makler/uebergabe/${res.data.id}`);
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-4"
      data-testid="handover-create"
    >
      <fieldset className="flex flex-wrap gap-4">
        <legend className={ui.label}>{t("kind")}</legend>
        {(["rental", "sale", "general"] as Kind[]).map((k) => (
          <label key={k} className="flex items-center gap-1.5 text-sm">
            <input
              type="radio"
              name="kind"
              checked={kind === k}
              onChange={() => setKind(k)}
            />
            {t(`kinds.${k}`)}
          </label>
        ))}
      </fieldset>
      <fieldset className="flex flex-wrap gap-4">
        <legend className="sr-only">{t("objectSource.portfolio")}</legend>
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="radio"
            name="objectSource"
            checked={!manual}
            onChange={() => setManual(false)}
          />
          {t("objectSource.portfolio")}
        </label>
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="radio"
            name="objectSource"
            checked={manual}
            onChange={() => setManual(true)}
            data-testid="handover-object-manual"
          />
          {t("objectSource.manual")}
        </label>
      </fieldset>
      {!manual ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="property" className={ui.label}>
              {t("property")}
            </label>
            <select
              id="property"
              className={ui.input}
              value={propertyId}
              onChange={(e) => setPropertyId(e.target.value)}
            >
              <option value="">{t("noProperty")}</option>
              {properties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="unit" className={ui.label}>
              {t("unit")}
            </label>
            <select
              id="unit"
              className={ui.input}
              value={unitId}
              onChange={(e) => setUnitId(e.target.value)}
              disabled={!propertyId}
            >
              <option value="">–</option>
              {units.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.label}
                </option>
              ))}
            </select>
          </div>
          <div className="md:col-span-2">
            <label htmlFor="contract" className={ui.label}>
              {t("contract")}
            </label>
            <select
              id="contract"
              className={ui.input}
              value={contractId}
              onChange={(e) => setContractId(e.target.value)}
              disabled={!unitId}
              data-testid="handover-contract"
            >
              <option value="">{t("noContract")}</option>
              {contracts.map((c) => (
                <option key={c.id} value={c.id}>
                  {contractLabel(c)}
                </option>
              ))}
            </select>
            <p className={ui.help}>{t("contractHelp")}</p>
          </div>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2" data-testid="handover-manual-fields">
          <div>
            <label htmlFor="manual-street" className={ui.label}>
              {t("manual.street")}
            </label>
            <input
              id="manual-street"
              className={ui.input}
              value={manualFields.street}
              onChange={(e) => setManualField("street", e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="manual-house-number" className={ui.label}>
              {t("manual.houseNumber")}
            </label>
            <input
              id="manual-house-number"
              className={ui.input}
              value={manualFields.house_number}
              onChange={(e) => setManualField("house_number", e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="manual-postal-code" className={ui.label}>
              {t("manual.postalCode")}
            </label>
            <input
              id="manual-postal-code"
              className={ui.input}
              value={manualFields.postal_code}
              onChange={(e) => setManualField("postal_code", e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="manual-city" className={ui.label}>
              {t("manual.city")}
            </label>
            <input
              id="manual-city"
              className={ui.input}
              value={manualFields.city}
              onChange={(e) => setManualField("city", e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="manual-floor" className={ui.label}>
              {t("manual.floor")}
            </label>
            <input
              id="manual-floor"
              className={ui.input}
              value={manualFields.floor}
              onChange={(e) => setManualField("floor", e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="manual-unit-label" className={ui.label}>
              {t("manual.unitLabel")}
            </label>
            <input
              id="manual-unit-label"
              className={ui.input}
              value={manualFields.unit_label}
              onChange={(e) => setManualField("unit_label", e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="manual-external-number" className={ui.label}>
              {t("manual.externalObjectNumber")}
            </label>
            <input
              id="manual-external-number"
              className={ui.input}
              value={manualFields.external_object_number}
              onChange={(e) => setManualField("external_object_number", e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="manual-owner-name" className={ui.label}>
              {t("manual.ownerName")}
            </label>
            <input
              id="manual-owner-name"
              className={ui.input}
              value={manualFields.owner_name}
              onChange={(e) => setManualField("owner_name", e.target.value)}
            />
          </div>
        </div>
      )}
      <p className={ui.help}>{manual ? t("manual.help") : t("help")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
        {t("submit")}
      </button>
    </form>
  );
}
