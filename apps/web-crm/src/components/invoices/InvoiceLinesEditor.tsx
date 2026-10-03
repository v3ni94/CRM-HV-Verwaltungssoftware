"use client";

import { useTranslations } from "next-intl";

import { formatEur } from "@/lib/format";
import { centsToDecimal } from "@/lib/money";
import { checkSplitSum, type EntryLine } from "@/lib/invoice-lines";
import { ui } from "@/lib/ui";

export const EMPTY_LINE: EntryLine = { account_id: "", net: "", vat_percent: "19", text: "" };

/**
 * GAM-106 (D22): split entry for mixed invoices. Each line carries account, net amount, VAT rate
 * and the justification of the split; the sum check compares the lines with the stated gross.
 */
export function InvoiceLinesEditor({
  accounts,
  lines,
  documentGross,
  onLines,
  onDocumentGross,
}: {
  accounts: { id: string; label: string }[];
  lines: EntryLine[];
  documentGross: string;
  onLines: (l: EntryLine[]) => void;
  onDocumentGross: (v: string) => void;
}) {
  const t = useTranslations("Invoices");
  const check = checkSplitSum(lines, documentGross);
  const patch = (i: number, key: keyof EntryLine, value: string) => onLines(lines.map((l, n) => (n === i ? { ...l, [key]: value } : l)));
  return (
    <div className="flex flex-col gap-2" data-testid="split-editor">
      <p className={ui.help}>{t("split.hint")}</p>
      {lines.map((l, i) => (
        <div key={i} className="grid gap-2 sm:grid-cols-[2fr_1fr_1fr_2fr_auto]">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("split.account", { n: i + 1 })}</span>
            <select className={ui.input} value={l.account_id} onChange={(e) => patch(i, "account_id", e.target.value)}>
              <option value="">{t("choose")}</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>{a.label}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("split.net", { n: i + 1 })}</span>
            <input className={ui.input} value={l.net} onChange={(e) => patch(i, "net", e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("split.vat", { n: i + 1 })}</span>
            <select className={ui.input} value={l.vat_percent} onChange={(e) => patch(i, "vat_percent", e.target.value)}>
              {["19", "7", "0"].map((v) => (
                <option key={v} value={v}>{v} %</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("split.reason", { n: i + 1 })}</span>
            <input className={ui.input} maxLength={500} value={l.text} onChange={(e) => patch(i, "text", e.target.value)} />
          </label>
          <button type="button" className={ui.button} disabled={lines.length <= 2} onClick={() => onLines(lines.filter((_, n) => n !== i))}>
            {t("split.remove")}
          </button>
        </div>
      ))}
      <div className="flex flex-wrap items-end gap-2">
        <button type="button" className={ui.button} disabled={lines.length >= 200} onClick={() => onLines([...lines, { ...EMPTY_LINE }])}>{t("split.add")}</button>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("split.documentGross")}</span>
          <input className={ui.input} value={documentGross} onChange={(e) => onDocumentGross(e.target.value)} />
        </label>
      </div>
      {check.totals ? (
        <p className="text-sm" data-testid="split-sum">
          {t("split.sum", { net: formatEur(centsToDecimal(check.totals.net)), vat: formatEur(centsToDecimal(check.totals.vat)), gross: formatEur(centsToDecimal(check.totals.gross)) })}
        </p>
      ) : null}
      {documentGross.trim() !== "" && check.totals && !check.ok ? (
        <p role="alert" className={ui.alert} data-testid="split-mismatch">{t("split.mismatch", { difference: formatEur(check.difference) })}</p>
      ) : null}
    </div>
  );
}
