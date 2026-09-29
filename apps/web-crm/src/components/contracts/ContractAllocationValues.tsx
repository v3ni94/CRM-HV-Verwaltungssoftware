"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDecimal } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Row of GET /contracts/{id}/allocation-values (4.5 Eigenschaften, migration 0150). */
export type AllocationValueOut = {
  id: string;
  contract_id: string;
  allocation_key_id: string;
  allocation_key_code: string | null;
  allocation_key_name: string | null;
  unit_of_measure: string | null;
  value: string;
  valid_from: string;
  valid_to: string | null;
};

export type AllocationKeyOption = { id: string; code: string; name: string; unit_of_measure: string };

/** Vertragsbezogene Umlagewerte (z. B. Personen) mit Zeitraum. Ein neuer Wert schließt den
 *  offenen Vorwert desselben Schlüssels am Vortag; die Historie bleibt erhalten. */
export function ContractAllocationValues({
  contractId,
  values,
  keys,
  canUpdate,
  startDate,
}: {
  contractId: string;
  values: AllocationValueOut[];
  keys: AllocationKeyOption[];
  canUpdate: boolean;
  startDate: string;
}) {
  const t = useTranslations("contracts");
  const router = useRouter();
  const [rows, setRows] = useState(values);
  const [keyId, setKeyId] = useState(keys[0]?.id ?? "");
  const [value, setValue] = useState("");
  const [validFrom, setValidFrom] = useState(startDate);
  const [validTo, setValidTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!keyId || !value.trim() || !validFrom) {
      setError(t("allocation.errors.required"));
      return;
    }
    setBusy(true);
    const res = await bff<AllocationValueOut>(`/api/bff/contracts/${contractId}/allocation-values`, {
      method: "POST",
      body: JSON.stringify({ allocation_key_id: keyId, value: value.trim().replace(",", "."), valid_from: validFrom, valid_to: validTo || null }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setRows((prev) =>
      [...prev.map((r) => (r.allocation_key_id === res.data.allocation_key_id && r.valid_to === null && r.valid_from < res.data.valid_from ? { ...r, valid_to: previousDay(res.data.valid_from) } : r)), res.data].sort(
        (a, b) => (a.allocation_key_code ?? "").localeCompare(b.allocation_key_code ?? "") || a.valid_from.localeCompare(b.valid_from),
      ),
    );
    setValue("");
    router.refresh();
  }

  return (
    <section className={ui.card} data-testid="contract-allocation-values">
      <h2 className={ui.h2}>{t("allocation.title")}</h2>
      <p className={ui.help}>{t("allocation.help")}</p>
      {rows.length === 0 ? (
        <p className={ui.help}>{t("allocation.none")}</p>
      ) : (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("allocation.key")}</th>
                <th>{t("allocation.value")}</th>
                <th>{t("allocation.validFrom")}</th>
                <th>{t("allocation.validTo")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{r.allocation_key_name ?? r.allocation_key_code ?? r.allocation_key_id}</td>
                  <td>
                    {formatDecimal(r.value, 2)} {r.unit_of_measure ?? ""}
                  </td>
                  <td>{formatDate(r.valid_from)}</td>
                  <td>{r.valid_to ? formatDate(r.valid_to) : t("allocation.open")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {canUpdate && keys.length > 0 ? (
        <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-5" noValidate data-testid="allocation-value-form">
          <label className={ui.label}>
            {t("allocation.key")}
            <select className={ui.input} value={keyId} onChange={(e) => setKeyId(e.target.value)}>
              {keys.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name} ({k.unit_of_measure})
                </option>
              ))}
            </select>
          </label>
          <label className={ui.label}>
            {t("allocation.value")}
            <input className={ui.input} inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} />
          </label>
          <label className={ui.label}>
            {t("allocation.validFrom")}
            <input className={ui.input} type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
          </label>
          <label className={ui.label}>
            {t("allocation.validTo")}
            <input className={ui.input} type="date" value={validTo} onChange={(e) => setValidTo(e.target.value)} />
          </label>
          <div className="flex items-end">
            <button type="submit" className={ui.primary} disabled={busy}>
              {t("allocation.add")}
            </button>
          </div>
          {error ? (
            <p role="alert" className={`${ui.alert} sm:col-span-5`}>
              {error}
            </p>
          ) : null}
        </form>
      ) : canUpdate ? (
        <p className={ui.help}>{t("allocation.noKeys")}</p>
      ) : null}
    </section>
  );
}

function previousDay(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}
