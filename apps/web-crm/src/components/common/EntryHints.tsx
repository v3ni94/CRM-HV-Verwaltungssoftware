"use client";
/** Inline hints of the entry standards (ES-01 to ES-10, handbook Erfassungsstandards). Warnings
 *  and hints never block saving; only findings of severity "error" are hard (ES-01). */
import Link from "next/link";
import { useTranslations } from "next-intl";

import { findingKey, type Finding } from "@/lib/entry-standards";
import { ui } from "@/lib/ui";

export function EntryHints({ findings, testId, onApplySuggestion }: { findings: Finding[]; testId?: string; onApplySuggestion?: (value: string) => void }) {
  const t = useTranslations("EntryStandards");
  if (findings.length === 0) return null;
  const errors = findings.filter((f) => f.severity === "error");
  const soft = findings.filter((f) => f.severity !== "error");
  return (
    <div className="flex flex-col gap-2" data-testid={testId ?? "entry-hints"}>
      {errors.length ? (
        <ul role="alert" className={ui.alert}>
          {errors.map((f) => (
            <li key={`${f.rule}-${f.field}`}>{t(findingKey(f), f.params ?? {})}</li>
          ))}
        </ul>
      ) : null}
      {soft.length ? (
        <div role="status" className={ui.warning}>
          <p className="font-medium">{t("softTitle")}</p>
          <ul className="list-disc pl-5">
            {soft.map((f) => (
              <li key={`${f.rule}-${f.field}`}>
                {t(findingKey(f), f.params ?? {})}
                {f.rule === "ES-04" && f.params?.suggestion && onApplySuggestion ? (
                  <button type="button" className="ml-2 underline" onClick={() => onApplySuggestion(f.params?.suggestion ?? "")}>
                    {t("applySuggestion")}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs">
            {t("softFooter")}{" "}
            <Link className="underline" href="/einstellungen/datenqualitaet">
              {t("reportLink")}
            </Link>
          </p>
        </div>
      ) : null}
    </div>
  );
}
