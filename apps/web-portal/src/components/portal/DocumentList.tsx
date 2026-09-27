"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { ListToolbar, matchesSearch } from "@/components/portal/ListToolbar";
import type { PortalDocument } from "@/components/portal/types";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Metadaten aus GET /portal/documents/{id}. Der Abruf vermerkt serverseitig die
 *  Lesebestätigung "opened" (11.3, D34); weitere Felder als die Liste sind optional. */
type PortalDocumentDetail = PortalDocument & { category?: string | null };

type DetailState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "loaded"; detail: PortalDocumentDetail };

/** Dokumentenliste mit Textsuche über Titel und Dateiname sowie aufklappbaren Details je
 *  Dokument. Das erste Aufklappen ruft die Metadaten über den BFF ab und erzeugt damit die
 *  Lesebestätigung "opened"; die Liste selbst lädt weiterhin die Server-Seite. */
export function DocumentList({ documents }: { documents: PortalDocument[] }) {
  const t = useTranslations("Documents");
  const td = useTranslations("DocumentDetail");
  const tf = useTranslations("ListFilter");
  const format = useFormatter();
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [details, setDetails] = useState<Record<string, DetailState>>({});
  const day = (value: string) => format.dateTime(new Date(value), { day: "2-digit", month: "2-digit", year: "numeric" });

  async function toggle(id: string) {
    const nextOpen = !open[id];
    setOpen((prev) => ({ ...prev, [id]: nextOpen }));
    const existing = details[id];
    // Fetch on the first opening only; after an error the next opening retries.
    if (!nextOpen || (existing && existing.kind !== "error")) return;
    setDetails((prev) => ({ ...prev, [id]: { kind: "loading" } }));
    const result = await bff<PortalDocumentDetail>(`/api/bff/portal/documents/${id}`);
    setDetails((prev) => ({
      ...prev,
      [id]: result.ok ? { kind: "loaded", detail: result.data } : { kind: "error", message: result.message },
    }));
  }

  if (documents.length === 0) return <p className={ui.notice}>{t("empty")}</p>;
  const rows = documents.filter((row) => matchesSearch(search, row.title, row.filename));
  return (
    <div className={ui.sectionGap}>
      <ListToolbar search={search} onSearchChange={setSearch} />
      {rows.length === 0 ? <p className={ui.notice}>{tf("noResults")}</p> : null}
      <ul className="flex flex-col gap-3">
        {rows.map((row) => {
          const state = details[row.id];
          return (
            <li key={row.id} className={`${ui.card} flex flex-col gap-2`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="flex flex-col gap-0.5">
                  <span className="font-medium">{row.title}</span>
                  <span className="text-xs text-subtle">
                    {t("created")} {day(row.created_at)}
                  </span>
                </span>
                <span className="flex flex-wrap items-center gap-2">
                  <button type="button" className={ui.buttonSm} aria-expanded={!!open[row.id]} onClick={() => void toggle(row.id)}>
                    {open[row.id] ? td("hide") : td("show")}
                  </button>
                  <a
                    href={`/api/portal-files/portal/documents/${row.id}/download`}
                    className={ui.buttonSm}
                    download={row.filename}
                  >
                    {t("download")}
                  </a>
                </span>
              </div>
              {open[row.id] ? (
                <div className="rounded-md border border-border bg-surface px-3 py-2 text-sm">
                  {!state || state.kind === "loading" ? <p role="status">{td("loading")}</p> : null}
                  {state?.kind === "error" ? (
                    <p role="alert" className="text-danger-fg">
                      {state.message}
                    </p>
                  ) : null}
                  {state?.kind === "loaded" ? (
                    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                      {state.detail.category ? (
                        <>
                          <dt className={ui.label}>{td("category")}</dt>
                          <dd>{state.detail.category}</dd>
                        </>
                      ) : null}
                      <dt className={ui.label}>{td("filename")}</dt>
                      <dd className="break-words">{state.detail.filename}</dd>
                      <dt className={ui.label}>{td("created")}</dt>
                      <dd>{day(state.detail.created_at)}</dd>
                    </dl>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
