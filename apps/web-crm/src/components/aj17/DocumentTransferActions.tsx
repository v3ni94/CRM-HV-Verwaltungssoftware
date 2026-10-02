"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type UrlOut = { url: string; expires_in: number };

/** Signierte Download-URL (GAI-417, `GET /documents/{id}/download-url`) und erneutes Anstoßen der
 *  Spiegelung (`POST /documents/{id}/mirror`, Recht documents:update). */
export function DocumentTransferActions({ documentId, canMirror }: { documentId: string; canMirror: boolean }) {
  const t = useTranslations("Aj17.docs");
  const [link, setLink] = useState<UrlOut | null>(null);
  const [mirrored, setMirrored] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const createLink = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<UrlOut>(`/api/bff/documents/${documentId}/download-url`);
    setBusy(false);
    if (res.ok) setLink(res.data);
    else setError(res.message);
  };
  const mirror = async () => {
    setBusy(true);
    setError(null);
    setMirrored(false);
    const res = await bff(`/api/bff/documents/${documentId}/mirror`, { method: "POST", body: "{}" });
    setBusy(false);
    if (res.ok) setMirrored(true);
    else setError(res.message);
  };
  return (
    <div className="flex flex-col gap-2" data-testid="document-transfer">
      <div className="flex flex-wrap gap-2">
        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void createLink()}>
          {t("downloadUrl")}
        </button>
        {canMirror ? (
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void mirror()}>
            {t("mirror")}
          </button>
        ) : null}
      </div>
      {link ? (
        <p className="text-sm" data-testid="download-link">
          <a className="underline" href={link.url} rel="noopener noreferrer">
            {t("downloadOpen")}
          </a>{" "}
          <span className="text-muted">{t("downloadReady", { seconds: link.expires_in })}</span>
        </p>
      ) : null}
      {mirrored ? <p role="status" className={ui.success}>{t("mirrorDone")}</p> : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}
