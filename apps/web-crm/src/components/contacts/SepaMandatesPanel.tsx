"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type SepaMandate = components["schemas"]["SepaMandateOut"];

export function SepaMandatesPanel({ contactId, mandates }: { contactId: string; mandates: SepaMandate[] }) {
  const t = useTranslations("Contacts");
  const tl = useTranslations("Labels");
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function revoke(accountId: string, ibanMasked: string) {
    if (!window.confirm(t("sepaMandates.revokeConfirm", { iban: ibanMasked }))) return;
    setError(null);
    setBusy(accountId);
    const result = await bff(`/api/bff/contacts/${contactId}/bank-accounts/${accountId}/mandate/revoke`, { method: "POST" });
    setBusy(null);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    router.refresh();
  }

  if (!mandates.length) return <p className="text-sm text-muted">{t("none")}</p>;

  return (
    <div className="flex flex-col gap-2">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-left text-xs text-muted">
            <tr>
              <th className="py-1 pr-3 font-medium">{t("sepaMandates.iban")}</th>
              <th className="py-1 pr-3 font-medium">{t("sepaMandates.reference")}</th>
              <th className="py-1 pr-3 font-medium">{t("sepaMandates.signedOn")}</th>
              <th className="py-1 pr-3 font-medium">{t("sepaMandates.status")}</th>
              <th className="py-1" />
            </tr>
          </thead>
          <tbody>
            {mandates.map((m) => (
              <tr key={m.bank_account_id} className="border-b border-border">
                <td className="py-1 pr-3 font-mono">{m.iban_masked}</td>
                <td className="py-1 pr-3">{m.mandate_reference ?? ""}</td>
                <td className="py-1 pr-3">{m.mandate_signed_on ? formatDate(m.mandate_signed_on) : ""}</td>
                <td className="py-1 pr-3">
                  {tl(`mandateStatus.${m.mandate_status}`)}
                  {m.mandate_status === "revoked" && m.mandate_revoked_on ? ` (${formatDate(m.mandate_revoked_on)})` : ""}
                </td>
                <td className="py-1 text-right">
                  {m.mandate_status === "active" ? (
                    <button
                      type="button"
                      className={ui.button}
                      disabled={busy === m.bank_account_id}
                      onClick={() => void revoke(m.bank_account_id, m.iban_masked)}
                    >
                      {t("sepaMandates.revoke")}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
