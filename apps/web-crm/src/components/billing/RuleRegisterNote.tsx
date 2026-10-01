import { useTranslations } from "next-intl";

import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type RuleRegisterRef = { rule_id: string; version: number; status: string; effective_from: string };

/** GA08-05: rule register entry pinned in the run snapshot (rule, version, status, effective date). */
export function RuleRegisterNote({ rule }: { rule: RuleRegisterRef | null | undefined }) {
  const t = useTranslations("Billing");
  return (
    <p className={ui.help} data-testid="rule-register">
      <strong>{t("ruleRegisterTitle")}: </strong>
      {rule
        ? t("ruleRegisterText", {
            rule: rule.rule_id,
            version: rule.version,
            status: rule.status,
            date: formatDate(rule.effective_from),
          })
        : t("ruleRegisterNone")}
    </p>
  );
}
