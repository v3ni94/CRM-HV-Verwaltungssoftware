"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** "Vorhandene Schadentickets übernehmen" (INT-SDT-01): remote tickets without a local ticket.
 *  The proposals (property by object number, ticket by the remote externalId) are only
 *  proposals; nothing is created or linked without the member's decision per ticket. */
export type TakeoverRow = {
  id: string;
  remote_id: string | null;
  remote_external_id: string | null;
  remote_title: string | null;
  remote_status: string | null;
  remote_status_label: string | null;
  object_external_id: string | null;
  remote_updated_at: string | null;
  proposed_property_id: string | null;
  proposed_property_label: string | null;
  proposed_ticket_id: string | null;
  proposed_ticket_number: number | null;
};

type Decision = { action: "create" | "link" | "dismiss"; ticket_id?: string; property_id?: string };

export function SchadenstoolTakeover({ canDecide }: { canDecide: boolean }) {
  const t = useTranslations("Schadenstool");
  const [rows, setRows] = useState<TakeoverRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [done, setDone] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const res = await bff<TakeoverRow[]>("/api/bff/integrations/schadenstool/takeover");
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function decide(row: TakeoverRow, decision: Decision) {
    setBusy(row.id);
    setError(null);
    const res = await bff<{ id: string; sync_status: string; ticket_id: string | null }>(
      `/api/bff/integrations/schadenstool/takeover/${row.id}`,
      { method: "POST", body: JSON.stringify(decision) },
    );
    setBusy(null);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setDone((d) => ({ ...d, [row.id]: res.data.ticket_id ?? "" }));
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="sdt-takeover-title">
      <h2 id="sdt-takeover-title" className={ui.h2}>
        {t("takeoverTitle")}
      </h2>
      <p className={ui.help}>{t("takeoverIntro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {rows === null ? <p className={ui.help}>{t("loading")}</p> : null}
      {rows !== null && rows.length === 0 ? <p className={ui.help}>{t("takeoverEmpty")}</p> : null}
      <ul className="flex flex-col gap-3">
        {(rows ?? []).map((row) => (
          <li key={row.id} className="flex flex-col gap-1 border-t border-border pt-2 text-sm">
            <p className="font-medium">{row.remote_title ?? t("untitled")}</p>
            <p className="text-muted">
              {t("remoteStatus")}: {row.remote_status_label ?? t("unknown")}
              {row.remote_updated_at ? ` · ${formatDateTime(row.remote_updated_at)}` : ""}
              {row.object_external_id ? ` · ${t("objectNumber", { number: row.object_external_id })}` : ""}
            </p>
            <p className="text-muted">
              {row.proposed_property_label ? t("proposedProperty", { label: row.proposed_property_label }) : t("noProperty")}
              {row.proposed_ticket_number !== null ? ` · ${t("proposedTicket", { number: row.proposed_ticket_number })}` : ""}
            </p>
            {row.id in done ? (
              <p role="status" className={ui.success}>
                {done[row.id] ? <Link href={`/tickets/${done[row.id]}`}>{t("decidedLinked")}</Link> : t("decidedDismissed")}
              </p>
            ) : canDecide ? (
              <div className={ui.formActions}>
                {row.proposed_ticket_id ? (
                  <button
                    type="button"
                    className={ui.primary}
                    disabled={busy !== null}
                    onClick={() => void decide(row, { action: "link", ticket_id: row.proposed_ticket_id ?? undefined })}
                  >
                    {t("linkProposed")}
                  </button>
                ) : null}
                <button
                  type="button"
                  className={row.proposed_ticket_id ? ui.secondary : ui.primary}
                  disabled={busy !== null}
                  onClick={() => void decide(row, { action: "create", property_id: row.proposed_property_id ?? undefined })}
                >
                  {t("createTicket")}
                </button>
                <button type="button" className={ui.secondary} disabled={busy !== null} onClick={() => void decide(row, { action: "dismiss" })}>
                  {t("dismiss")}
                </button>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
