"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type AssistantLogRow = {
  id: string;
  account_id: string;
  question: string;
  answer: string | null;
  mode: "ai" | "search";
  status: "answered" | "not_answerable" | "failed" | "search_hits" | "no_sources";
  reason_code: string | null;
  technical_reason: string | null;
  sources: { document_id: string; title: string }[];
  scope_documents: number;
  created_at: string;
};

/** Protokoll des Portal-Assistenten (AE28, M7-06): letzte Fragen mit Art, Ergebnis, Quellen und
 *  Grund, falls keine KI-Antwort entstand. Fragen sind maskiert gespeichert (IBAN, E-Mail,
 *  Telefon, Adressen). Nur lesend, Recht Mandanteneinstellungen. */
export function AssistantLogPanel() {
  const t = useTranslations("AssistantLog");
  const format = useFormatter();
  const [rows, setRows] = useState<AssistantLogRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void bff<AssistantLogRow[]>("/api/bff/portal-admin/assistant/log?limit=20").then((res) => {
      if (!live) return;
      if (res.ok) setRows(res.data);
      else setError(res.message);
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className={`${ui.card} flex flex-col gap-2`} data-testid="assistant-log">
      <h3 className="text-base font-semibold">{t("title")}</h3>
      <p className={ui.help}>{t("note")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {rows && rows.length === 0 ? <p className="text-sm text-muted">{t("empty")}</p> : null}
      {rows && rows.length > 0 ? (
        <div className={ui.tableScroll}>
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th scope="col" className="py-1 pr-3">
                  {t("when")}
                </th>
                <th scope="col" className="py-1 pr-3">
                  {t("result")}
                </th>
                <th scope="col" className="py-1 pr-3">
                  {t("question")}
                </th>
                <th scope="col" className="py-1">
                  {t("reason")}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="align-top">
                  <td className="py-1 pr-3 whitespace-nowrap">
                    {format.dateTime(new Date(r.created_at), { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}
                  </td>
                  <td className="py-1 pr-3">
                    {t(`mode.${r.mode}`)}, {t(`status.${r.status}`)}
                    {r.sources.length > 0 ? ` (${t("sourceCount", { count: r.sources.length })})` : ""}
                  </td>
                  <td className="py-1 pr-3 break-words">{r.question}</td>
                  <td className="py-1 break-words">{r.technical_reason ?? r.reason_code ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
