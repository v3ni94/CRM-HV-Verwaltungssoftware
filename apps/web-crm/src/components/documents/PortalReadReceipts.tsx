"use client";

import { useTranslations } from "next-intl";

import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Portal read receipts of a document (11.3, D34, A53): who opened or downloaded it through
 *  the portal and when. An indication only, kept apart from dispatch evidence and from any
 *  receipt date; the note comes from the API and is shown unchanged. */
export type PortalReadReceipt = {
  id: string;
  account_id: string;
  contact_id: string;
  kind: "opened" | "downloaded";
  occurred_at: string;
};

export type PortalReadReceiptsOut = {
  document_id: string;
  note: string;
  items: PortalReadReceipt[];
};

export function PortalReadReceipts({ data, contactNames = {} }: { data: PortalReadReceiptsOut; contactNames?: Record<string, string> }) {
  const t = useTranslations("ReadReceipts");
  return (
    <section className="flex flex-col gap-2" data-testid="portal-read-receipts">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.notice}>{t("legalNote")}</p>
      <p className="text-xs text-muted">{data.note}</p>
      {data.items.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className={`${ui.card} overflow-x-auto p-0`}>
          <div className="overflow-x-auto">
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("columns.at")}</th>
                  <th>{t("columns.kind")}</th>
                  <th>{t("columns.account")}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id}>
                    <td className="tabular-nums">{formatDateTime(r.occurred_at)}</td>
                    <td>{t(`kind.${r.kind}`)}</td>
                    <td className="text-sm">{contactNames[r.contact_id] ?? r.contact_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
