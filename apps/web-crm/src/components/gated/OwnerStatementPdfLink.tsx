"use client";

import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

import { GateStatusNotice } from "./GateStatusNotice";
import { useReleaseGate } from "./useReleaseGate";

/** GAI-409 (AJ28): PDF output of an owner statement; G3 and the internal approval are required. */
export function OwnerStatementPdfLink({ statementId, approved }: { statementId: string; approved: boolean }) {
  const t = useTranslations("gatedMasks.ownerPdf");
  const state = useReleaseGate("G3");
  const usable = state.status === "open" && approved;
  return (
    <div className="flex flex-col gap-1" data-testid="owner-statement-pdf">
      <div className="flex flex-wrap items-center gap-2">
        {usable ? (
          <a className={ui.buttonSm} href={`/api/bff/billing/owner-statements/${statementId}/pdf`} target="_blank" rel="noopener noreferrer">
            {t("action")}
          </a>
        ) : (
          <button type="button" className={ui.buttonSm} disabled>
            {t("action")}
          </button>
        )}
        <span className={ui.help}>{approved ? t("hint") : t("notApproved")}</span>
      </div>
      <GateStatusNotice gate="G3" state={state} lockedText={t("locked")} />
    </div>
  );
}
