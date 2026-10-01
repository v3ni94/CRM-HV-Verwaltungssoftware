"use client";

import { useTranslations } from "next-intl";

import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export const CONSENT_WARN_DAYS = 10;

/** Days from `today` (local calendar day) until an ISO date; negative when it is past. */
export function daysUntil(isoDate: string, today: Date = new Date()): number {
  const [y = 0, m = 1, d = 1] = isoDate.slice(0, 10).split("-").map(Number);
  const target = Date.UTC(y, m - 1, d);
  const base = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((target - base) / 86_400_000);
}

/** Hinweis zur Bankzustimmung (A29, 8.2): ab 10 Tagen vor Ablauf ein Warnhinweis mit
 *  Ablaufdatum und "Zustimmung erneuern" (startet den bestehenden finAPI-WebForm-Fluss,
 *  Reconnect). Eine abgelaufene Zustimmung wird deutlich als abgelaufen markiert. */
export function FinApiConsentBanner({
  status,
  consentValidUntil,
  busy,
  onRenew,
  today,
}: {
  status: string;
  consentValidUntil: string | null;
  busy: boolean;
  onRenew: () => void;
  today?: Date;
}) {
  const t = useTranslations("BankConnections");
  const days = consentValidUntil ? daysUntil(consentValidUntil, today) : null;
  const expired = status === "consent_expired" || (days !== null && days < 0);
  const expiring = !expired && days !== null && days <= CONSENT_WARN_DAYS;
  if (!expired && !expiring) {
    // M11-08: permanent status line, so the operator sees the consent state at all times.
    if (status === "web_form_pending" || status === "disabled") return null;
    return (
      <p className="mt-1 text-xs text-muted" data-testid="consent-status">
        {consentValidUntil
          ? t("consentValidUntil", { date: formatDate(consentValidUntil) })
          : t("consentUnknown")}
      </p>
    );
  }
  const date = consentValidUntil ? formatDate(consentValidUntil) : null;
  return (
    <div
      role={expired ? "alert" : "status"}
      data-testid="consent-banner"
      className={`mt-2 flex flex-wrap items-center justify-between gap-2 ${expired ? ui.alert : ui.notice}`}
    >
      <span>
        {expired
          ? date
            ? t("consentExpiredOn", { date })
            : t("consentExpired")
          : t("consentExpiring", { date: date ?? "", days: days ?? 0 })}
      </span>
      <button type="button" className={ui.buttonSm} disabled={busy} onClick={onRenew}>
        {t("renewConsent")}
      </button>
    </div>
  );
}
