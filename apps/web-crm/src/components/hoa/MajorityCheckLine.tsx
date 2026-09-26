import { useTranslations } from "next-intl";

export type MajorityCheck = {
  result: "erreicht" | "nicht erreicht" | "nicht prüfbar";
  rule_text: string;
  reason?: string | null;
  standard_rule?: boolean;
};

const RESULT_KEY: Record<MajorityCheck["result"], string> = {
  erreicht: "reached",
  "nicht erreicht": "notReached",
  "nicht prüfbar": "notCheckable",
};

/** Mehrheitsprüfung (M25-01): Ergebnis mit angewandter Regel, nur Anzeige und Protokollvermerk. */
export function MajorityCheckLine({ check }: { check: MajorityCheck }) {
  const t = useTranslations("MajorityRules");
  return (
    <div className="text-xs text-muted" data-testid="majority-check">
      <span className="font-medium">
        {t("check")}: {t(`results.${RESULT_KEY[check.result] ?? "notCheckable"}`)}
      </span>
      {" · "}
      {check.rule_text}
      {check.reason ? ` · ${check.reason}` : ""}
    </div>
  );
}
