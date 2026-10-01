"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { partyName, type PropertyParty } from "@/lib/ai";
import { bff } from "@/lib/bff";
import { formatConfidence } from "@/lib/format";
import { ui } from "@/lib/ui";

type Candidate = { contact_id: string; name: string; score: number; reasons: string[] };
type MatchResult = { decision: "link" | "suggest" | "none"; candidates: Candidate[] };
type BatchResult = { results: MatchResult[]; link_threshold: string; suggest_threshold: string };

const KEYS = ["first_name", "last_name", "company_name", "email", "iban", "postal_code", "street"] as const;

function personOf(party: PropertyParty): Record<string, string> {
  const source = party as unknown as Record<string, unknown>;
  const out: Record<string, string> = {};
  for (const key of KEYS) {
    const value = source[key];
    if (typeof value === "string" && value.trim()) out[key] = value.trim();
  }
  return out;
}

/** Preview of the person match (10.2 step 4) as a table: per owner or tenant of the proposal the
 *  decision the apply step will take with the thresholds of the tenant. Writes nothing. */
export function PersonMatchTable({ parties }: { parties: PropertyParty[] }) {
  const t = useTranslations("OnboardingExtras");
  const [data, setData] = useState<BatchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const usable = parties.length > 0;

  async function load() {
    setBusy(true);
    setError(null);
    const res = await bff<BatchResult>("/api/bff/onboarding/person-match-batch", {
      method: "POST",
      body: JSON.stringify({ persons: parties.slice(0, 500).map(personOf) }),
    });
    setBusy(false);
    if (res.ok) setData(res.data);
    else setError(res.message);
  }

  if (!usable) return null;
  return (
    <section className="flex flex-col gap-2" aria-labelledby="match-title" data-testid="person-match">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 id="match-title" className="text-sm font-medium">
          {t("matchTitle")}
        </h4>
        <button type="button" className={ui.button} onClick={load} disabled={busy} data-testid="person-match-load">
          {data ? t("matchReload") : t("matchLoad")}
        </button>
      </div>
      <p className={ui.help}>{t("matchHint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {data ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm" data-testid="person-match-table">
            <caption className="sr-only">{t("matchTitle")}</caption>
            <thead>
              <tr className="text-xs text-muted">
                <th scope="col" className="py-1 pr-3">
                  {t("colUnit")}
                </th>
                <th scope="col" className="py-1 pr-3">
                  {t("colRole")}
                </th>
                <th scope="col" className="py-1 pr-3">
                  {t("colName")}
                </th>
                <th scope="col" className="py-1 pr-3">
                  {t("colDecision")}
                </th>
                <th scope="col" className="py-1">
                  {t("colCandidate")}
                </th>
              </tr>
            </thead>
            <tbody>
              {parties.slice(0, data.results.length).map((party, i) => {
                const result = data.results[i];
                if (!result) return null;
                const best = result.candidates[0];
                return (
                  <tr key={i} className="border-t border-border align-top" data-testid={`person-match-row-${i}`}>
                    <td className="py-1 pr-3">{party.unit_number}</td>
                    <td className="py-1 pr-3">{party.role === "owner" ? t("roleOwner") : t("roleTenant")}</td>
                    <td className="py-1 pr-3">{partyName(party) || t("noName")}</td>
                    <td className="py-1 pr-3">
                      <span className={result.decision === "link" ? ui.badgeSuccess : result.decision === "suggest" ? ui.badgeWarning : ui.badge}>
                        {t(`decision.${result.decision}`)}
                      </span>
                    </td>
                    <td className="py-1">
                      {best ? (
                        <>
                          {best.name} ({formatConfidence(best.score)})
                          <span className="block text-xs text-muted">{best.reasons.join(", ")}</span>
                        </>
                      ) : (
                        <span className="text-muted">{t("noCandidate")}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className={ui.help}>
            {t("thresholds", { link: formatConfidence(data.link_threshold), suggest: formatConfidence(data.suggest_threshold) })}
          </p>
        </div>
      ) : null}
    </section>
  );
}
