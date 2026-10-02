"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { ui } from "@/lib/ui";

import { GatedAction } from "./GatedAction";

/**
 * GAI-410 (AJ28): release of a deposit settlement draft (G3). Four eyes: the releasing person
 * confirms not to be the author of the draft; the API does not enforce this yet (AJ28-04).
 */
export function DepositSettlementReleaseButton({
  settlementId,
  status,
  onReleased,
}: {
  settlementId: string;
  status: string;
  onReleased?: () => void;
}) {
  const t = useTranslations("gatedMasks.depositRelease");
  const [confirmed, setConfirmed] = useState(false);
  const isDraft = status === "draft";
  return (
    <div className="flex flex-col gap-1" data-testid="deposit-settlement-release-box">
      <p className={ui.notice}>{t("fourEyes")}</p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} disabled={!isDraft} />
        {t("confirm")}
      </label>
      <GatedAction
        gate="G3"
        url={`/api/bff/deposit-settlements/${settlementId}/release`}
        label={t("action")}
        hint={isDraft ? undefined : t("notDraft")}
        lockedText={t("locked")}
        blocked={!isDraft || !confirmed}
        onDone={() => onReleased?.()}
        testId="deposit-settlement-release"
      />
    </div>
  );
}
