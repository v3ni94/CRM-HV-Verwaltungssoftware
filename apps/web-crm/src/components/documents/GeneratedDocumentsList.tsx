"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type GeneratedDocument = {
  id: string;
  document_id: string;
  template_id: string | null;
  template_code: string | null;
  template_version: number | null;
  context_type: string | null;
  recipient_contact_id: string | null;
  delivery_channel: string | null;
  delivery_status: string | null;
  created_at: string;
};
export type TemplateOption = {
  id: string;
  code: string;
  name: string;
  version: number;
};

/** Query string of GET /generated-documents; empty filters are left out. */
export function generatedDocumentsQuery(
  templateId: string,
  from: string,
  to: string,
): string {
  const s = new URLSearchParams();
  if (templateId) s.set("template_id", templateId);
  if (from) s.set("created_from", from);
  if (to) s.set("created_to", to);
  s.set("limit", "100");
  return s.toString();
}

/** Produced documents (GA04-11) with template, version, context and delivery; filter by
 *  template and period; each row links to the stored document. */
export function GeneratedDocumentsList({
  templates,
}: {
  templates: TemplateOption[];
}) {
  const t = useTranslations("GeneratedDocuments");
  const [templateId, setTemplateId] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [rows, setRows] = useState<GeneratedDocument[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<GeneratedDocument[]>(
      `/api/bff/generated-documents?${generatedDocumentsQuery(templateId, from, to)}`,
    );
    if (res.ok) {
      setRows(res.data);
      setError(null);
    } else setError(res.message);
  }, [templateId, from, to]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex flex-col gap-4">
      <form
        className="flex flex-wrap items-end gap-3"
        aria-label={t("filter")}
        onSubmit={(e) => e.preventDefault()}
      >
        <label className={ui.label}>
          {t("template")}
          <select
            className={ui.input}
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
          >
            <option value="">{t("allTemplates")}</option>
            {templates.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name} (v{x.version})
              </option>
            ))}
          </select>
        </label>
        <label className={ui.label}>
          {t("from")}
          <input
            type="date"
            className={ui.input}
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </label>
        <label className={ui.label}>
          {t("to")}
          <input
            type="date"
            className={ui.input}
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </label>
      </form>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : rows === null ? null : rows.length === 0 ? (
        <p className={ui.help}>{t("empty")}</p>
      ) : (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("colCreated")}</th>
                <th>{t("colTemplate")}</th>
                <th>{t("colContext")}</th>
                <th>{t("colDelivery")}</th>
                <th>{t("colDocument")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="tabular-nums">
                    {formatDateTime(r.created_at)}
                  </td>
                  <td>
                    {r.template_code
                      ? `${r.template_code} (v${r.template_version ?? "?"})`
                      : t("noTemplate")}
                  </td>
                  <td>{r.context_type ?? ""}</td>
                  <td>
                    {r.delivery_channel
                      ? `${r.delivery_channel}${r.delivery_status ? `, ${r.delivery_status}` : ""}`
                      : t("notSent")}
                  </td>
                  <td>
                    <Link
                      href={`/dokumente/${r.document_id}`}
                      className="hover:underline"
                    >
                      {t("open")}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
