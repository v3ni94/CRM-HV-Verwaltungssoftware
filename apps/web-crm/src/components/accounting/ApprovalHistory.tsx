"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type ApprovalDecisionRow = {
  id: string;
  step: string;
  user_id: string;
  subject_snapshot_hash: string;
  status: string;
  decided_at: string;
  invalidated_at: string | null;
  invalidation_reason: string | null;
  warnings: string[];
};

/** Freigabeverlauf eines Vorgangs (GAH-106, 6.9.9, D35, D36): jede Freigabe mit Prüfsumme des
 *  freigegebenen Stands, eine entwertete Freigabe mit Grund und die Personenhinweise (S69-03).
 *  Nur Anzeige, keine Aktion. */
export function ApprovalHistory({
  subjectType,
  subjectId,
}: {
  subjectType: "payment_order" | "invoice";
  subjectId: string;
}) {
  const t = useTranslations("Accounting.approvalHistory");
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<ApprovalDecisionRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    const query = new URLSearchParams({ subject_type: subjectType, subject_id: subjectId });
    const res = await bff<ApprovalDecisionRow[]>(`/api/bff/accounting/approval-decisions?${query.toString()}`);
    setLoading(false);
    if (res.ok) setRows(res.data ?? []);
    else setError(res.message);
  }

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && rows === null) await load();
  }

  return (
    <section className="flex flex-col gap-2" aria-label={t("title")}>
      <div>
        <button type="button" className={ui.buttonSm} onClick={() => void toggle()} aria-expanded={open}>
          {open ? t("hide") : t("show")}
        </button>
      </div>
      {open ? (
        <div className="flex flex-col gap-2" data-testid="approval-history">
          {loading ? <p className={ui.help}>{t("loading")}</p> : null}
          {error ? (
            <p role="alert" className={ui.alert}>
              {error}
            </p>
          ) : null}
          {rows && rows.length === 0 ? <p className={ui.help}>{t("empty")}</p> : null}
          {rows && rows.length > 0 ? (
            <ul className="flex flex-col gap-2 text-sm">
              {rows.map((r) => (
                <li key={r.id} className="rounded-md border border-border p-2">
                  <div>
                    <strong>{t.has(`steps.${r.step}`) ? t(`steps.${r.step}`) : r.step}</strong>
                    {" · "}
                    {formatDateTime(r.decided_at)}
                    {" · "}
                    {t.has(`statuses.${r.status}`) ? t(`statuses.${r.status}`) : r.status}
                  </div>
                  <div className="text-xs text-muted">
                    {t("hash")}: <code>{r.subject_snapshot_hash.slice(0, 12)}</code>
                  </div>
                  {r.status === "invalidated" ? (
                    <p className="text-xs text-warning-fg" role="note">
                      {t("invalidated", {
                        at: r.invalidated_at ? formatDateTime(r.invalidated_at) : "",
                        reason: r.invalidation_reason || t("noReason"),
                      })}
                    </p>
                  ) : null}
                  {r.warnings.map((w) => (
                    <p key={w} className="text-xs text-warning-fg" role="note">
                      {t("personWarning", { text: w })}
                    </p>
                  ))}
                </li>
              ))}
            </ul>
          ) : null}
          <p className="text-xs text-muted">{t("note")}</p>
        </div>
      ) : null}
    </section>
  );
}
