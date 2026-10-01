import { Fragment } from "react";
import { useTranslations } from "next-intl";

import { formatEur } from "@/lib/format";

export type DiffTriple = { old: string; new: string; difference: string };
export type StatementDiff = {
  old: { id: string; version: number };
  new: { id: string; version: number };
  total_costs: DiffTriple;
  units: { unit_number: string; in_old: boolean; in_new: boolean; cost_share: DiffTriple; advances_resolved: DiffTriple; result: DiffTriple; arrears: DiffTriple }[];
  owners?: { owner: string; units: string[]; cost_share: DiffTriple; advances_resolved: DiffTriple; result: DiffTriple }[];
  heating?: { old: Record<string, string>; new: Record<string, string>; difference: Record<string, string> };
  correction?: { reason: string | null; basis: string | null; legal_note: string };
  positions: { label: string; in_old: boolean; in_new: boolean; amount: DiffTriple; split: Record<string, DiffTriple> }[];
};

function Row({ label, triple, muted }: { label: string; triple: DiffTriple; muted?: boolean }) {
  const changed = triple.difference !== "0.00" && triple.difference !== "0";
  return (
    <tr className={muted ? "text-muted" : undefined}>
      <td>{label}</td>
      <td className="num">{formatEur(triple.old)}</td>
      <td className="num">{formatEur(triple.new)}</td>
      <td className={changed ? "num font-medium" : "num"}>{formatEur(triple.difference)}</td>
    </tr>
  );
}

/** Versionsvergleich zweier Hausgeldabrechnungen je Einheit und je Kostenposition (D14).
 * Nur Anzeige; die Werte kommen aus den berechneten Snapshots des Vergleichsendpunkts. */
export function StatementVersionDiff({ diff }: { diff: StatementDiff }) {
  const t = useTranslations("HoaWork.versionDiff");
  const head = (
    <thead>
      <tr>
        <th />
        <th className="num">{t("old", { version: diff.old.version })}</th>
        <th className="num">{t("new", { version: diff.new.version })}</th>
        <th className="num">{t("difference")}</th>
      </tr>
    </thead>
  );
  return (
    <section className="flex flex-col gap-3" data-testid="statement-version-diff">
      <h2 className="text-base font-semibold">{t("title", { old: diff.old.version, new: diff.new.version })}</h2>
      <p className="text-sm text-muted">{t("notice")}</p>
      <div className="overflow-x-auto">
        <table className="mhvp-table">
          {head}
          <tbody>
            <Row label={t("totalCosts")} triple={diff.total_costs} />
            {diff.positions.map((p) => (
              <Row key={p.label} label={`${t("position")}: ${p.label}${p.in_old && p.in_new ? "" : ` (${t(p.in_new ? "onlyNew" : "onlyOld")})`}`} triple={p.amount} />
            ))}
          </tbody>
        </table>
      </div>
      <h3 className="text-sm font-medium">{t("perUnit")}</h3>
      <div className="overflow-x-auto">
        <table className="mhvp-table">
          {head}
          <tbody>
            {diff.units.map((u) => (
              <>
                <Row key={`${u.unit_number}-cost`} label={`${t("unit")} ${u.unit_number}: ${t("costShare")}`} triple={u.cost_share} />
                <Row key={`${u.unit_number}-adv`} label={`${t("unit")} ${u.unit_number}: ${t("advancesResolved")}`} triple={u.advances_resolved} muted />
                <Row key={`${u.unit_number}-result`} label={`${t("unit")} ${u.unit_number}: ${t("result")}`} triple={u.result} />
              </>
            ))}
          </tbody>
        </table>
      </div>
      {diff.owners && diff.owners.length > 0 ? (
        <div className="flex flex-col gap-2" data-testid="correction-owners">
          <h3 className="text-sm font-medium">{t("perOwner")}</h3>
          <div className="overflow-x-auto">
            <table className="mhvp-table">
              {head}
              <tbody>
                {diff.owners.map((o) => (
                  <Fragment key={o.owner}>
                    <Row label={`${o.units.join(", ")}: ${t("costShare")}`} triple={o.cost_share} />
                    <Row label={`${o.units.join(", ")}: ${t("result")}`} triple={o.result} />
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      {diff.heating ? (
        <div className="flex flex-col gap-2" data-testid="correction-heating">
          <h3 className="text-sm font-medium">{t("heating")}</h3>
          <div className="overflow-x-auto">
          <table className="mhvp-table">
            {head}
            <tbody>
              {(["cash_outflows", "cost_distributed", "heating_accrual", "unexplained"] as const).map((k) => (
                <Row
                  key={k}
                  label={t(`heatingRows.${k}`)}
                  triple={{ old: diff.heating!.old[k] ?? "0.00", new: diff.heating!.new[k] ?? "0.00", difference: diff.heating!.difference[k] ?? "0.00" }}
                />
              ))}
            </tbody>
          </table>
          </div>
        </div>
      ) : null}
      {diff.correction ? <p className="text-sm text-muted">{diff.correction.legal_note}</p> : null}
    </section>
  );
}
