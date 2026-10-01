"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type DueCheckpoint = {
  id: string;
  rule_id: string;
  version: number;
  title: string;
  effective_from: string;
  status: string;
  change_reason: string;
};

/** GA08-02: due dated check points of the rule register. Hint only, no legal effect. */
export function RuleCheckpointsDue() {
  const t = useTranslations("Accounting.ruleCheckpoints");
  const [rows, setRows] = useState<DueCheckpoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    void bff<DueCheckpoint[]>("/api/bff/accounting/rule-versions/due-checkpoints").then((res) => {
      if (!active) return;
      if (res.ok) setRows(res.data ?? []);
      else setError(res.message);
    });
    return () => {
      active = false;
    };
  }, []);
  return (
    <section className="flex flex-col gap-2" data-testid="rule-checkpoints">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.notice}>{t("notice")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : rows === null ? null : rows.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("rule")}</th>
                <th>{t("version")}</th>
                <th>{t("dueOn")}</th>
                <th>{t("status")}</th>
                <th>{t("reason")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    {r.rule_id} {r.title}
                  </td>
                  <td className="num">{r.version}</td>
                  <td>{formatDate(r.effective_from)}</td>
                  <td>{r.status}</td>
                  <td>{r.change_reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
