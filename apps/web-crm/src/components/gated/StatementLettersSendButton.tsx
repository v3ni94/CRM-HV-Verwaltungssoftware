"use client";

import { useTranslations } from "next-intl";

import { GatedAction } from "./GatedAction";

/** GAI-409 (AJ28): delivery of the statement letters; G3 and M17-04 lock it. */
export function StatementLettersSendButton({ statementId }: { statementId: string }) {
  const t = useTranslations("gatedMasks.statementLettersSend");
  return (
    <GatedAction
      gate="G3"
      url={`/api/bff/statements/${statementId}/letters/send`}
      label={t("action")}
      hint={t("hint")}
      lockedText={t("locked")}
      testId="statement-letters-send"
    />
  );
}
