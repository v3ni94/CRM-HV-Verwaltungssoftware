"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type TextBlockCode = { code: string; label: string; released: boolean; approved_version: number | null };
export type TextBlock = {
  id: string;
  code: string;
  version: number;
  title: string;
  body: string;
  source_note: string | null;
  status: "draft" | "submitted" | "approved" | "retired";
  reject_reason: string | null;
};

const VARIANT: Record<TextBlock["status"], StatusPillVariant> = {
  draft: "neutral",
  submitted: "warning",
  approved: "success",
  retired: "neutral",
};

/** Pflegemaske der Textbausteine: Ampel je Code, Entwurf, Einreichen, Freigabe durch eine
 *  zweite Person. Ohne freigegebene Version zeigt die Ausgabe "Text nicht freigegeben". */
export function TextBlocksAdmin({
  codes,
  blocks,
  canEdit,
  canApprove,
}: {
  codes: TextBlockCode[];
  blocks: TextBlock[];
  canEdit: boolean;
  canApprove: boolean;
}) {
  const t = useTranslations("TextBlocks");
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, { title: string; body: string; source: string }>>({});

  async function call(path: string, method: string, body?: unknown) {
    setError(null);
    const res = await bff(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
    if (!res.ok) {
      setError(res.message || t("error"));
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {codes.map((c) => {
        const mine = blocks.filter((b) => b.code === c.code);
        const draft = drafts[c.code] ?? { title: c.label, body: "", source: "" };
        return (
          <section key={c.code} className="flex min-w-0 flex-col gap-2 rounded-md border border-line p-3" data-testid={`text-block-${c.code}`}>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-semibold">{c.label}</h2>
              <StatusPill
                variant={c.released ? "success" : "warning"}
                label={c.released ? t("released", { version: c.approved_version ?? 0 }) : t("notReleased")}
              />
            </div>
            {mine.map((b) => (
              <div key={b.id} className="flex min-w-0 flex-col gap-1 border-t border-line pt-2 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span>v{b.version}</span>
                  <StatusPill variant={VARIANT[b.status]} label={t(`status.${b.status}`)} />
                </div>
                <p className="whitespace-pre-wrap break-words">{b.body}</p>
                {b.reject_reason ? <p className="text-xs text-muted">{b.reject_reason}</p> : null}
                <div className={ui.formActions}>
                  {canEdit && b.status === "draft" ? (
                    <button type="button" className={ui.buttonSm} onClick={() => call(`/api/bff/document-text-blocks/${b.id}/submit`, "POST")}>
                      {t("submit")}
                    </button>
                  ) : null}
                  {canApprove && b.status === "submitted" ? (
                    <>
                      <button type="button" className={ui.buttonSm} onClick={() => call(`/api/bff/document-text-blocks/${b.id}/approve`, "POST")}>
                        {t("approve")}
                      </button>
                      <button
                        type="button"
                        className={ui.buttonSm}
                        onClick={() => {
                          const reason = window.prompt(t("rejectReason"));
                          if (reason) void call(`/api/bff/document-text-blocks/${b.id}/reject`, "POST", { reason });
                        }}
                      >
                        {t("reject")}
                      </button>
                    </>
                  ) : null}
                  {canApprove && b.status === "approved" ? (
                    <button type="button" className={ui.buttonSm} onClick={() => call(`/api/bff/document-text-blocks/${b.id}/retire`, "POST")}>
                      {t("retire")}
                    </button>
                  ) : null}
                </div>
              </div>
            ))}
            {canEdit ? (
              <form
                className="flex min-w-0 flex-col gap-2 border-t border-line pt-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void call("/api/bff/document-text-blocks", "POST", {
                    code: c.code,
                    title: draft.title,
                    body: draft.body,
                    source_note: draft.source || null,
                  });
                }}
              >
                <label className={ui.label} htmlFor={`tb-body-${c.code}`}>{t("bodyField")}</label>
                <textarea
                  id={`tb-body-${c.code}`}
                  className={ui.input}
                  rows={4}
                  value={draft.body}
                  onChange={(e) => setDrafts({ ...drafts, [c.code]: { ...draft, body: e.target.value } })}
                />
                <label className={ui.label} htmlFor={`tb-src-${c.code}`}>{t("sourceField")}</label>
                <input
                  id={`tb-src-${c.code}`}
                  className={ui.input}
                  value={draft.source}
                  onChange={(e) => setDrafts({ ...drafts, [c.code]: { ...draft, source: e.target.value } })}
                />
                <div className={ui.formActions}>
                  <button type="submit" className={ui.button} disabled={!draft.body.trim()}>
                    {t("newVersion")}
                  </button>
                </div>
              </form>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
