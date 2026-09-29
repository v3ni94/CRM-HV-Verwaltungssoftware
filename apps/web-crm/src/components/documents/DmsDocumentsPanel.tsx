"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type DmsDocument = {
  id: number;
  title: string;
  created: string | null;
  added: string | null;
  correspondent: string | null;
  document_type: string | null;
  tags: string[];
  page_count: number | null;
  original_file_name: string | null;
  company?: string | null;
  preview_url: string;
  download_url: string;
};

type DmsDocumentPage = {
  data: DmsDocument[];
  meta: { page: number; per_page: number; total: number };
};

type CompanyOption = { option_id: string; label: string };

const PAGE_SIZE = 20;

export function DmsDocumentsPanel({ entity, id }: { entity: "ticket" | "property"; id: string }) {
  const t = useTranslations("DmsDocuments");
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<DmsDocumentPage | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Gesellschaftsfilter (Immoware Hub 7.2): Optionen aus der DMS-Anbindung, leer = kein Filter.
  const [companies, setCompanies] = useState<CompanyOption[]>([]);
  const [company, setCompany] = useState("");

  const basePath = entity === "ticket" ? `tickets/${id}/dms-documents` : `properties/${id}/dms-documents`;

  useEffect(() => {
    let active = true;
    void (async () => {
      const res = await bff<CompanyOption[]>("/api/bff/dms-documents/companies");
      if (active && res.ok) setCompanies(res.data);
    })();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    setLoaded(false);
    setError(null);
    void (async () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
      if (company) params.set("company", company);
      const res = await bff<DmsDocumentPage>(`/api/bff/${basePath}?${params.toString()}`);
      if (!active) return;
      setLoaded(true);
      if (res.ok) {
        setResult(res.data);
      } else if (res.status === 502) {
        // MHVP-DOC-0005: keine aktive Paperless-Anbindung.
        setError(t("errors.notConfigured"));
      } else if (res.status === 503) {
        // MHVP-DOC-0006: Paperless nicht erreichbar oder Fehlerantwort.
        setError(t("errors.unreachable"));
      } else {
        setError(res.message);
      }
    })();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [basePath, page, company]);

  const showCompany = companies.length > 0;

  const rows = result?.data ?? [];
  const total = result?.meta.total ?? 0;
  const hasNext = page * PAGE_SIZE < total;
  const hasPrev = page > 1;

  return (
    <section className="flex flex-col gap-2">
      <h2 className={ui.h2}>{t("title")}</h2>
      {showCompany ? (
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor={`dms-company-${entity}-${id}`} className="text-sm text-muted">
            {t("company.label")}
          </label>
          <select
            id={`dms-company-${entity}-${id}`}
            className={`${ui.input} w-auto`}
            value={company}
            onChange={(e) => {
              setCompany(e.target.value);
              setPage(1);
            }}
          >
            <option value="">{t("company.all")}</option>
            {companies.map((c) => (
              <option key={c.option_id} value={c.option_id}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      {!loaded ? (
        <p className="text-sm text-muted">{t("loading")}</p>
      ) : error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className={ui.tableCard}>
          <table className={ui.table} data-testid="dms-documents">
            <thead>
              <tr>
                <th>{t("columns.title")}</th>
                <th>{t("columns.date")}</th>
                <th>{t("columns.correspondent")}</th>
                <th>{t("columns.documentType")}</th>
                {showCompany ? <th>{t("columns.company")}</th> : null}
                <th>{t("columns.tags")}</th>
                <th>{t("columns.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((doc) => (
                <tr key={doc.id}>
                  <td className="font-medium">{doc.title}</td>
                  <td className="tabular-nums text-muted">{formatDate(doc.created ?? doc.added)}</td>
                  <td>{doc.correspondent ?? ""}</td>
                  <td>{doc.document_type ?? ""}</td>
                  {showCompany ? <td>{doc.company ?? ""}</td> : null}
                  <td className="text-xs text-muted">{doc.tags.join(", ")}</td>
                  <td>
                    <div className="flex flex-wrap gap-2">
                      {/* Same tab links (M31, no target=_blank); the download carries the attribute. */}
                      <a href={`/api/bff/dms-documents/${String(doc.id)}/file?kind=preview`} className={ui.buttonSm}>
                        {t("actions.preview")}
                      </a>
                      <a href={`/api/bff/dms-documents/${String(doc.id)}/file?kind=download`} download className={ui.buttonSm}>
                        {t("actions.download")}
                      </a>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {loaded && !error && total > PAGE_SIZE ? (
        <div className="flex items-center gap-2">
          <button type="button" className={ui.buttonSm} disabled={!hasPrev} onClick={() => setPage((p) => p - 1)}>
            {t("pagination.previous")}
          </button>
          <button type="button" className={ui.buttonSm} disabled={!hasNext} onClick={() => setPage((p) => p + 1)}>
            {t("pagination.next")}
          </button>
          <span className="text-xs text-muted">{t("pagination.page", { page })}</span>
        </div>
      ) : null}
    </section>
  );
}
