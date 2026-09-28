"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Lern-Workflow (rule M9-11): rule proposals from repeated manual decisions of the same
 *  sender (`GET /automation/rule-proposals`). A proposal never acts by itself; accepting it
 *  (`POST .../accept`, tenant_settings:update) creates an active rule of the rule engine,
 *  rejecting it (`POST .../reject`, optional reason) suppresses the pattern until its evidence
 *  doubles. The threshold is the tenant setting `rule_proposal_threshold` (default 5). */

export type RuleProposal = {
  id: string;
  entity_type: "message" | "ticket";
  field: string;
  scope: "address" | "domain";
  sender_key: string;
  value: string;
  value_label: string | null;
  status: string;
  evidence_count: number;
  threshold: number;
  evidence: {
    decision_ids: string[];
    addresses: string[];
    first_at?: string | null;
    last_at?: string | null;
  };
  rule_id: string | null;
};

const FIELDS = ["contact", "property", "unit", "topic", "assignee_user_id"] as const;

export function RuleProposals({
  initial,
  canManage,
  initialThreshold = 5,
}: {
  initial: RuleProposal[];
  canManage: boolean;
  initialThreshold?: number;
}) {
  const t = useTranslations("RuleProposals");
  const [rows, setRows] = useState(initial);
  const [busy, setBusy] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<{ text: string; ruleId?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [threshold, setThreshold] = useState(String(initialThreshold));

  const fieldLabel = (field: string) =>
    (FIELDS as readonly string[]).includes(field) ? t(`fields.${field}`) : field;

  async function accept(row: RuleProposal) {
    setBusy(row.id);
    setError(null);
    setMessage(null);
    const res = await bff<RuleProposal>(`/api/bff/automation/rule-proposals/${row.id}/accept`, {
      method: "POST",
    });
    setBusy(null);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setRows((current) => current.filter((r) => r.id !== row.id));
    setMessage({ text: t("accepted"), ruleId: res.data.rule_id ?? undefined });
  }

  async function reject(row: RuleProposal) {
    setBusy(row.id);
    setError(null);
    setMessage(null);
    const res = await bff<RuleProposal>(`/api/bff/automation/rule-proposals/${row.id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason: reason.trim() || null }),
    });
    setBusy(null);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setRows((current) => current.filter((r) => r.id !== row.id));
    setRejecting(null);
    setReason("");
    setMessage({ text: t("rejected") });
  }

  async function saveThreshold() {
    const value = Number(threshold.trim());
    if (!/^\d+$/.test(threshold.trim()) || value < 2 || value > 50) {
      setError(t("thresholdInvalid"));
      return;
    }
    setError(null);
    setMessage(null);
    const res = await bff<{ rule_proposal_threshold: number }>("/api/bff/tenant/settings", {
      method: "PATCH",
      body: JSON.stringify({ rule_proposal_threshold: value }),
    });
    if (res.ok) setMessage({ text: t("thresholdSaved") });
    else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="rule-proposals-title">
      <div className="flex flex-col gap-3">
        <h2 id="rule-proposals-title" className={ui.title}>
          {t("title")} <span className={ui.badgeGold}>{rows.length}</span>
        </h2>
        <p className={ui.notice}>{t("intro")}</p>
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {message ? (
          <p role="status" className={ui.success}>
            {message.text}{" "}
            {message.ruleId ? (
              <Link href="/einstellungen/automatisierung" className="underline">
                {t("toRules")}
              </Link>
            ) : null}
          </p>
        ) : null}
        {rows.length === 0 ? (
          <p className={ui.small}>{t("empty")}</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {rows.map((row) => (
              <li key={row.id} className="rounded-md border border-hairline p-3" data-testid="rule-proposal">
                <p className="font-medium text-fg">
                  {t(`entity.${row.entity_type}`)}: {fieldLabel(row.field)} {row.value_label ?? row.value}
                </p>
                <p className={ui.small}>
                  {t(`scope.${row.scope}`, { sender: row.sender_key })}
                </p>
                <p className={ui.small}>
                  {t("evidence", {
                    count: row.evidence_count,
                    threshold: row.threshold,
                    first: formatDate(row.evidence.first_at ?? null),
                    last: formatDate(row.evidence.last_at ?? null),
                  })}
                </p>
                {row.scope === "domain" && row.evidence.addresses.length > 0 ? (
                  <p className={ui.small}>
                    {t("addresses", { addresses: row.evidence.addresses.join(", ") })}
                  </p>
                ) : null}
                {canManage ? (
                  rejecting === row.id ? (
                    <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-end">
                      <label className="flex flex-1 flex-col gap-1">
                        <span className={ui.label}>{t("reason")}</span>
                        <input
                          className={ui.input}
                          value={reason}
                          maxLength={500}
                          onChange={(e) => setReason(e.target.value)}
                        />
                      </label>
                      <button
                        type="button"
                        className={ui.danger}
                        disabled={busy === row.id}
                        onClick={() => void reject(row)}
                      >
                        {t("confirmReject")}
                      </button>
                      <button type="button" className={ui.button} onClick={() => setRejecting(null)}>
                        {t("cancel")}
                      </button>
                    </div>
                  ) : (
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button
                        type="button"
                        className={ui.primary}
                        disabled={busy === row.id}
                        onClick={() => void accept(row)}
                      >
                        {t("accept")}
                      </button>
                      <button
                        type="button"
                        className={ui.button}
                        disabled={busy === row.id}
                        onClick={() => {
                          setRejecting(row.id);
                          setReason("");
                        }}
                      >
                        {t("reject")}
                      </button>
                    </div>
                  )
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {canManage ? (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("thresholdLabel")}</span>
              <input
                type="number"
                min={2}
                max={50}
                className={ui.input}
                data-testid="rule-proposal-threshold"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
              />
            </label>
            <button type="button" className={ui.button} onClick={() => void saveThreshold()}>
              {t("thresholdSave")}
            </button>
          </div>
        ) : (
          <p className={ui.help}>{t("readOnly")}</p>
        )}
        <p className={ui.help}>{t("thresholdHint")}</p>
      </div>
    </section>
  );
}

/** Hint badge for headers (mail workspace): link to the proposals with the open count. */
export function RuleProposalsBadge({ count }: { count: number }) {
  const t = useTranslations("RuleProposals");
  if (count <= 0) return null;
  return (
    <Link
      href="/einstellungen/regelvorschlaege"
      className={ui.button}
      data-testid="rule-proposals-badge"
      title={t("badgeHint", { count })}
    >
      {t("title")} <span className={ui.badgeGold}>{count}</span>
    </Link>
  );
}
