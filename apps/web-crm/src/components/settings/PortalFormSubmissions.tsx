"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type PortalFormSubmission = {
  id: string;
  template_id: string;
  account_id: string;
  account_status: string;
  contact_id: string;
  contact_name: string;
  created_at: string;
  unit_id: string | null;
  ticket_id: string;
  ticket_number: number | string;
  ticket_status: string;
};

/** Einreichungen einer Portalformular-Vorlage (A73): loaded on demand from
 *  GET /portal-admin/forms/{id}/submissions; each row links to the ticket that was created
 *  from it. The values themselves are on the ticket. */
export function PortalFormSubmissions({ templateId }: { templateId: string }) {
  const t = useTranslations("PortalForms");
  const tt = useTranslations("Tickets");
  const [rows, setRows] = useState<PortalFormSubmission[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setBusy(true);
    setError(null);
    const res = await bff<PortalFormSubmission[]>(`/api/bff/portal-admin/forms/${templateId}/submissions`);
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setRows(res.data);
  }

  return (
    <div className="flex flex-col gap-2" data-testid="portal-form-submissions">
      <div>
        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void load()}>
          {rows === null ? t("submissions.show") : t("submissions.reload")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {rows !== null && rows.length === 0 ? <p className="text-sm text-muted">{t("submissions.empty")}</p> : null}
      {rows !== null && rows.length > 0 ? (
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("submissions.date")}</th>
              <th>{t("submissions.account")}</th>
              <th>{t("submissions.ticket")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{formatDateTime(r.created_at)}</td>
                <td>
                  <Link href={`/kontakte/${r.contact_id}`} className="hover:underline">
                    {r.contact_name}
                  </Link>{" "}
                  <span className="text-xs text-muted">({t(`submissions.accountStatus.${r.account_status}`)})</span>
                </td>
                <td>
                  <Link href={`/tickets/${r.ticket_id}`} className="font-medium hover:underline">
                    {t("submissions.ticketNumber", { number: String(r.ticket_number) })}
                  </Link>{" "}
                  <span className={ui.badge}>{tt(`statuses.${r.ticket_status}`)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}
