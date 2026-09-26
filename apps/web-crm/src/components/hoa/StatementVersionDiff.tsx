import { useTranslations } from "next-intl";

import { formatEur } from "@/lib/format";

export type DiffTriple = { old: string; new: string; difference: string };
export type StatementDiff = {
  old: { id: string; version: number };
  new: { id: string; version: number };
  total_costs: DiffTriple;
  units: { unit_number: string; in_old: boolean; in_new: boolean; cost_share: DiffTriple; advances_resolved: DiffTriple; result: DiffTriple; arrears: DiffTriple }[];
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
    </section>
  );
}
