"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { ui } from "@/lib/ui";
import type { PortalDocument } from "./types";

/** Belegliste mit Auswahl und Sammel-Download als ZIP mit Index (M25-06). Der Abruf läuft über
 *  den BFF und prüft dieselbe Sichtbarkeit wie der Einzelabruf. */
export function DocumentBundleList({
  rows,
  formatDate,
}: {
  rows: PortalDocument[];
  formatDate: (value: string) => string;
}) {
  const t = useTranslations("Documents");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/bff/portal/documents/bundle", {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ document_ids: [...selected] }),
      });
      if (!response.ok) {
        setError(t("bundleError"));
        return;
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "Belege.zip";
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(t("bundleError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className={ui.buttonSm}
          disabled={busy || selected.size === 0}
          onClick={download}
        >
          {t("bundleDownload", { count: selected.size })}
        </button>
        <button
          type="button"
          className={ui.buttonSm}
          onClick={() => setSelected(new Set(rows.slice(0, 100).map((row) => row.id)))}
        >
          {t("selectAll")}
        </button>
        {error ? (
          <span role="alert" className="text-sm text-danger">
            {error}
          </span>
        ) : null}
      </div>
      <ul className="flex flex-col gap-3">
        {rows.map((row) => (
          <li key={row.id} className={`${ui.card} flex flex-wrap items-center justify-between gap-2`}>
            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={selected.has(row.id)}
                onChange={() => toggle(row.id)}
                aria-label={t("select", { title: row.title })}
                className="mt-1"
              />
              <span className="flex flex-col gap-0.5">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{row.title}</span>
                  <span className={ui.badge} data-testid="document-state">
                    {row.is_new ? t("isNew") : t("read")}
                  </span>
                </span>
                {row.context ? <span className="text-xs text-subtle">{row.context}</span> : null}
                <span className="text-xs text-subtle">
                  {t("created")} {formatDate(row.created_at)}
                </span>
              </span>
            </label>
            <a
              href={`/api/portal-files/portal/documents/${row.id}/download`}
              className={ui.buttonSm}
              download={row.filename}
            >
              {t("download")}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
