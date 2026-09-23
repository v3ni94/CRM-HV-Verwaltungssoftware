"use client";

import { useTranslations } from "next-intl";

import type { Reasoning } from "@/lib/ai";
import { formatConfidence } from "@/lib/format";

/** Every AI output is a proposal (9.4): badge, confidence and a "Warum?" disclosure. */
export function ProposalBadge({
  confidence,
  reasoning,
}: {
  confidence: string | number | null | undefined;
  reasoning?: Reasoning;
}) {
  const t = useTranslations("Ai");
  const conf = formatConfidence(confidence);
  const empty = !reasoning || (reasoning.sources.length + reasoning.notes.length + reasoning.questions.length === 0);
  return (
    <div className="flex flex-col gap-1 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded border border-border bg-bg px-1.5 py-0.5 font-medium" data-testid="proposal-badge">
          {t("proposal")}
        </span>
        <span className="text-muted">{conf ? t("confidence", { value: conf }) : t("confidenceUnknown")}</span>
      </div>
      <details>
        <summary className="cursor-pointer text-muted underline">{t("why")}</summary>
        <div className="mt-1 flex flex-col gap-1 rounded border border-border bg-bg p-2">
          <p className="text-muted">{t("whyHint")}</p>
          {empty ? <p>{t("whyEmpty")}</p> : null}
          {reasoning && reasoning.sources.length > 0 ? (
            <div>
              <p className="font-medium">{t("sources")}</p>
              <ul className="list-disc pl-4">
                {reasoning.sources.map((s, i) => (
                  <li key={`${s.document_id}-${i}`}>
                    <span className="text-muted">{t("sourceDocument", { id: s.document_id.slice(0, 8) })}</span> {s.excerpt}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {reasoning && reasoning.notes.length > 0 ? (
            <div>
              <p className="font-medium">{t("notes")}</p>
              <ul className="list-disc pl-4">
                {reasoning.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {reasoning && reasoning.questions.length > 0 ? (
            <div>
              <p className="font-medium">{t("questions")}</p>
              <ul className="list-disc pl-4">
                {reasoning.questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </details>
    </div>
  );
}
