"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Protokollabschluss der Eigentümerversammlung (R07-01): Antrag mit dem unterschriebenen
 *  Protokoll, Bestätigung durch eine zweite Person, danach Sperre der Versammlung. Eine
 *  Protokollfrist wird nur als Hinweis gezeigt, nie berechnet oder gesperrt. */
export function MeetingClose({
  meetingId,
  status,
  minutesDocumentId,
  closeRequestedAt,
  closedAt,
}: {
  meetingId: string;
  status: string;
  minutesDocumentId: string | null;
  closeRequestedAt: string | null;
  closedAt: string | null;
}) {
  const t = useTranslations("HoaWork.meetingClose");
  const router = useRouter();
  const [documentId, setDocumentId] = useState(minutesDocumentId ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const call = async (path: string, body?: unknown) => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/hoa/meetings/${meetingId}/${path}`, {
      method: "POST",
      ...(body
        ? {
            body: JSON.stringify(body),
            headers: { "content-type": "application/json" },
          }
        : {}),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    router.refresh();
  };

  if (!["held", "closing", "closed"].includes(status)) return null;
  return (
    <section className={ui.card} data-testid="meeting-close">
      <h2 className={ui.subtitle}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("notice")}</p>
      <p className="mt-1 text-sm text-muted">{t("periodNote")}</p>
      {status === "closed" ? (
        <p className="mt-2 text-sm">
          {t("closed", { date: closedAt ? formatDateTime(closedAt) : "" })}
        </p>
      ) : (
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <label className="flex flex-col text-sm">
            {t("documentId")}
            <input
              className={ui.input}
              value={documentId}
              disabled={status === "closing"}
              onChange={(e) => setDocumentId(e.target.value)}
            />
          </label>
          {status === "held" ? (
            <button
              type="button"
              className={ui.button}
              disabled={busy || !documentId.trim()}
              onClick={() =>
                call("close", { minutes_document_id: documentId.trim() })
              }
            >
              {t("request")}
            </button>
          ) : (
            <>
              <button
                type="button"
                className={ui.button}
                disabled={busy}
                onClick={() =>
                  call("close/confirm", {
                    minutes_document_id: documentId.trim(),
                  })
                }
              >
                {t("confirm")}
              </button>
              <button
                type="button"
                className={ui.button}
                disabled={busy}
                onClick={() => call("close/withdraw")}
              >
                {t("withdraw")}
              </button>
            </>
          )}
        </div>
      )}
      {status === "closing" && closeRequestedAt ? (
        <p className="mt-2 text-sm text-muted">
          {t("requested", { date: formatDateTime(closeRequestedAt) })}
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
