"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type VersionPayment = { payment_type_code: string; gross: string; valid_from: string; valid_to: string | null; reason: string };
export type ContractVersionRow = { id: string; version: number; start_date: string; end_date: string | null; termination_reason?: string | null; payments?: VersionPayment[] };
export type PaymentDiff = { added: VersionPayment[]; removed: VersionPayment[] };

const key = (p: VersionPayment) => `${p.payment_type_code}|${p.valid_from}|${p.gross}`;

/** Difference of the payment lines of a version against its predecessor (GAK-207): lines with
 *  a new type, start or amount are added, lines missing in the newer version are removed. */
export function diffPayments(previous: VersionPayment[], current: VersionPayment[]): PaymentDiff {
  const before = new Set(previous.map(key));
  const after = new Set(current.map(key));
  return { added: current.filter((p) => !before.has(key(p))), removed: previous.filter((p) => !after.has(key(p))) };
}

/** Versionsverlauf eines Vertrags (GAK-207): alle Versionen mit Gültigkeit, Link auf frühere
 *  Versionen und Differenz der Zahlungszeilen gegenüber der Vorversion. Nur Anzeige. */
export function ContractVersionHistory({ contractId }: { contractId: string }) {
  const t = useTranslations("ContractVersionHistory");
  const [rows, setRows] = useState<ContractVersionRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void bff<ContractVersionRow[]>(`/api/bff/contracts/${contractId}/versions`).then((res) => {
      if (!alive) return;
      if (res.ok) setRows([...res.data].sort((a, b) => a.version - b.version));
      else setError(res.message);
    });
    return () => {
      alive = false;
    };
  }, [contractId]);

  const line = (p: VersionPayment) => `${p.payment_type_code} ${formatEur(p.gross)} ${t("from")} ${formatDate(p.valid_from)}`;

  return (
    <section className={ui.card} aria-labelledby={`contract-versions-${contractId}`}>
      <h2 id={`contract-versions-${contractId}`} className={ui.h2}>
        {t("title")}
      </h2>
      <p className={ui.help}>{t("notice")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {rows === null && !error ? <p className={ui.help}>{t("loading")}</p> : null}
      {rows !== null && rows.length === 0 ? <p className={ui.help}>{t("empty")}</p> : null}
      {rows !== null && rows.length > 0 ? (
        <ol className="mt-2 grid gap-3 text-sm">
          {rows.map((row, index) => {
            const diff = index > 0 ? diffPayments(rows[index - 1]!.payments ?? [], row.payments ?? []) : null;
            const current = row.id === contractId;
            return (
              <li key={row.id} data-testid={`contract-version-${row.version}`}>
                <div className="flex flex-wrap items-center gap-2">
                  {current ? (
                    <span className="font-semibold">{t("version", { n: row.version })}</span>
                  ) : (
                    <Link href={`/vertraege/${row.id}`} className="font-semibold hover:underline">
                      {t("version", { n: row.version })}
                    </Link>
                  )}
                  {current ? <span className={ui.badgeInfo}>{t("current")}</span> : null}
                  <span>
                    {t("validity", { from: formatDate(row.start_date), to: row.end_date ? formatDate(row.end_date) : t("openEnd") })}
                  </span>
                </div>
                {diff ? (
                  diff.added.length === 0 && diff.removed.length === 0 ? (
                    <p className={ui.help}>{t("noPaymentChange")}</p>
                  ) : (
                    <ul className="ml-4 list-disc">
                      {diff.added.map((p) => (
                        <li key={`a-${key(p)}`}>
                          {t("added")}: {line(p)}
                        </li>
                      ))}
                      {diff.removed.map((p) => (
                        <li key={`r-${key(p)}`}>
                          {t("removed")}: {line(p)}
                        </li>
                      ))}
                    </ul>
                  )
                ) : null}
              </li>
            );
          })}
        </ol>
      ) : null}
    </section>
  );
}
