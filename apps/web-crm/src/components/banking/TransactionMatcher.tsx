"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { settleAmount } from "@/lib/money";
import { ui } from "@/lib/ui";

type Split = { open_item_id: string; amount: string; contract_id?: string | null };
type Proposal = {
  source: "rule" | "match" | "ai";
  kind: string;
  confidence: number | null;
  reasoning: string[] | string | null;
  account_number: string | null;
  rule_id?: string | null;
  splits?: Split[];
  unambiguous?: boolean;
};
type AiProposal = Proposal & {
  id: string;
  decision: string;
  proposed?: { splits?: Split[] };
};
type Proposals = {
  stage1: Proposal[];
  ai: AiProposal[];
  ai_stage: { enabled: boolean; blocked_reason: string | null };
  object_period_lock?: { locked: boolean; code: string | null };
  note: string;
  ledger_id?: string | null;
};

const SOURCE_KEY = {
  rule: "sourceRule",
  match: "sourceMatch",
  ai: "sourceAi",
} as const;

function reasons(value: Proposal["reasoning"]): string {
  if (!value) return "";
  return Array.isArray(value) ? value.join(", ") : value;
}

/** Two stage posting proposals (M12-01): stage 1 is deterministic (rule, match), stage 2 the AI
 *  proposal when released. Every entry shows source, confidence and reasoning; booking needs an
 *  explicit click and confirmation and settles the proposed splits (never more than the payment). */
export function TransactionMatcher({
  txId,
  amount,
}: {
  txId: string;
  amount: string;
}) {
  const t = useTranslations("Bank");
  const router = useRouter();
  const [data, setData] = useState<Proposals | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<Proposals>(
      `/api/bff/banking/transactions/${txId}/posting-proposals`,
    );
    setBusy(false);
    if (res.ok) setData(res.data);
    else setError(res.message);
  };
  const book = async (splits: Split[]) => {
    const settle = settleAmount(
      amount,
      splits.map((s) => s.amount),
    );
    if (!window.confirm(t("confirmBook", { amount: formatEur(settle) })))
      return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/banking/transactions/${txId}/book`, {
      method: "POST",
      body: JSON.stringify({
        settlements: splits.map((s) => ({
          open_item_id: s.open_item_id,
          amount: s.amount,
        })),
      }),
    });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
  };
  const ignore = async () => {
    const reason = window.prompt(t("ignoreReason"));
    if (!reason || reason.trim().length < 3) return;
    setBusy(true);
    const res = await bff(`/api/bff/banking/transactions/${txId}/ignore`, {
      method: "POST",
      body: JSON.stringify({ decision: "ignore", reason: reason.trim() }),
    });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
  };
  const kindLabel = (kind: string) =>
    t.has(`kind.${kind}`) ? t(`kind.${kind}`) : kind;
  const row = (p: Proposal, key: string, splits: Split[] | undefined) => (
    <li key={key} className="flex flex-wrap items-center gap-2">
      <span className="rounded bg-surface-2 px-1 font-medium">
        {t(SOURCE_KEY[p.source])}
      </span>
      <span>{kindLabel(p.kind)}</span>
      {p.confidence !== null && p.confidence !== undefined ? (
        <span className="tabular-nums">
          {t("confidence", { value: Math.round(p.confidence * 100) })}
        </span>
      ) : null}
      {splits && splits.length > 0 ? (
        <span className="tabular-nums">
          {formatEur(
            splits.reduce((sum, s) => sum + Number(s.amount), 0).toFixed(2),
          )}
        </span>
      ) : null}
      {p.account_number ? (
        <span className="text-muted">{p.account_number}</span>
      ) : null}
      <span className="text-muted">{reasons(p.reasoning)}</span>
      {p.unambiguous ? (
        <span className="rounded bg-surface-2 px-1">{t("unambiguous")}</span>
      ) : null}
      {splits && splits.length > 0 ? (
        <span className="flex flex-wrap gap-2">
          {splits.map((s) => (
            <span key={s.open_item_id} className="flex gap-1">
              {data?.ledger_id ? (
                <a className="underline" href={`/buchhaltung/${data.ledger_id}#open-item-${s.open_item_id}`}>
                  {t("openItemLink")}
                </a>
              ) : null}
              {s.contract_id ? (
                <a className="underline" href={`/vertraege/${s.contract_id}`}>
                  {t("contractLink")}
                </a>
              ) : null}
            </span>
          ))}
        </span>
      ) : null}
      {splits && splits.length > 0 ? (
        <button
          type="button"
          className={ui.button}
          onClick={() => book(splits)}
          disabled={busy || data?.object_period_lock?.locked === true}
        >
          {t("book")}
        </button>
      ) : null}
    </li>
  );
  const entries = data
    ? [
        ...data.stage1.map((p, i) => row(p, `s1-${i}`, p.splits)),
        ...data.ai.map((p) =>
          row({ ...p, source: "ai" }, `ai-${p.id}`, p.proposed?.splits),
        ),
      ]
    : [];
  return (
    <div className="flex flex-col gap-1">
      <div className="flex gap-2">
        <button
          type="button"
          className={ui.button}
          onClick={load}
          disabled={busy}
        >
          {t("proposals")}
        </button>
        <button
          type="button"
          className={ui.button}
          onClick={ignore}
          disabled={busy}
        >
          {t("ignore")}
        </button>
      </div>
      {error ? (
        <span role="alert" className={ui.error}>
          {error}
        </span>
      ) : null}
      {data?.object_period_lock?.locked ? (
        <span role="alert" className={ui.error} data-testid="period-lock-hint">
          {t("periodLocked", { code: data.object_period_lock.code ?? "MHVP-ACC-0030" })}
        </span>
      ) : null}
      {data ? (
        <ul className="flex flex-col gap-1 text-xs">
          {entries.length === 0 ? (
            <li className="text-muted">{t("noCandidates")}</li>
          ) : (
            entries
          )}
          <li className="text-muted">
            {data.ai_stage.enabled
              ? t("aiActive")
              : t("aiBlocked", { reason: data.ai_stage.blocked_reason ?? "" })}
          </li>
          <li className="text-muted">{t("proposalNote")}</li>
        </ul>
      ) : null}
    </div>
  );
}
