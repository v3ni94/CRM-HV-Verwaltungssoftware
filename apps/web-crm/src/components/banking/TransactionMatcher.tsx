"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Candidate = {
  open_item_id: string;
  remaining: string;
  score: number;
  reasons: string[];
};
type Candidates = { candidates: Candidate[]; unambiguous_open_item_id: string | null; note: string };

/** Match proposals (M12): shown with reasons; booking needs an explicit click and confirmation.
 *  The settled amount is the smaller of payment and remaining open amount (partial payments). */
export function TransactionMatcher({ txId, amount }: { txId: string; amount: string }) {
  const t = useTranslations("Bank");
  const router = useRouter();
  const [data, setData] = useState<Candidates | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<Candidates>(`/api/bff/banking/transactions/${txId}/candidates`);
    setBusy(false);
    if (res.ok) setData(res.data);
    else setError(res.message);
  };
  const book = async (c: Candidate) => {
    const cents = Math.min(Math.round(Number(amount) * 100), Math.round(Number(c.remaining) * 100));
    const settle = (cents / 100).toFixed(2);
    if (!window.confirm(t("confirmBook", { amount: formatEur(settle) }))) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/banking/transactions/${txId}/book`, {
      method: "POST",
      body: JSON.stringify({ settlements: [{ open_item_id: c.open_item_id, amount: settle }] }),
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
  return (
    <div className="flex flex-col gap-1">
      <div className="flex gap-2">
        <button type="button" className={ui.button} onClick={load} disabled={busy}>
          {t("proposals")}
        </button>
        <button type="button" className={ui.button} onClick={ignore} disabled={busy}>
          {t("ignore")}
        </button>
      </div>
      {error ? (
        <span role="alert" className={ui.error}>
          {error}
        </span>
      ) : null}
      {data ? (
        data.candidates.length === 0 ? (
          <span className="text-xs text-muted">{t("noCandidates")}</span>
        ) : (
          <ul className="flex flex-col gap-1 text-xs">
            {data.candidates.map((c) => (
              <li key={c.open_item_id} className="flex flex-wrap items-center gap-2">
                <span className="tabular-nums">{formatEur(c.remaining)}</span>
                <span className="text-muted">{c.reasons.join(", ")}</span>
                {c.open_item_id === data.unambiguous_open_item_id ? (
                  <span className="rounded bg-surface px-1">{t("unambiguous")}</span>
                ) : null}
                <button type="button" className={ui.button} onClick={() => book(c)} disabled={busy}>
                  {t("book")}
                </button>
              </li>
            ))}
            <li className="text-muted">{data.note}</li>
          </ul>
        )
      ) : null}
    </div>
  );
}
