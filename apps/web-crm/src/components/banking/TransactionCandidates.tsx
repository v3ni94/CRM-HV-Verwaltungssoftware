"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Candidate = {
  open_item_id: string;
  account_id: string;
  contract_id: string | null;
  remaining: string;
  score: number;
  reasons: string[];
  allocation_reason?: string;
};
type CandidatesOut = { candidates: Candidate[]; unambiguous_open_item_id: string | null; note: string };

/** Zuordnungsvorschläge mit Begründung je Bankbewegung (GAI-405). Reine Anzeige: ein Vorschlag
 *  bucht nichts und ersetzt keine Prüfung, die IBAN allein beweist keinen Schuldner. Die Buchung
 *  erfolgt weiter im Buchungsdialog durch eine Person. */
export function TransactionCandidates({ txId }: { txId: string }) {
  const t = useTranslations("BankActions.candidates");
  const [data, setData] = useState<CandidatesOut | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const toggle = async () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (data) return;
    setBusy(true);
    setError(null);
    const res = await bff<CandidatesOut>(`/api/bff/banking/transactions/${txId}/candidates`);
    setBusy(false);
    if (res.ok) setData(res.data);
    else setError(res.message);
  };

  return (
    <div data-testid="tx-candidates">
      <button type="button" className={ui.buttonSm} onClick={() => void toggle()} aria-expanded={open}>
        {open ? t("hide") : t("show")}
      </button>
      {open ? (
        <div className="mt-1 max-w-md text-xs">
          {busy ? <p className="text-muted">{t("loading")}</p> : null}
          {error ? (
            <p role="alert" className={ui.alert}>
              {error}
            </p>
          ) : null}
          {data && data.candidates.length === 0 ? <p className="text-muted">{t("none")}</p> : null}
          {data && data.candidates.length > 0 ? (
            <ul className="flex flex-col gap-1">
              {data.candidates.map((c) => (
                <li key={c.open_item_id} className="rounded border border-border p-1">
                  <span className="font-medium">{t("remaining", { amount: formatEur(c.remaining) })}</span>
                  <span className="ml-2 text-muted">{t("score", { score: c.score })}</span>
                  {data.unambiguous_open_item_id === c.open_item_id ? <span className={`ml-2 ${ui.badgeInfo}`}>{t("unambiguous")}</span> : null}
                  {c.reasons.length > 0 ? (
                    <ul className="ml-4 list-disc text-muted">
                      {c.reasons.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
          {data ? <p className="mt-1 text-muted">{t("note")}</p> : null}
        </div>
      ) : null}
    </div>
  );
}
