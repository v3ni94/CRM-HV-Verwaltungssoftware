import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { DunningApproveButton } from "@/components/accounting/DunningApproveButton";
import { DunningCaseActions } from "@/components/accounting/DunningCaseActions";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusChip } from "@/components/ui/StatusChip";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Case = {
  id: string;
  contract_id: string | null;
  level: number;
  total: string;
  fee_amount: string;
  status: string;
  reason: string | null;
  // Warnungen aus der Vorschau (M23-07: Zustellung nur an den Bevollmächtigten).
  warnings?: string[];
  letter_document_id?: string | null;
  // Höchste Stufe der Leiter, die für das Objekt dieses Falls gilt (Objektüberschreibung
  // oder Mandantenvorgabe, M16-10, docs/rules/M16-02.md).
  highest_level?: number | null;
  // Fälligkeit und Verzug getrennt (M16-03); Konto des Forderungsinhabers im Schreiben (M16-13).
  due_date?: string | null;
  default_start?: string | null;
  default_mode_label?: string | null;
  bank_account?: { id: string; holder: string; iban_masked: string } | null;
  bank_warning?: string | null;
  // Objekt des Falls, aus dem Ledger abgeleitet (M16-15): fehlt bei Konten ohne Objektbezug.
  property_id?: string | null;
  property_number?: string | null;
};

export default async function DunningRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const t = await getTranslations("Dunning");
  const api = serverApi();
  const { data, error, response } = await api.GET("/api/v1/accounting/dunning-runs/{run_id}", {
    params: { path: { run_id: runId } },
  });
  redirectIfUnauthenticated(response);
  if (!data) {
    return (
      <p role="alert" className={ui.alert}>
        {problemMessage(error as Problem | undefined, response.status)}
      </p>
    );
  }
  const cases = (data.cases ?? []) as Case[];
  const proposed = cases.filter((c) => c.status === "proposed").length;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[{ href: "/buchhaltung/mahnwesen", label: t("title") }]}
        title={`${t("run", { date: formatDate(String(data.run_date)) })} · ${t(`runStatus.${String(data.status)}`)}`}
      />
      <p className={ui.notice}>{t("feesLocked")}</p>
      <p className={ui.notice}>{t("letterNotice")}</p>
      <p className={ui.notice}>{t("paymentAccountHint")}</p>
      {data.status === "preview" && proposed > 0 ? (
        <div className="flex flex-col gap-1">
          <DunningApproveButton runId={runId} />
          <p className={ui.help}>{t("approveHint", { count: proposed })}</p>
        </div>
      ) : null}
      {data.status === "preview" && proposed === 0 ? <p className={ui.help}>{t("nothingToApprove")}</p> : null}
      {cases.length === 0 ? <p className={ui.help}>{t("noCases")}</p> : null}
      <div className="overflow-x-auto">
<table className="mhvp-table mhvp-table--sticky-col">
        <thead>
          <tr>
            <th>{t("level")}</th>
            <th className="num">{t("total")}</th>
            <th className="num">{t("fee")}</th>
            <th>{t("dueDate")}</th>
            <th>{t("defaultStart")}</th>
            <th>{t("paymentAccount")}</th>
            <th>{t("status")}</th>
            <th>{t("reason")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {cases.map((c, i) => (
            <tr key={`${c.contract_id ?? "x"}-${i}`} className="align-top">
              <td>
                {c.level}
                {c.level === 1 ? <span className="block text-xs text-muted">{t("reminderLevel")}</span> : null}
              </td>
              <td className="num">{formatEur(c.total)}</td>
              <td className="num">
                {c.level === 1 ? <span className="text-muted">{t("noFee")}</span> : formatEur(c.fee_amount)}
              </td>
              <td>{c.due_date ? formatDate(c.due_date) : ""}</td>
              <td>
                {c.default_start ? formatDate(c.default_start) : <span className="text-muted">{t("defaultStartOpen")}</span>}
                {c.default_mode_label ? <span className="block text-xs text-muted">{c.default_mode_label}</span> : null}
              </td>
              <td>
                {c.bank_account ? (
                  <>
                    {c.bank_account.holder}
                    <span className="block text-xs text-muted">{c.bank_account.iban_masked}</span>
                  </>
                ) : c.status === "excluded" ? (
                  ""
                ) : (
                  <>
                    <StatusChip
                      descriptor={{ label: t("paymentAccountMissing"), tone: "warning", icon: "warning" }}
                      explanation={c.bank_warning ?? undefined}
                    />
                    {c.property_id ? (
                      <Link href={`/objekte/${c.property_id}#bankkonten`} className="mt-1 block text-xs underline">
                        {t("setDefaultAccountLink")}
                      </Link>
                    ) : null}
                  </>
                )}
                {c.bank_account && c.property_id ? (
                  <span className="block text-xs text-muted">
                    {t("objectLabel")}{" "}
                    <Link href={`/objekte/${c.property_id}`} className="underline">
                      {c.property_number ?? c.property_id}
                    </Link>
                  </span>
                ) : null}
              </td>
              <td>
                <StatusChip domain="dunningCase" status={c.status} label={t(`caseStatus.${c.status}`)} />
              </td>
              <td className="text-muted">
                {c.reason}
                {c.warnings && c.warnings.length > 0 ? (
                  <span className="mt-1 block">
                    <StatusChip
                      descriptor={{ label: t("representativeOnly"), tone: "warning", icon: "warning" }}
                      explanation={c.warnings[0]}
                    />
                  </span>
                ) : null}
              </td>
              <td>
                {c.status !== "excluded" ? (
                  <DunningCaseActions
                    caseId={c.id}
                    status={c.status}
                    isHighestLevel={c.highest_level != null && c.level >= c.highest_level}
                    hasLetter={Boolean(c.letter_document_id)}
                  />
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
</div>
    </div>
  );
}
