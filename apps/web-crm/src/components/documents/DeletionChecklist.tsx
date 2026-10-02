"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Item = { target: string; status: string; detail: string | null };
type Checklist = {
  document_id: string;
  status: "done" | "open" | "held" | "in_trash";
  items: Item[];
  purge_at?: string | null;
};

/** Löschcheckliste je Ziel mit Nachlauf (AC07, GA08-08). Backups werden nur genannt, nicht
 * bearbeitet; ein wiederhergestelltes Dokument unter Sperre bleibt erhalten. */
export function DeletionChecklist({ documentId, canDelete }: { documentId: string; canDelete: boolean }) {
  const t = useTranslations("DeletionProposals.checklist");
  const tCommon = useTranslations("Common");
  const [data, setData] = useState<Checklist | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const base = `/api/bff/documents/deletions/${documentId}`;

  async function run(path: string, init?: RequestInit) {
    setBusy(true);
    setError(null);
    const res = await bff<Checklist>(path, init);
    setBusy(false);
    if (res.ok) setData(res.data);
    else setError(res.message);
  }

  if (data === null) {
    return (
      <div>
        <button type="button" className={ui.button} disabled={busy} onClick={() => void run(`${base}/checklist`)}>
          {t("show")}
        </button>
        {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      </div>
    );
  }
  return (
    <div className={ui.small}>
      <p>{t(`overall.${data.status}`)}</p>
      <ul>
        {data.items.length === 0 ? <li className="text-sm text-muted">{tCommon("emptyList")}</li> : null}
        {data.items.map((i) => (
          <li key={i.target}>
            {t(`target.${i.target}`)}: {t(`status.${i.status}`)}
            {i.detail ? ` (${i.detail})` : ""}
          </li>
        ))}
      </ul>
      {canDelete && data.status === "open" ? (
        <button
          type="button"
          className={ui.button}
          disabled={busy}
          onClick={() => void run(`${base}/follow-up`, { method: "POST" })}
        >
          {t("followUp")}
        </button>
      ) : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}
