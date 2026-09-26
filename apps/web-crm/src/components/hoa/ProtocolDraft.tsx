"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type DraftResult = { document_id: string; title: string; missing: string[]; note: string };

/** Protokollentwurf der Eigentümerversammlung (A62): erzeugt ein PDF im Mandanten-CI und
 *  verknüpft es als Entwurf mit der Versammlung. Das unterschriebene Protokoll bleibt
 *  unberührt; der Entwurf hat keine Rechtsfolge. */
export function ProtocolDraft({
  meetingId,
  draftDocumentId,
  minutesDocumentId,
}: {
  meetingId: string;
  draftDocumentId: string | null;
  minutesDocumentId: string | null;
}) {
  const t = useTranslations("HoaWork.protocol");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DraftResult | null>(null);
  const documentId = result?.document_id ?? draftDocumentId;

  const create = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<DraftResult>(`/api/bff/hoa/meetings/${meetingId}/protocol-draft`, { method: "POST" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setResult(res.data);
    router.refresh();
  };

  return (
    <section className={ui.card} data-testid="protocol-draft">
      <h2 className={ui.subtitle}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("notice")}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button type="button" className={ui.button} disabled={busy} onClick={create}>
          {documentId ? t("recreate") : t("create")}
        </button>
        {documentId ? (
          <a className={ui.button} href={`/api/handover-files/documents/${documentId}/content`} download>
            {t("download")}
          </a>
        ) : null}
        {minutesDocumentId ? <span className="text-sm text-muted">{t("signedLinked")}</span> : null}
      </div>
      {result?.missing.length ? (
        <p className="mt-2 text-sm text-muted">
          {t("missing")}: {result.missing.join(", ")}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
