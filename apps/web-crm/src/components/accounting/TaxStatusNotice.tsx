"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/**
 * GAM-210 (D45): hint when accounts with a VAT option exist but the tenant has no usable tax
 * status (unset or Kleinunternehmer): no input tax posting happens then.
 */
export function TaxStatusNotice({ hasVatAccounts }: { hasVatAccounts: boolean }) {
  const t = useTranslations("Bookkeeping");
  const [status, setStatus] = useState<string | null>(null);
  useEffect(() => {
    if (!hasVatAccounts) return;
    let cancelled = false;
    void bff<{ vat_status: string }>("/api/bff/tenant/billing-settings").then((res) => {
      if (!cancelled && res.ok) setStatus(res.data.vat_status);
    });
    return () => {
      cancelled = true;
    };
  }, [hasVatAccounts]);
  if (!hasVatAccounts || status === null || status === "regelbesteuert") return null;
  return (
    <p className={ui.notice} role="status" data-testid="tax-status-notice">
      {status === "kleinunternehmer" ? t("accounts.taxStatusSmall") : t("accounts.taxStatusMissing")}
    </p>
  );
}
