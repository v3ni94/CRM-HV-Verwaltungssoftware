"use client";

import { useTranslations } from "next-intl";

import { GatedAction } from "./GatedAction";

/** GAI-408 (AJ28): dispatch of the dunning letter; G1 and the dispatch release (M16-02) lock it. */
export function DunningLetterSendButton({ caseId }: { caseId: string }) {
  const t = useTranslations("gatedMasks.dunningSend");
  return (
    <GatedAction
      gate="G1"
      url={`/api/bff/accounting/dunning-cases/${caseId}/letter/send`}
      label={t("action")}
      hint={t("hint")}
      lockedText={t("locked")}
      testId="dunning-letter-send"
    />
  );
}
