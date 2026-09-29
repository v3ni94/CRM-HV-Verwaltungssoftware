"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { ResponsiveList } from "@/components/ui/ResponsiveList";
import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { dmsBase, type DmsDocumentPage, type DmsLinkResult } from "@/lib/objektakte-dms";
import { ui } from "@/lib/ui";

const PAGE_SIZE = 50;

/** M29 Stufe 4: document list of one object from objektakte with the jump into Google Drive and
 *  the CRM document it is linked to. "Als CRM-Dokumente verknüpfen" links every document of the
 *  object (matching over Drive file id and sha256, no copy of the original). */
export function DmsDocuments({ number }: { number: string }) {
  const t = useTranslations("Dms");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<DmsDocumentPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DmsLinkResult | null>(null);

  const load = useCallback(
    async (target: number) => {
      setError(null);
      const res = await bff<DmsDocumentPage>(`${dmsBase(number)}/documents?page=${target}&page_size=${PAGE_SIZE}`);
      if (res.ok) setData(res.data);
      else setError(res.message);
    },
    [number],
  );

  useEffect(() => {
    void load(page);
  }, [load, page]);

  const link = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<DmsLinkResult>(`${dmsBase(number)}/documents/link`, { method: "POST" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setResult(res.data);
    await load(page);
  };

  const pages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1;

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("documents.title")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={ui.h2}>{t("documents.title")}</h2>
        <button type="button" className={ui.buttonSm} onClick={() => void link()} disabled={busy} data-testid="dms-link">
          {t("documents.link")}
        </button>
      </div>
      <p className="text-xs text-muted">{t("documents.linkHint")}</p>
      {result ? (
        <p className={ui.success} data-testid="dms-link-result">
          {t("documents.linkResult", {
            created: result.created,
            linked: result.linked,
            unchanged: result.unchanged + result.updated,
            invalid: result.invalid,
          })}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {!data ? null : data.results.length === 0 ? (
        <p className="text-sm text-muted">{t("documents.empty")}</p>
      ) : (
        <ResponsiveList
          rows={data.results}
          keyOf={(d) => String(d.id)}
          testId="dms-documents"
          card={(d) => (
            <div className="flex flex-col gap-1">
              <span className="font-medium [overflow-wrap:anywhere]">{d.title}</span>
              <span className="text-sm text-muted">{[d.doc_type, [d.category, d.subfolder].filter(Boolean).join(" / ")].filter(Boolean).join(" · ")}</span>
              <span className="text-sm tabular-nums text-muted">{formatDate(d.filed_at)}</span>
              <div className="flex flex-wrap gap-3">
                {d.drive_url ? (
                  <a href={d.drive_url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center text-sm font-medium hover:underline">
                    {t("documents.openDrive")}
                  </a>
                ) : null}
                {d.crm_document_id ? (
                  <Link href={`/dokumente/${d.crm_document_id}`} className="inline-flex min-h-11 items-center text-sm font-medium hover:underline">
                    {t("documents.openCrm")}
                  </Link>
                ) : (
                  <span className={ui.badge}>{t("documents.notLinked")}</span>
                )}
              </div>
            </div>
          )}
          table={
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("documents.colTitle")}</th>
                <th>{t("documents.colFolder")}</th>
                <th>{t("documents.colType")}</th>
                <th>{t("documents.colFiled")}</th>
                <th>{t("documents.colLinks")}</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((d) => (
                <tr key={d.id}>
                  <td>{d.title}</td>
                  <td>{[d.category, d.subfolder].filter(Boolean).join(" / ")}</td>
                  <td>{d.doc_type ?? ""}</td>
                  <td className="tabular-nums">{formatDate(d.filed_at)}</td>
                  <td>
                    <div className="flex flex-wrap gap-2">
                      {d.drive_url ? (
                        <a href={d.drive_url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium hover:underline">
                          {t("documents.openDrive")}
                        </a>
                      ) : null}
                      {d.crm_document_id ? (
                        <Link href={`/dokumente/${d.crm_document_id}`} className="text-sm font-medium hover:underline">
                          {t("documents.openCrm")}
                        </Link>
                      ) : (
                        <span className={ui.badge}>{t("documents.notLinked")}</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          }
        />
      )}
      {data && pages > 1 ? (
        <div className="flex items-center gap-2 text-sm">
          <button type="button" className={ui.buttonSm} disabled={page <= 1} onClick={() => setPage(page - 1)}>
            {t("documents.previous")}
          </button>
          <span className="tabular-nums">{t("documents.pageOf", { page, pages })}</span>
          <button type="button" className={ui.buttonSm} disabled={page >= pages} onClick={() => setPage(page + 1)}>
            {t("documents.next")}
          </button>
        </div>
      ) : null}
    </section>
  );
}
