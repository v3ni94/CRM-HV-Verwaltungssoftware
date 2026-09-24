"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { contactName, contactsPreview, type ContactChoice, type ContactRow, type ImportRun, type Proposal } from "@/lib/ai";
import { bff } from "@/lib/bff";
import { formatConfidence } from "@/lib/format";
import { ui } from "@/lib/ui";

import { ImportResult } from "./ImportResult";

type Action = "create" | "link" | "skip";
type RowChoice = { action: Action; contactId: string | null };

const LIGHT: Record<ContactRow["status"], string> = {
  new: "bg-green-600",
  existing: "bg-yellow-500",
  incomplete: "bg-orange-500",
  invalid: "bg-red-600",
};

function defaultChoice(row: ContactRow): RowChoice {
  if (row.status === "invalid") return { action: "skip", contactId: null };
  if (row.status === "existing" && row.duplicates[0]) return { action: "link", contactId: row.duplicates[0].contact_id };
  return { action: "create", contactId: null };
}

/** Preview of extracted contacts (10.1 step 4): traffic light, notes and a choice per row. */
export function ContactProposal({ proposal, onDecided }: { proposal: Proposal; onDecided?: () => void }) {
  const t = useTranslations("Ai");
  const preview = contactsPreview(proposal.proposed);
  const [choices, setChoices] = useState<RowChoice[]>(() => preview.rows.map(defaultChoice));
  const [result, setResult] = useState<ImportRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [decision, setDecision] = useState(proposal.decision);

  const set = (i: number, next: Partial<RowChoice>) =>
    setChoices((prev) => prev.map((c, j) => (j === i ? { ...c, ...next } : c)));

  const apply = async () => {
    setBusy(true);
    setError(null);
    const contacts: ContactChoice[] = preview.rows.map((row, i) => {
      const c = choices[i]!;
      return c.action === "link"
        ? { index: row.index, action: "link", contact_id: c.contactId }
        : { index: row.index, action: c.action };
    });
    const res = await bff<ImportRun>(`/api/bff/ai/proposals/${proposal.id}/apply`, {
      method: "POST",
      body: JSON.stringify({ contacts }),
    });
    setBusy(false);
    if (res.ok) {
      setResult(res.data);
      setDecision("accepted");
      onDecided?.();
    } else setError(res.message);
  };

  const reject = async () => {
    setBusy(true);
    const res = await bff<Proposal>(`/api/bff/ai/proposals/${proposal.id}/reject`, { method: "POST" });
    setBusy(false);
    if (res.ok) {
      setDecision(res.data.decision);
      onDecided?.();
    } else setError(res.message);
  };

  const invalidLink = choices.some((c) => c.action === "link" && !c.contactId);
  const nothingToDo = choices.every((c) => c.action === "skip");

  if (result) return <ImportResult importRun={result} />;

  return (
    <section className="flex flex-col gap-3" aria-label={t("contactPreviewTitle")}>
      <h3 className="text-sm font-semibold">{t("contactPreviewTitle")}</h3>
      {preview.questions.length> 0 ? (
        <div className={ui.notice}>
          <p className="font-medium">{t("openQuestions")}</p>
          <ul className="list-disc pl-4">
            {preview.questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="text-xs text-muted">{t("contactLegend")}</p>
      <div className="overflow-x-auto">
        <div className="overflow-x-auto">
<table className="mhvp-table">
          <thead>
            <tr>
              <th className="font-medium">{t("colStatus")}</th>
              <th className="font-medium">{t("colName")}</th>
              <th className="font-medium">{t("colRole")}</th>
              <th className="font-medium">{t("colConfidence")}</th>
              <th className="font-medium">{t("colNotes")}</th>
              <th className="font-medium">{t("colAction")}</th>
            </tr>
          </thead>
          <tbody>
            {preview.rows.map((row, i) => {
              const choice = choices[i]!;
              const name = contactName(row.contact) || t("noName");
              return (
                <tr key={row.index} className="border-b border-border align-top" data-testid={`contact-row-${row.index}`}>
                  <td>
                    <span className="inline-flex items-center gap-1">
                      <span className={`inline-block h-3 w-3 rounded-full ${LIGHT[row.status]}`} aria-hidden />
                      <span>{t(`rowStatus.${row.status}`)}</span>
                    </span>
                  </td>
                  <td>
                    <div>{name}</div>
                    {row.source_row ? <div className="text-xs text-muted">{t("sourceRow", { row: row.source_row })}</div> : null}
                    {row.duplicates.length> 0 ? (
                      <ul className="text-xs text-muted">
                        {row.duplicates.map((d) => (
                          <li key={d.contact_id}>
                            {t("duplicate", { name: d.name, score: formatConfidence(d.score) })}
                            {d.reasons.length ? `: ${d.reasons.join(", ")}` : ""}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </td>
                  <td>
                    {row.role ? t(`role.${row.role}`) : ""}
                    {row.unit_number ? <div className="text-xs text-muted">{t("unit", { number: row.unit_number })}</div> : null}
                  </td>
                  <td>{formatConfidence(row.confidence)}</td>
                  <td>
                    {row.notes.length> 0 ? (
                      <ul className="list-disc pl-4 text-xs">
                        {row.notes.map((n, k) => (
                          <li key={k}>{n}</li>
                        ))}
                      </ul>
                    ) : null}
                  </td>
                  <td>
                    <label className="sr-only" htmlFor={`action-${row.index}`}>
                      {t("actionFor", { name })}
                    </label>
                    <select
                      id={`action-${row.index}`}
                      className={ui.input}
                      value={choice.action}
                      disabled={decision !== "pending"}
                      onChange={(e) => {
                        const action = e.target.value as Action;
                        set(i, { action, contactId: action === "link" ? (row.duplicates[0]?.contact_id ?? null) : null });
                      }}
>
                      <option value="create" disabled={row.status === "invalid"}>
                        {t("actionCreate")}
                      </option>
                      <option value="link" disabled={row.duplicates.length === 0}>
                        {t("actionLink")}
                      </option>
                      <option value="skip">{t("actionSkip")}</option>
                    </select>
                    {choice.action === "link" && row.duplicates.length> 1 ? (
                      <select
                        aria-label={t("linkTarget", { name })}
                        className={`${ui.input} mt-1`}
                        value={choice.contactId ?? ""}
                        onChange={(e) => set(i, { contactId: e.target.value })}
>
                        {row.duplicates.map((d) => (
                          <option key={d.contact_id} value={d.contact_id}>
                            {d.name}
                          </option>
                        ))}
                      </select>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
</div>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {decision === "pending" ? (
        <div className="flex flex-wrap gap-2">
          <button type="button" className={ui.primary} onClick={apply} disabled={busy || invalidLink || nothingToDo}>
            {t("confirmApply")}
          </button>
          <button type="button" className={ui.button} onClick={reject} disabled={busy}>
            {t("reject")}
          </button>
          <p className="self-center text-xs text-muted">{t("applyHint")}</p>
        </div>
      ) : (
        <p className="text-sm text-muted">{t(`decision.${decision}`)}</p>
      )}
    </section>
  );
}
