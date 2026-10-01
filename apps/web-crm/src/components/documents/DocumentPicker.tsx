"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Hit = { id: string; title: string; filename: string; created_at: string };

/** Dokumentauswahl per Suche im Dokumentenbestand (GET /documents). Ersetzt freie ID-Felder:
 *  gespeichert wird nur die ID eines vorhandenen Dokuments. Das Hochladen bleibt im
 *  Dokumentenbereich; hier wird nur ausgewählt. */
export function DocumentPicker({
  value,
  onChange,
  disabled = false,
  label,
}: {
  value: string;
  onChange: (documentId: string, title: string | null) => void;
  disabled?: boolean;
  label: string;
}) {
  const t = useTranslations("DocumentPicker");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const search = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ items: Hit[] }>(
      `/api/bff/documents?q=${encodeURIComponent(query.trim())}&is_draft=false&page_size=10`,
    );
    setBusy(false);
    if (!res.ok) {
      setError(t("error"));
      return;
    }
    setHits(res.data.items ?? []);
  };

  return (
    <div className="flex flex-col gap-1 text-sm" data-testid="document-picker">
      <span>{label}</span>
      {value ? (
        <div className="flex flex-wrap items-center gap-2">
          <span data-testid="document-picker-chosen">
            {title ? t("chosen", { title }) : t("chosenId", { id: value })}
          </span>
          {!disabled ? (
            <button
              type="button"
              className={ui.button}
              onClick={() => {
                setTitle(null);
                onChange("", null);
              }}
            >
              {t("clear")}
            </button>
          ) : null}
        </div>
      ) : null}
      {!disabled ? (
        <>
          <div className="flex flex-wrap gap-2">
            <input
              className={ui.input}
              aria-label={t("search")}
              placeholder={t("search")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button type="button" className={ui.button} disabled={busy || query.trim().length < 2} onClick={() => void search()}>
              {t("searchBtn")}
            </button>
          </div>
          <p className="text-xs text-muted">{t("uploadHint")}</p>
        </>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {hits && !disabled ? (
        hits.length === 0 ? (
          <p className="text-muted">{t("none")}</p>
        ) : (
          <ul className="flex flex-col gap-1" data-testid="document-picker-hits">
            {hits.map((h) => (
              <li key={h.id} className="flex flex-wrap items-center gap-2">
                <span>
                  {h.title} ({formatDate(h.created_at)})
                </span>
                <button
                  type="button"
                  className={ui.button}
                  onClick={() => {
                    setTitle(h.title);
                    setHits(null);
                    onChange(h.id, h.title);
                  }}
                >
                  {t("pick")}
                </button>
              </li>
            ))}
          </ul>
        )
      ) : null}
    </div>
  );
}
