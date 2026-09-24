"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

export type DuplicateCandidate = components["schemas"]["DuplicateCandidate"];

export function DuplicateWarning({
  candidates,
  onSaveAnyway,
  onCancel,
  busy = false,
}: {
  candidates: DuplicateCandidate[];
  onSaveAnyway: () => void;
  onCancel: () => void;
  busy?: boolean;
}) {
  const t = useTranslations("Duplicates");
  const tf = useTranslations("ContactForm");
  return (
    <section role="alert" aria-labelledby="dup-title" className="rounded border border-border bg-surface p-4">
      <h2 id="dup-title" className="text-base font-semibold">
        {t("title")}
      </h2>
      <p className="mb-3 text-sm text-muted">{t("hint")}</p>
      <div className="overflow-x-auto">
<table className="w-full text-sm">
        <thead className="text-left text-xs text-muted">
          <tr>
            <th className="py-1 pr-2 font-medium">{tf("lastName")}</th>
            <th className="py-1 pr-2 font-medium">{t("score")}</th>
            <th className="py-1 pr-2 font-medium">{t("reasons")}</th>
            <th className="py-1" />
          </tr>
        </thead>
        <tbody>
          {candidates.map((c) => (
            <tr key={c.contact.id} className="border-t border-border">
              <td className="py-1 pr-2">
                {c.contact.display_name}
                {c.contact.city ? <span className="text-muted">, {c.contact.city}</span> : null}
              </td>
              <td className="py-1 pr-2 tabular-nums">{Math.round(c.score * 100)} %</td>
              <td className="py-1 pr-2">{c.reasons.join(", ")}</td>
              <td className="py-1 text-right">
                <a
                  href={`/kontakte/${c.contact.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline"
                >
                  {t("open")}
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
</div>
      <div className="mt-3 flex gap-2">
        <button type="button" className={ui.primary} onClick={onSaveAnyway} disabled={busy}>
          {tf("saveAnyway")}
        </button>
        <button type="button" className={ui.button} onClick={onCancel} disabled={busy}>
          {tf("cancel")}
        </button>
      </div>
    </section>
  );
}
