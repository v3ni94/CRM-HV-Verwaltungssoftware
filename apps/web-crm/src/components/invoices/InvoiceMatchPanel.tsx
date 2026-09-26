"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { BankAccountSelect } from "@/components/banking/BankAccountSelect";
import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Match = { id: string; bank_transaction_id: string; match_basis: string; amount: string };
type MatchResult = {
  invoice_id: string;
  matches: Match[];
  proposal: { id: string; status: string } | null;
  proposal_note: string | null;
};

/** Bank reconciliation for one incoming invoice (M11-finapi Stage 3): shows a matched bank
 *  transaction when one exists, or lets a person prepare a payment PROPOSAL when none does.
 *  The proposal is always a draft `PaymentOrder`: gate G2 stays closed, nothing here submits
 *  or initiates a payment. */
export function InvoiceMatchPanel({ invoiceId }: { invoiceId: string }) {
  const t = useTranslations("InvoiceMatch");
  const [matches, setMatches] = useState<Match[] | null>(null);
  const [proposalNote, setProposalNote] = useState<string | null>(null);
  const [bankAccountId, setBankAccountId] = useState("");
  const [executionDate, setExecutionDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  async function load() {
    const result = await bff<Match[]>(`/api/bff/banking/invoice-matching/${invoiceId}`);
    if (result.ok) {
      setMatches(result.data);
      setLoadError(null);
    } else {
      setMatches([]);
      setLoadError(result.message);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [invoiceId]);

  async function match(withProposal: boolean) {
    setBusy(true);
    setError(null);
    setProposalNote(null);
    const body = withProposal ? { bank_account_id: bankAccountId, execution_date: executionDate } : undefined;
    const result = await bff<MatchResult>(`/api/bff/banking/invoice-matching/${invoiceId}/match`, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message || t("error"));
      return;
    }
    setMatches(result.data.matches);
    setProposalNote(result.data.proposal_note);
  }

  if (matches === null) {
    return (
      <section className={ui.card} data-testid="invoice-match-panel">
        <h2 className={ui.h2}>{t("title")}</h2>
        <p role="status" className="mt-2 text-sm text-muted">
          {t("loading")}
        </p>
      </section>
    );
  }

  return (
    <section className={ui.card} data-testid="invoice-match-panel">
      <h2 className={ui.h2}>{t("title")}</h2>
      {loadError ? (
        <p role="alert" className={ui.alert}>
          {loadError}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {matches.length > 0 ? (
        <ul className="mt-2 text-sm">
          {matches.map((m) => (
            <li key={m.id}>
              {t("matched")}: {formatEur(m.amount)} · {m.match_basis}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-muted">{t("noMatch")}</p>
      )}
      {proposalNote ? <p className={ui.notice}>{proposalNote}</p> : null}
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => match(false)}>
          {t("match")}
        </button>
        {matches.length === 0 ? (
          <>
            <div className="min-w-64">
              <BankAccountSelect
                id="invoice-match-bank-account"
                label={t("bankAccount")}
                value={bankAccountId || null}
                onChange={(a) => setBankAccountId(a?.id ?? "")}
                showBalance={false}
              />
            </div>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("executionDate")}</span>
              <input
                type="date"
                className={ui.input}
                value={executionDate}
                onChange={(e) => setExecutionDate(e.target.value)}
              />
            </label>
            <button
              type="button"
              className={ui.primary}
              disabled={busy || !bankAccountId.trim() || !executionDate}
              onClick={() => match(true)}
            >
              {t("proposePayment")}
            </button>
          </>
        ) : null}
      </div>
      {matches.length === 0 ? <p className={`${ui.help} mt-2`}>{t("proposeHint")}</p> : null}
    </section>
  );
}
