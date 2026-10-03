"use client";

import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

import { GateStatusNotice } from "./GateStatusNotice";
import { useReleaseGate } from "./useReleaseGate";

/** GAJ-203: single statement of one unit as PDF (draft) for review before output. Needs gate G4
 *  and the internal approval; the API decides again and stays the authority. */
export function UnitStatementPdfLink({ statementId, units, approved }: { statementId: string; units: { unit_id: string; unit_number: string }[]; approved: boolean }) {
  const t = useTranslations("gatedMasks.unitPdf");
  const state = useReleaseGate("G4");
  const usable = state.status === "open" && approved;
  if (units.length === 0) return null;
  return (
    <div className="flex flex-col gap-1" data-testid="unit-statement-pdf">
      <span className={ui.label}>{t("title")}</span>
      <ul className="flex flex-wrap gap-2">
        {units.map((u) => (
          <li key={u.unit_id}>
            {usable ? (
              <a className={ui.buttonSm} href={`/api/bff/hoa/statements/${statementId}/units/${u.unit_id}/pdf`} target="_blank" rel="noopener noreferrer">
                {t("action", { unit: u.unit_number })}
              </a>
            ) : (
              <button type="button" className={ui.buttonSm} disabled>
                {t("action", { unit: u.unit_number })}
              </button>
            )}
          </li>
        ))}
      </ul>
      <span className={ui.help}>{approved ? t("hint") : t("notApproved")}</span>
      <GateStatusNotice gate="G4" state={state} lockedText={t("locked")} />
    </div>
  );
}
