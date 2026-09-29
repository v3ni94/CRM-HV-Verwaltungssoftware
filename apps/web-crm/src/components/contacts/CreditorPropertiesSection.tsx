import Link from "next/link";
import { useTranslations } from "next-intl";

import { formatDate } from "@/lib/format";

export type CreditorProperty = {
  id: string;
  property_id: string;
  property_number: string;
  property_name: string;
  trade: string | null;
  since: string | null;
  source: "proposal" | "manual" | "backfill";
};

/** Abschnitt "Objekte als Dienstleister" der Kontaktseite (Regel M11-08): Objekte, an denen
 *  der Kontakt als Kreditor verknüpft ist, mit Gewerk und Beginn. Lesend; gepflegt wird auf der
 *  Objektseite (Reiter Dienstleister/Handwerker). */
export function CreditorPropertiesSection({ rows }: { rows: CreditorProperty[] }) {
  const t = useTranslations("Contacts.creditorProperties");
  return (
    <section className="mt-6" aria-labelledby="contact-creditor-properties-title" data-testid="creditor-properties">
      <h2 id="contact-creditor-properties-title" className="mb-1 text-sm font-semibold">
        {t("title")}
      </h2>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted">
              <th className="py-1.5 pr-2 font-medium">{t("property")}</th>
              <th className="py-1.5 pr-2 font-medium">{t("trade")}</th>
              <th className="py-1.5 pr-2 font-medium">{t("since")}</th>
              <th className="py-1.5 font-medium">{t("source")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-border">
                <td className="py-1.5 pr-2">
                  <Link href={`/objekte/${r.property_id}#dienstleister`} className="hover:underline">
                    {r.property_number} {r.property_name}
                  </Link>
                </td>
                <td className="py-1.5 pr-2">{r.trade ?? ""}</td>
                <td className="py-1.5 pr-2">{r.since ? formatDate(r.since) : ""}</td>
                <td className="py-1.5">{t(`sourceLabel.${r.source}`)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
