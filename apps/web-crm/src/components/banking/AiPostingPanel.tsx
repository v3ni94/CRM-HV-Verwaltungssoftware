"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { formatDateTime, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type AiPostingSplit = { account_number: string; amount: string; cost_object: string | null; open_item_id?: string | null };

export type AiPostingProposal = {
  id: string;
  decision: string;
  created_at: string;
  proposed: {
    account_number: string | null;
    splits: AiPostingSplit[];
    reasoning: string;
    confidence: number;
    warnings: string[];
    prompt_version?: string;
  } | null;
  run?: { provider: string | null; model: string | null; prompt_version: string; status: string; cost_eur: string; tokens_in: number; tokens_out: number };
};

type AiPostingResponse = { bank_transaction_id: string; proposals: AiPostingProposal[]; note: string };

/** KI-Kontierung am Umsatz (M12-04, 7.4 Nr. 3): Anzeige der KI-Vorschläge mit Modell, Quelle,
 *  Kosten, Kandidaten, Begründung und Konfidenz sowie der Auslöser. Nur Vorschlag: nichts wird
 *  gebucht; ohne Mandantenschalter und freigegebenen Anbieter lehnt die API mit Grund ab. */
export function AiPostingPanel({ txId, canRequest }: { txId: string; canRequest: boolean }) {
  const t = useTranslations("Bank.aiPosting");
  const [data, setData] = useState<AiPostingResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    bff<AiPostingResponse>(`/api/bff/banking/transactions/${txId}/ai-posting`).then((r) => {
      if (cancelled) return;
      if (r.ok) setData(r.data);
    });
    return () => {
      cancelled = true;
    };
  }, [txId]);

  async function request() {
    setBusy(true);
    setError(null);
    const r = await bff<AiPostingResponse>(`/api/bff/banking/transactions/${txId}/ai-posting`, { method: "POST" });
    setBusy(false);
    if (r.ok) setData(r.data);
    else setError(r.message || t("error"));
  }

  return (
    <section className="mt-4 flex flex-col gap-2" data-testid="ai-posting-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className={ui.h3}>{t("title")}</h3>
        {canRequest ? (
          <button type="button" className={ui.secondary} onClick={request} disabled={busy}>
            {t("request")}
          </button>
        ) : null}
      </div>
      <p className="text-xs text-muted">{t("hint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {data && data.proposals.length === 0 ? <p className="text-xs text-muted">{t("none")}</p> : null}
      <ul className="flex flex-col gap-2">
        {(data?.proposals ?? []).map((p) => (
          <li key={p.id} className="rounded-lg border border-border p-2 text-sm" data-testid="ai-posting-proposal">
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
              <span>{t("source")}</span>
              <span>
                {t("model")}: {p.run?.model ?? t("unknown")}
                {p.run?.provider ? ` (${p.run.provider})` : ""}
              </span>
              <span>
                {t("cost")}: {p.run ? formatEur(p.run.cost_eur) : t("unknown")}
              </span>
              <span>{formatDateTime(p.created_at)}</span>
              <span>{t(`decision.${p.decision === "pending" || p.decision === "applied" || p.decision === "rejected" ? p.decision : "other"}`)}</span>
            </div>
            {p.proposed ? (
              <>
                <p className="mt-1">
                  {t("account")}: {p.proposed.account_number ?? t("unknown")} · {t("confidence")}:{" "}
                  {new Intl.NumberFormat("de-DE", { style: "percent", maximumFractionDigits: 0 }).format(p.proposed.confidence)}
                </p>
                {p.proposed.splits.length > 0 ? (
                  <ul className="mt-1 text-xs">
                    {p.proposed.splits.map((s, i) => (
                      <li key={i}>
                        {s.account_number}: {formatEur(s.amount)}
                        {s.cost_object ? ` · ${s.cost_object}` : ""}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {p.proposed.reasoning ? (
                  <p className="mt-1 text-xs">
                    {t("reasoning")}: {p.proposed.reasoning}
                  </p>
                ) : null}
                {p.proposed.warnings.map((w, i) => (
                  <p key={i} className="mt-1 text-xs text-warning-fg">
                    {w}
                  </p>
                ))}
              </>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

type PostingEnabled = { enabled: boolean; blocked_reason: string | null };

/** Mandantenschalter KI-Kontierung (ai_posting_enabled, M12-01), Standard aus. Auch
 *  eingeschaltet braucht jeder Lauf einen freigegebenen Anbieter mit AVV. */
export function AiPostingSwitch() {
  const t = useTranslations("Bank.aiPosting");
  const [state, setState] = useState<PostingEnabled | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    bff<PostingEnabled>("/api/bff/ai/posting-enabled").then((r) => {
      if (r.ok) setState(r.data);
      else setError(r.message);
    });
  }, []);

  async function change(next: boolean) {
    setBusy(true);
    setError(null);
    const r = await bff<PostingEnabled>("/api/bff/ai/posting-enabled", { method: "PUT", body: JSON.stringify({ enabled: next }) });
    setBusy(false);
    if (r.ok) setState(r.data);
    else setError(r.message);
  }

  return (
    <section className={`${ui.card} flex flex-col gap-2`} data-testid="ai-posting-switch">
      <h2 className="text-sm font-semibold">{t("switchTitle")}</h2>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={state?.enabled ?? false} disabled={busy || state === null} onChange={(e) => void change(e.target.checked)} />
        {t("switchLabel")}
      </label>
      <p className="text-xs text-muted">{t("switchHint")}</p>
      {state?.blocked_reason ? <p className="text-xs text-warning-fg">{t("blocked", { reason: state.blocked_reason })}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
