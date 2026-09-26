import { useTranslations } from "next-intl";
import Link from "next/link";

import type { components } from "@mhvp/api-client";
import { formatDate } from "@/lib/format";

export type ObjectRelation = components["schemas"]["ObjectRelationOut"];

function period(r: ObjectRelation, since: (date: string) => string): string {
  const from = formatDate(r.valid_from);
  const to = formatDate(r.valid_to);
  if (from && to) return `${from} bis ${to}`;
  if (from) return since(from);
  return to ? `bis ${to}` : "";
}

/** Object and unit relations of a contact (tenancy, ownership, property contact). */
export function RelationsPanel({ relations }: { relations: ObjectRelation[] }) {
  const t = useTranslations("Contacts.relations");
  const tl = useTranslations("Labels");
  return (
    <section className="mt-6" aria-labelledby="contact-relations-title">
      <h2 id="contact-relations-title" className="mb-1 text-sm font-semibold">
        {t("title")}
      </h2>
      {relations.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted">
                <th className="py-1.5 pr-2 font-medium">{t("object")}</th>
                <th className="py-1.5 pr-2 font-medium">{t("unit")}</th>
                <th className="py-1.5 pr-2 font-medium">{t("role")}</th>
                <th className="py-1.5 pr-2 font-medium">{t("period")}</th>
                <th className="py-1.5 font-medium">{t("status")}</th>
              </tr>
            </thead>
            <tbody>
              {relations.map((r) => (
                <tr
                  key={`${r.source}-${r.contract_id ?? ""}-${r.property_id}-${r.unit_id ?? ""}-${r.category_code ?? ""}-${r.valid_from ?? ""}`}
                  className="border-b border-border"
                >
                  <td className="py-1.5 pr-2">
                    <Link href={`/objekte/${r.property_id}`} className="hover:underline">
                      {r.property_name}
                    </Link>
                    {r.property_city ? <span className="text-muted">, {r.property_city}</span> : null}
                  </td>
                  <td className="py-1.5 pr-2">{r.unit_label ?? ""}</td>
                  <td className="py-1.5 pr-2">
                    <span className="rounded-full bg-surface px-2 py-0.5 text-xs text-muted">
                      {r.kind === "kontakt" ? (r.category_code ?? "") : tl(`role.${r.kind}`)}
                    </span>
                  </td>
                  <td className="py-1.5 pr-2">{period(r, (date) => t("since", { date }))}</td>
                  <td className={`py-1.5 ${r.active ? "" : "text-muted"}`}>{r.active ? t("active") : t("ended")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
