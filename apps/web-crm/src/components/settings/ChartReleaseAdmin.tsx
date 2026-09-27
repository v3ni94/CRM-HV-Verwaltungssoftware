"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Shapes of /api/v1/accounting/templates (M10-01/M10-02 release workflow, V8). */
export type ChartTemplate = {
  id: string;
  code: string;
  name: string;
  version: number;
  released: boolean;
  released_at: string | null;
  released_by: string | null;
  status: "draft" | "in_review" | "released";
  review_requested_at: string | null;
  review_requested_by: string | null;
  release_comment: string | null;
  release_document_id: string | null;
  supersedes_id: string | null;
  accounts: Record<string, unknown>[];
};

const BASE = "/api/bff/accounting/templates";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
}

export function ChartReleaseAdmin({
  initial,
  canManage,
  canApprove,
}: {
  initial: ChartTemplate[];
  canManage: boolean;
  canApprove: boolean;
}) {
  const t = useTranslations("ChartRelease");
  const [templates, setTemplates] = useState<ChartTemplate[]>(initial);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState<ChartTemplate | null>(null);
  const [comment, setComment] = useState("");
  const [documentId, setDocumentId] = useState("");

  async function reload() {
    const res = await bff<ChartTemplate[]>(BASE);
    if (res.ok) setTemplates(res.data);
  }

  async function act(path: string, done: string, init: RequestInit = { method: "POST" }) {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<ChartTemplate>(path, init);
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return null;
    }
    setMessage(done);
    await reload();
    return res.data;
  }

  async function submitRelease(event: React.FormEvent) {
    event.preventDefault();
    if (!dialog) return;
    const body = { comment: comment.trim() || null, document_id: documentId.trim() || null };
    const result = await act(`${BASE}/${dialog.id}/release`, t("releasedMessage"), {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (result) {
      setDialog(null);
      setComment("");
      setDocumentId("");
    }
  }

  // Group by code: the highest version first, older versions as history.
  const codes = Array.from(new Set(templates.map((tpl) => tpl.code)));

  return (
    <section className={ui.sectionGap}>
      <p className={ui.notice}>{t("intro")}</p>
      {!canManage && !canApprove ? <p className={ui.small}>{t("readOnly")}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className={ui.success}>
          {message}
        </p>
      ) : null}

      {templates.length === 0 ? (
        <div className={ui.card}>
          <p className={ui.small}>{t("noTemplates")}</p>
          {canManage ? (
            <button
              type="button"
              className={`${ui.primary} mt-2`}
              disabled={busy}
              onClick={() => act(`${BASE}/default`, t("created"))}
            >
              {t("createDefault")}
            </button>
          ) : null}
        </div>
      ) : null}

      {codes.map((code) => {
        const versions = templates.filter((tpl) => tpl.code === code).sort((a, b) => b.version - a.version);
        const latest = versions[0];
        if (!latest) return null;
        return (
          <div key={code} className={ui.card} data-testid={`chart-${code}`}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className={ui.h2}>
                {latest.name} ({latest.code}), {t("version", { version: latest.version })}
              </h2>
              <span className={ui.small}>
                {t(`status.${latest.status}`)}, {t("accounts", { count: latest.accounts.length })}
              </span>
            </div>
            {latest.status === "released" ? (
              <p className={`${ui.small} mt-1`}>
                {t("releasedAt", { date: formatDate(latest.released_at) })}
                {latest.release_comment ? `, ${t("comment")}: ${latest.release_comment}` : ""}
                {latest.release_document_id ? `, ${t("document")}: ${latest.release_document_id}` : ""}
              </p>
            ) : null}
            {latest.status === "in_review" ? (
              <p className={`${ui.small} mt-1`}>{t("reviewRequestedAt", { date: formatDate(latest.review_requested_at) })}</p>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2">
              {canManage && latest.status === "draft" ? (
                <button type="button" className={ui.button} disabled={busy} onClick={() => act(`${BASE}/${latest.id}/submit-review`, t("submitted"))}>
                  {t("submitReview")}
                </button>
              ) : null}
              {canManage && latest.status === "in_review" ? (
                <button type="button" className={ui.button} disabled={busy} onClick={() => act(`${BASE}/${latest.id}/back-to-draft`, t("submitted"))}>
                  {t("backToDraft")}
                </button>
              ) : null}
              {canApprove && latest.status !== "released" ? (
                <button type="button" className={ui.primary} disabled={busy} onClick={() => setDialog(latest)}>
                  {t("release")}
                </button>
              ) : null}
              {canManage && latest.status === "released" ? (
                <button
                  type="button"
                  className={ui.button}
                  disabled={busy}
                  onClick={async () => {
                    const created = await act(`${BASE}/${latest.id}/versions`, "");
                    if (created) setMessage(t("versionCreated", { version: created.version }));
                  }}
                >
                  {t("newVersion")}
                </button>
              ) : null}
              <a className={ui.button} href={`${BASE}/${latest.id}/export?format=csv`} download>
                {t("exportCsv")}
              </a>
              <a className={ui.button} href={`${BASE}/${latest.id}/export?format=pdf`} download>
                {t("exportPdf")}
              </a>
            </div>

            <h3 className={`${ui.h3} mt-4`}>{t("history")}</h3>
            {versions.length <= 1 ? (
              <p className={`${ui.small} mt-1`}>{t("historyEmpty")}</p>
            ) : (
              <div className="mt-1 overflow-x-auto">
                <table className={ui.table}>
                  <thead>
                    <tr>
                      <th className="num">{t("colVersion")}</th>
                      <th>{t("colStatus")}</th>
                      <th>{t("colReleased")}</th>
                      <th>{t("colBy")}</th>
                      <th>{t("colComment")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {versions.map((v) => (
                      <tr key={v.id}>
                        <td className={`num ${ui.num}`}>{v.version}</td>
                        <td>{t(`status.${v.status}`)}</td>
                        <td>{formatDate(v.released_at)}</td>
                        <td className={ui.mono}>{v.released_by ?? ""}</td>
                        <td>{v.release_comment ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      })}

      {dialog ? (
        <form role="dialog" aria-labelledby="chart-release-title" className={ui.card} onSubmit={submitRelease}>
          <h3 id="chart-release-title" className={ui.h3}>
            {t("dialogTitle", { code: dialog.code, version: dialog.version })}
          </h3>
          <p className={`${ui.small} mt-1`}>{t("dialogHelp")}</p>
          <label className={`${ui.label} mt-3`} htmlFor="chart-release-comment">
            {t("commentLabel")}
          </label>
          <textarea
            id="chart-release-comment"
            className={`${ui.input} min-h-20`}
            value={comment}
            placeholder={t("commentPlaceholder")}
            onChange={(e) => setComment(e.target.value)}
          />
          <label className={`${ui.label} mt-3`} htmlFor="chart-release-document">
            {t("documentLabel")}
          </label>
          <input id="chart-release-document" className={ui.input} value={documentId} onChange={(e) => setDocumentId(e.target.value)} />
          <p className={ui.help}>{t("documentHelp")}</p>
          <div className={`${ui.formActions} mt-3`}>
            <button type="submit" className={ui.primary} disabled={busy}>
              {t("confirmRelease")}
            </button>
            <button type="button" className={ui.button} onClick={() => setDialog(null)}>
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
