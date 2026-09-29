"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState, type FormEvent } from "react";

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
};

type DmsDocumentPage = {
  data: DmsDocument[];
  meta: { page: number; per_page: number; total: number };
};

type CompanyOption = { option_id: string; label: string };
type Criteria = { q: string; objectNumber: string; company: string };

const PAGE_SIZE = 25;
const fileUrl = (id: number, kind: "preview" | "download" | "thumb") => `/api/bff/dms-documents/${String(id)}/file?kind=${kind}`;

/** Document search over Paperless inside the CRM (Immoware Hub 7.2, 26.09.2026): full text,
 *  object number (Hub rule: exactly the number or "<Nummer>, ...") and company, combined with AND.
 *  Thumbnails, preview and download go through the API proxy; the Paperless token stays server
 *  side, dms.muellerhv.de is only needed for administration. */
export function DmsSearch() {
  const t = useTranslations("DmsSearch");
  const [companies, setCompanies] = useState<CompanyOption[]>([]);
  const [draft, setDraft] = useState<Criteria>({ q: "", objectNumber: "", company: "" });
  const [criteria, setCriteria] = useState<Criteria | null>(null);
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<DmsDocumentPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
    if (!criteria) return;
    let active = true;
    setBusy(true);
    setError(null);
    void (async () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
      if (criteria.q) params.set("q", criteria.q);
      if (criteria.objectNumber) params.set("object_number", criteria.objectNumber);
      if (criteria.company) params.set("company", criteria.company);
      const res = await bff<DmsDocumentPage>(`/api/bff/dms-documents?${params.toString()}`);
      if (!active) return;
      setBusy(false);
      if (res.ok) {
        setResult(res.data);
      } else {
        setResult(null);
        setError(res.status === 502 ? t("errors.notConfigured") : res.status === 503 ? t("errors.unreachable") : res.message);
      }
    })();
    return () => {
      active = false;
    };
  }, [criteria, page, t]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const next = { q: draft.q.trim(), objectNumber: draft.objectNumber.trim(), company: draft.company };
    if (!next.q && !next.objectNumber && !next.company) {
      setError(t("errors.criterion"));
      return;
    }
    setPage(1);
    setCriteria(next);
  };

  const rows = result?.data ?? [];
  const total = result?.meta.total ?? 0;

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      <form className="flex flex-wrap items-end gap-3" onSubmit={submit} data-testid="dms-search-form">
        <label className="flex min-w-64 flex-1 flex-col gap-1 text-sm">
          <span className="text-muted">{t("fields.q")}</span>
          <input className={ui.input} value={draft.q} onChange={(e) => setDraft({ ...draft, q: e.target.value })} placeholder={t("fields.qPlaceholder")} />
        </label>
        <label className="flex w-32 flex-col gap-1 text-sm">
          <span className="text-muted">{t("fields.objectNumber")}</span>
          <input
            className={ui.input}
            inputMode="numeric"
            maxLength={3}
            pattern="[0-9]{1,3}"
            value={draft.objectNumber}
            onChange={(e) => setDraft({ ...draft, objectNumber: e.target.value.replace(/[^0-9]/g, "") })}
          />
        </label>
        {companies.length > 0 ? (
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted">{t("fields.company")}</span>
            <select className={`${ui.input} w-auto`} value={draft.company} onChange={(e) => setDraft({ ...draft, company: e.target.value })}>
              <option value="">{t("fields.companyAll")}</option>
              {companies.map((c) => (
                <option key={c.option_id} value={c.option_id}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("search")}
        </button>
      </form>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {criteria && !error && !busy && rows.length === 0 ? <p className="text-sm text-muted">{t("empty")}</p> : null}
      {rows.length > 0 ? (
        <>
          <p className="text-xs text-muted">{t("total", { total })}</p>
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="dms-search-results">
            {rows.map((doc) => (
              <li key={doc.id} className="flex gap-3 rounded-lg border border-border p-3">
                {/* eslint-disable-next-line @next/next/no-img-element -- proxied Paperless thumbnail, no Next image optimisation */}
                <img src={fileUrl(doc.id, "thumb")} alt="" loading="lazy" className="h-28 w-20 shrink-0 rounded border border-border object-cover" />
                <div className="flex min-w-0 flex-col gap-1 text-sm">
                  <span className="truncate font-medium" title={doc.title}>
                    {doc.title}
                  </span>
                  <span className="text-xs text-muted tabular-nums">{formatDate(doc.created ?? doc.added)}</span>
                  <span className="text-xs text-muted">{[doc.document_type, doc.correspondent, doc.company].filter(Boolean).join(" · ")}</span>
                  {doc.tags.length > 0 ? <span className="truncate text-xs text-muted">{doc.tags.join(", ")}</span> : null}
                  <div className="mt-auto flex flex-wrap gap-2">
                    <a href={fileUrl(doc.id, "preview")} className={ui.buttonSm}>
                      {t("actions.preview")}
                    </a>
                    <a href={fileUrl(doc.id, "download")} download className={ui.buttonSm}>
                      {t("actions.download")}
                    </a>
                  </div>
                </div>
              </li>
            ))}
          </ul>
          {total > PAGE_SIZE ? (
            <div className="flex items-center gap-2">
              <button type="button" className={ui.buttonSm} disabled={page <= 1 || busy} onClick={() => setPage((p) => p - 1)}>
                {t("pagination.previous")}
              </button>
              <button type="button" className={ui.buttonSm} disabled={page * PAGE_SIZE >= total || busy} onClick={() => setPage((p) => p + 1)}>
                {t("pagination.next")}
              </button>
              <span className="text-xs text-muted">{t("pagination.page", { page })}</span>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
