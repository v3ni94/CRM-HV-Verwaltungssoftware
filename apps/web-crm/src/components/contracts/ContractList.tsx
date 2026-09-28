import { useTranslations } from "next-intl";
import Link from "next/link";

import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import type { ContractOut } from "./ContractForm";

/** Suchfeld der Vertragsliste: einfaches GET-Formular, die Suche läuft serverseitig
 *  (GET /contracts?q=). Vorhandene Filter (Objekt, Einheit) bleiben als versteckte Felder. */
export function ContractSearch({ q, hidden }: { q: string; hidden: Record<string, string> }) {
  const t = useTranslations("ContractForm");
  return (
    <form method="get" action="/vertraege" role="search" className="flex flex-wrap items-end gap-2">
      {Object.entries(hidden).map(([k, v]) => (
        <input key={k} type="hidden" name={k} value={v} />
      ))}
      <label className="flex flex-col gap-1 text-sm">
        {t("page.search")}
        <input
          type="search"
          name="q"
          defaultValue={q}
          maxLength={200}
          placeholder={t("page.searchPlaceholder")}
          className={ui.input}
        />
      </label>
      <button type="submit" className={ui.button}>
        {t("page.searchSubmit")}
      </button>
    </form>
  );
}

/** Vertragsliste mit Objekt, Einheit und Personen (Mieter oder Eigentümer), jeweils verlinkt. */
export function ContractList({ rows }: { rows: ContractOut[] }) {
  const t = useTranslations("ContractForm");
  const ta = useTranslations("ContractApproval");
  return (
    <div className="overflow-x-auto">
      <table className={ui.table}>
        <thead>
          <tr>
            <th>{t("page.number")}</th>
            <th>{t("page.kind")}</th>
            <th>{t("page.property")}</th>
            <th>{t("page.unit")}</th>
            <th>{t("page.persons")}</th>
            <th>{t("page.term")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id}>
              <td>
                {c.number} ({t("edit.version", { n: c.version })})
              </td>
              <td>
                {t(`kinds.${c.kind}`)}
                {c.approval_status === "pending" ? (
                  <>
                    {" "}
                    <span className={ui.badgeWarning}>{ta("pendingBadge")}</span>
                  </>
                ) : null}
              </td>
              <td>
                <Link href={`/objekte/${c.property_id}`} className="hover:underline">
                  {[c.property_number, c.property_name].filter(Boolean).join(" ") || t("page.toProperty")}
                </Link>
                {c.property_address ? <div className={ui.help}>{c.property_address}</div> : null}
              </td>
              <td>
                <Link href={`/vermietung/einheit/${c.unit_id}`} className="hover:underline">
                  {[c.unit_number, c.unit_label].filter(Boolean).join(" · ") || t("page.toUnit")}
                </Link>
              </td>
              <td>
                {c.members && c.members.length ? (
                  <ul>
                    {c.members.map((m) => (
                      <li key={m.contact_id}>
                        <Link href={`/kontakte/${m.contact_id}`} className="hover:underline">
                          {m.name}
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  (c.party_name ?? "")
                )}
              </td>
              <td>
                {formatDate(c.start_date)}
                {c.end_date ? ` bis ${formatDate(c.end_date)}` : ""}
              </td>
              <td>
                <Link href={`/vertraege/${c.id}`} className="hover:underline">
                  {t("page.toDetail")}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
