"use client";

import { useTranslations } from "next-intl";

import { instructionLines } from "@/lib/invoice-lines";
import { ui } from "@/lib/ui";

/**
 * GAM-207 (D57): shows when the extraction or the findings contain text that reads like an
 * instruction (new IBAN, self release, export). The text is data: nothing is carried out.
 */
export function InstructionTextNotice({ texts }: { texts: string[] }) {
  const t = useTranslations("Invoices");
  const hits = instructionLines(texts);
  if (hits.length === 0) return null;
  return (
    <section className={ui.alert} role="alert" data-testid="instruction-notice">
      <p className="font-medium">{t("instruction.title")}</p>
      <p>{t("instruction.text")}</p>
      <ul className="list-inside list-disc">
        {hits.map((h, i) => <li key={i}>{h}</li>)}
      </ul>
    </section>
  );
}
