"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type ElementType = {
  type: string;
  kind: "input" | "display";
  value_format: string;
  rule: string;
  needs_options: boolean;
  required_allowed: boolean;
  source_status: string;
};

/** Typen und Prüfregeln des Formularbaukastens (AA14-01): die verbindliche Liste der 20
 *  Elementtypen aus dem Backend, erst beim Aufklappen geladen. Der Abgleich mit der
 *  Typenliste des Altportals ist offen und steht als Quellenstatus dabei. */
export function PortalFormElementTypes() {
  const t = useTranslations("PortalFormTypes");
  const tCommon = useTranslations("Common");
  const labels = useTranslations("PortalForms");
  const [rows, setRows] = useState<ElementType[] | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (rows !== null) return;
    setError(null);
    const res = await bff<ElementType[]>("/api/bff/portal-admin/forms/element-types");
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }

  return (
    <section className="flex flex-col gap-2" aria-label={t("title")}>
      <div>
        <button type="button" className={ui.buttonSm} aria-expanded={open} onClick={toggle}>
          {open ? t("hide") : t("show")}
        </button>
      </div>
      {open && error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {open && rows ? (
        <div className={`${ui.card} flex flex-col gap-2`} data-testid="portal-form-types">
          <p className={ui.help}>{t("count", { count: rows.length })}</p>
          <p className={ui.notice}>{rows[0]?.source_status}</p>
          <div className={ui.tableScroll}>
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  <th scope="col" className="py-1 pr-3">
                    {t("type")}
                  </th>
                  <th scope="col" className="py-1 pr-3">
                    {t("format")}
                  </th>
                  <th scope="col" className="py-1">
                    {t("rule")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={99} className="text-muted">
                      {tCommon("emptyList")}
                    </td>
                  </tr>
                ) : null}
                {rows.map((row) => (
                  <tr key={row.type} className="align-top">
                    <th scope="row" className="py-1 pr-3 font-medium">
                      {labels(`fieldTypes.${row.type}`)}
                    </th>
                    <td className="py-1 pr-3">{row.value_format}</td>
                    <td className="py-1 text-muted">{row.rule}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}
