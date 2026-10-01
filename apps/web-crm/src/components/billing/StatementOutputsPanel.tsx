"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { problemMessage, readProblem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export type OutputPreview = { key: string; path: string; method: "GET" | "POST" };
type Output = { document_id: string; origin: string | null; title: string; created_at: string };

/** GA06-02, GA06-03: technical outputs of a statement run (info sheet, owner letter, § 35a
 *  proof). Previews are drafts; filing needs G3 and links the documents to the run. Legally
 *  relevant paragraphs stay marked "Text nicht freigegeben" until AA11-01/AA11-02 are decided. */
export function StatementOutputsPanel({ base, previews, filePath, enabled }: { base: string; previews: OutputPreview[]; filePath: string; enabled: boolean }) {
  const t = useTranslations("Billing.outputs");
  const [items, setItems] = useState<Output[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const res = await bff<{ items: Output[] }>(`${base}/outputs`);
    if (res.ok) setItems(res.data?.items ?? []);
  }, [base]);
  useEffect(() => {
    if (enabled) void load();
  }, [enabled, load]);
  if (!enabled) return null;

  const preview = async (p: OutputPreview) => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${base}/${p.path}`, { method: p.method, credentials: "same-origin", cache: "no-store" });
      if (!response.ok) {
        setError(problemMessage(await readProblem(response), response.status));
        return;
      }
      const href = URL.createObjectURL(await response.blob());
      window.open(href, "_blank", "noopener");
    } catch {
      setError(problemMessage(null, 0));
    } finally {
      setBusy(false);
    }
  };
  const file = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    const res = await bff(`${base}/${filePath}`, { method: "POST" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setNotice(t("filed"));
    await load();
  };
  return (
    <section className={ui.card} data-testid="statement-outputs">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={`${ui.notice} mt-1`}>{t("textNotice")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {notice ? <p className="text-sm">{notice}</p> : null}
      <div className="mt-2 flex flex-wrap gap-2">
        {previews.map((p) => (
          <button key={p.key} type="button" className={ui.secondary} disabled={busy} onClick={() => void preview(p)}>
            {t(`preview.${p.key}`)}
          </button>
        ))}
        <button type="button" className={ui.primary} disabled={busy} onClick={() => void file()}>
          {t("file")}
        </button>
      </div>
      <p className={`${ui.help} mt-1`}>{t("gate")}</p>
      {items.length === 0 ? (
        <p className={`${ui.help} mt-2`}>{t("none")}</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-1 text-sm">
          {items.map((i) => (
            <li key={i.document_id}>
              <Link href={`/dokumente/${i.document_id}`} className="underline">
                {i.title}
              </Link>{" "}
              <span className="text-muted">{formatDate(i.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
