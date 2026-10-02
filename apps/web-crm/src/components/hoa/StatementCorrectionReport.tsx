import { useTranslations } from "next-intl";

import { formatEur } from "@/lib/format";

type Triple = { old: string; new: string; difference: string };
export type CorrectionReport = {
  old: { version: number };
  new: { version: number };
  owners?: { owner: string; units: string[]; cost_share: Triple; advances_resolved: Triple; result: Triple }[];
  heating?: { cash_outflows: Record<string, string> | string } & Record<string, unknown>;
  correction?: { reason: string | null; basis: string | null; legal_note: string };
};

const HEATING_KEYS = ["cash_outflows", "cost_booked", "cost_distributed", "heating_accrual", "unexplained"] as const;

/** GAF-16: Korrekturbericht je Eigentümer mit Heizkostenüberleitung (P02, D09). Nur Anzeige. */
export function StatementCorrectionReport({ report }: { report: CorrectionReport }) {
  const t = useTranslations("HoaAF09.correction");
  const heating = report.heating as unknown as { old: Record<string, string>; new: Record<string, string>; difference: Record<string, string> } | undefined;
  return (
    <section className="flex flex-col gap-2" data-testid="correction-report">
      <h2 className="text-base font-semibold">
        {t("title")} V{report.old.version} / V{report.new.version}
      </h2>
      <p className="text-sm text-muted">{t("hint")}</p>
      {report.correction ? (
        <p className="text-sm">
          {t("reason")}: {report.correction.reason ?? ""} · {t("basis")}: {report.correction.basis ?? ""}
          <span className="block text-xs text-subtle">{report.correction.legal_note}</span>
        </p>
      ) : null}
      {report.owners && report.owners.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("owner")}</th>
                <th>{t("units")}</th>
                <th className="num">{t("costShare")} {t("difference")}</th>
                <th className="num">{t("advances")} {t("difference")}</th>
                <th className="num">{t("result")} {t("old")}</th>
                <th className="num">{t("result")} {t("new")}</th>
                <th className="num">{t("result")} {t("difference")}</th>
              </tr>
            </thead>
            <tbody>
              {report.owners.map((o) => (
                <tr key={o.owner}>
                  <td>{o.owner}</td>
                  <td>{o.units.join(", ")}</td>
                  <td className="num">{formatEur(o.cost_share.difference)}</td>
                  <td className="num">{formatEur(o.advances_resolved.difference)}</td>
                  <td className="num">{formatEur(o.result.old)}</td>
                  <td className="num">{formatEur(o.result.new)}</td>
                  <td className="num font-medium">{formatEur(o.result.difference)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-muted">{t("noOwners")}</p>
      )}
      {heating ? (
        <div className="overflow-x-auto">
          <h3 className="text-sm font-medium">{t("heating")}</h3>
          <table className="mhvp-table">
            <thead>
              <tr>
                <th />
                <th className="num">{t("old")}</th>
                <th className="num">{t("new")}</th>
                <th className="num">{t("difference")}</th>
              </tr>
            </thead>
            <tbody>
              {HEATING_KEYS.map((k) => (
                <tr key={k}>
                  <td>{t(k)}</td>
                  <td className="num">{formatEur(heating.old?.[k] ?? "0")}</td>
                  <td className="num">{formatEur(heating.new?.[k] ?? "0")}</td>
                  <td className="num">{formatEur(heating.difference?.[k] ?? "0")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
