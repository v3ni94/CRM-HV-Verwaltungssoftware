/**
 * Preview arithmetic for the invoice entry (GAM-105, GAM-106, GAL-304). All amounts run through
 * integer cents from `money.ts`, never through a binary float. The API stays the source of truth
 * (7.9.1, `invoices.expense_amount`); these helpers only show the operator what the API checks.
 */
import { centsToDecimal, parseCents } from "@/lib/money";

export type EntryLine = { account_id: string; net: string; vat_percent: string; text: string };

/** VAT of one net amount (cents) at a percentage with up to two decimals, rounded half up. */
export function vatCents(netCents: bigint, percent: string): bigint | null {
  const pct = parseCents(percent);
  if (pct === null || pct < 0n) return null;
  const product = netCents * pct; // cents of percent, scale 10_000
  const negative = product < 0n;
  const abs = negative ? -product : product;
  const rounded = (abs + 5_000n) / 10_000n;
  return negative ? -rounded : rounded;
}

export type LineTotals = { net: bigint; vat: bigint; gross: bigint };

/** Sums net, VAT and gross over all lines; null when one line has no valid amount or percentage. */
export function lineTotals(lines: EntryLine[]): LineTotals | null {
  let net = 0n;
  let vat = 0n;
  for (const line of lines) {
    const n = parseCents(line.net);
    const v = n === null ? null : vatCents(n, line.vat_percent);
    if (n === null || v === null) return null;
    net += n;
    vat += v;
  }
  return { net, vat, gross: net + vat };
}

export type SumCheck = { ok: boolean; difference: string; totals: LineTotals | null };

/** D22: the split lines must add up to the gross amount stated on the document. */
export function checkSplitSum(lines: EntryLine[], documentGross: string): SumCheck {
  const totals = lineTotals(lines);
  const gross = parseCents(documentGross);
  if (totals === null || gross === null) return { ok: false, difference: "", totals };
  const diff = totals.gross - gross;
  return { ok: diff === 0n, difference: centsToDecimal(diff), totals };
}

export type Deduction = { invoice_id: string; gross: string };

export type FinalSummary = { service: string; deducted: string; remaining: string; ok: boolean };

/** D12: final invoice 5.950,00 minus deducted partial invoices 2.380,00 gives 3.570,00 payable. */
export function finalSummary(finalGross: string, deductions: Deduction[]): FinalSummary | null {
  const gross = parseCents(finalGross);
  if (gross === null) return null;
  let deducted = 0n;
  for (const d of deductions) {
    const c = parseCents(d.gross);
    if (c === null) return null;
    deducted += c;
  }
  const remaining = gross - deducted;
  return {
    service: centsToDecimal(gross),
    deducted: centsToDecimal(deducted),
    remaining: centsToDecimal(remaining),
    ok: remaining >= 0n,
  };
}

/** Words that mark an instruction inside a document or an extraction warning (D57). */
const INSTRUCTION_PATTERNS: RegExp[] = [
  /neue\s+iban|iban\s*(ge[aä]ndert|[aä]nderung|wechsel)|bankverbindung\s*(ge[aä]ndert|[aä]nderung)/i,
  /selbst\s*freigabe|selbst\s*freigeben|ohne\s+(zweite\s+)?freigabe|sofort\s+(zahlen|[uü]berweisen|freigeben)/i,
  /\b(exportier|export\s+(aller|der)|daten\s+(senden|weiterleiten))/i,
  /ignor(e|ier)\w*\s+(previous|vorherige|alle|bisherige)|ignore\s+all|system\s*prompt|anweisung/i,
];

/** True when a text line looks like an instruction to the processor rather than invoice content. */
export function looksLikeInstruction(text: string): boolean {
  return INSTRUCTION_PATTERNS.some((p) => p.test(text));
}

export function instructionLines(texts: string[]): string[] {
  return texts.filter((t) => looksLikeInstruction(t));
}

/** Standard rate (19, 7, 0) that explains the stated VAT of a net amount to the cent, else null. */
export function impliedVatPercent(net: string, vat: string): "19" | "7" | "0" | null {
  const n = parseCents(net);
  const v = parseCents(vat);
  if (n === null || v === null) return null;
  for (const p of ["19", "7", "0"] as const) {
    if (vatCents(n, p) === v) return p;
  }
  return null;
}
