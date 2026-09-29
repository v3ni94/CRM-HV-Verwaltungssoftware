"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Prepared recurring invoices (Dauerrechnungen) for new management fees (INT-LEXO-01). The
 *  Lexware Office API offers recurring templates read only, so a person creates the template
 *  there with this checklist and records its id here. */
export type LexofficeRecurringPrep = {
  id: string;
  property_id: string;
  status: string;
  prepared: {
    property?: { number?: string | null; name?: string | null };
    contact?: { display_name?: string; deeplink?: string | null } | null;
    amounts_per_unit_type?: Record<string, string>;
    vat_percent?: string;
    interval_label?: string;
    start_date?: string;
    text?: string;
    api_limitation?: string;
    recurring_templates_url?: string;
  };
  checklist: { step: number; text: string; done: boolean }[];
  lexoffice_template_id: string | null;
  deeplink: string | null;
};

export function LexofficeRecurringPreps({ canManage }: { canManage: boolean }) {
  const t = useTranslations("Lexoffice");
  const [rows, setRows] = useState<LexofficeRecurringPrep[]>([]);
  const [templateIds, setTemplateIds] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<LexofficeRecurringPrep[]>("/api/bff/integrations/lexoffice/recurring-preps?status=open");
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(id: string, action: "done" | "dismiss") {
    setBusy(true);
    setError(null);
    const res = await bff<LexofficeRecurringPrep>(`/api/bff/integrations/lexoffice/recurring-preps/${id}/${action}`, {
      method: "POST",
      ...(action === "done" ? { body: JSON.stringify({ lexoffice_template_id: templateIds[id] ?? "" }) } : {}),
    });
    setBusy(false);
    if (res.ok) await load();
    else setError(res.message);
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`}>
      <h2 className={ui.h2}>{t("recurring.heading")}</h2>
      <p className={ui.help}>{t("recurring.intro")}</p>
      {rows.length === 0 ? <p className={ui.help}>{t("recurring.empty")}</p> : null}
      <ul className="flex flex-col gap-3">
        {rows.map((row) => (
          <li key={row.id} className="rounded border border-border p-3 text-sm">
            <p className="font-medium">
              {t("recurring.property")}: {row.prepared.property?.number} {row.prepared.property?.name}
            </p>
            <p>
              {t("recurring.contact")}: {row.prepared.contact?.display_name ?? t("recurring.contactMissing")}
              {row.prepared.contact?.deeplink ? (
                <>
                  {" "}
                  <a href={row.prepared.contact.deeplink} target="_blank" rel="noreferrer" className="underline">
                    {t("links.openRemote")}
                  </a>
                </>
              ) : null}
            </p>
            <p>
              {t("recurring.amounts")}:{" "}
              {Object.entries(row.prepared.amounts_per_unit_type ?? {})
                .map(([k, v]) => `${k}: ${v.replace(".", ",")} EUR`)
                .join(", ")}
            </p>
            <p>
              {t("recurring.interval")}: {row.prepared.interval_label} {"·"} {t("recurring.start")}: {formatDate(row.prepared.start_date ?? null)}
            </p>
            <p>
              {t("recurring.text")}: {row.prepared.text}
            </p>
            <p className={ui.help}>{row.prepared.api_limitation}</p>
            <p className={ui.label}>{t("recurring.checklist")}</p>
            <ol className="list-decimal pl-5">
              {row.checklist.map((item) => (
                <li key={item.step}>{item.text}</li>
              ))}
            </ol>
            {row.prepared.recurring_templates_url ? (
              <a href={row.prepared.recurring_templates_url} target="_blank" rel="noreferrer" className="underline">
                {t("recurring.openTemplates")}
              </a>
            ) : null}
            {canManage ? (
              <div className={`${ui.formActions} mt-2 items-end`}>
                <div>
                  <label htmlFor={`lx-rt-${row.id}`} className={ui.label}>
                    {t("recurring.templateId")}
                  </label>
                  <input id={`lx-rt-${row.id}`} className={ui.input} value={templateIds[row.id] ?? ""} maxLength={64} onChange={(e) => setTemplateIds((prev) => ({ ...prev, [row.id]: e.target.value }))} />
                </div>
                <button type="button" className={ui.buttonSm} disabled={busy || !(templateIds[row.id] ?? "").trim()} onClick={() => void act(row.id, "done")}>
                  {t("recurring.done")}
                </button>
                <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void act(row.id, "dismiss")}>
                  {t("recurring.dismiss")}
                </button>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
