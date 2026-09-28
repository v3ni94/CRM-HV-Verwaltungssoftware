"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import type { ContractSummary } from "./types";

/** Contract as GET /api/v1/contracts?unit_id= returns it (only the fields the picker uses). */
export type ContractOption = {
  id: string;
  number: string;
  kind: string;
  party_name?: string | null;
  start_date: string;
  end_date: string | null;
};

/** "MV-0001, Mustermann, 01.01.2025 bis 30.09.2026" without dashes as punctuation. */
export function contractLabel(c: ContractOption | ContractSummary): string {
  const parts = [c.number, c.party_name || null];
  const term = [c.start_date ? formatDate(c.start_date) : null, c.end_date ? `bis ${formatDate(c.end_date)}` : null]
    .filter(Boolean)
    .join(" ");
  if (term) parts.push(term);
  return parts.filter(Boolean).join(", ");
}

/** Link between a handover protocol and a contract (Package F, handbook Mieterwechsel):
 *  shows the linked contract with a link to the contract page and lets the user pick one of
 *  the unit's contracts (or remove the link). Kept as its own small block so the editor
 *  layout stays untouched for the coming restructuring. */
export function HandoverContractLink({
  base,
  unitId,
  contract,
  disabled,
  onChanged,
  onError,
}: {
  base: string;
  unitId: string | null;
  contract: ContractSummary | null | undefined;
  disabled: boolean;
  onChanged: () => Promise<void>;
  onError: (m: string | null) => void;
}) {
  const t = useTranslations("Handover.contractLink");
  const [options, setOptions] = useState<ContractOption[]>([]);
  const [selected, setSelected] = useState(contract?.id ?? "");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSelected(contract?.id ?? "");
  }, [contract?.id]);

  useEffect(() => {
    setOptions([]);
    if (!unitId || disabled) return;
    let active = true;
    void (async () => {
      const res = await bff<ContractOption[]>(`/api/bff/contracts?unit_id=${encodeURIComponent(unitId)}&limit=200`);
      if (active && res.ok) setOptions(res.data);
    })();
    return () => {
      active = false;
    };
  }, [unitId, disabled]);

  async function save() {
    setBusy(true);
    onError(null);
    const res = await bff(base, {
      method: "PATCH",
      body: JSON.stringify({ contract_id: selected || null }),
    });
    setBusy(false);
    if (res.ok) await onChanged();
    else onError(res.message);
  }

  return (
    <section className={`${ui.card} flex flex-col gap-2`} aria-label={t("title")} data-testid="handover-contract-link">
      <h2 className={ui.h2}>{t("title")}</h2>
      {contract ? (
        <p className="text-sm">
          <Link href={`/vertraege/${contract.id}`} className="font-medium hover:underline">
            {contractLabel(contract)}
          </Link>{" "}
          <span className="text-muted">({t(`kinds.${contract.kind === "ownership" ? "ownership" : "tenancy"}`)})</span>
        </p>
      ) : (
        <p className="text-sm text-muted">{t("none")}</p>
      )}
      {!disabled ? (
        unitId ? (
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex min-w-64 flex-1 flex-col gap-1 text-sm">
              <span className={ui.label}>{t("choose")}</span>
              <select className={ui.input} value={selected} onChange={(e) => setSelected(e.target.value)} aria-label={t("choose")}>
                <option value="">{t("noContract")}</option>
                {options.map((c) => (
                  <option key={c.id} value={c.id}>
                    {contractLabel(c)}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className={ui.buttonSm} disabled={busy || selected === (contract?.id ?? "")} onClick={() => void save()}>
              {t("save")}
            </button>
          </div>
        ) : (
          <p className={ui.help}>{t("needsUnit")}</p>
        )
      ) : null}
      <p className={ui.help}>{t("help")}</p>
    </section>
  );
}
