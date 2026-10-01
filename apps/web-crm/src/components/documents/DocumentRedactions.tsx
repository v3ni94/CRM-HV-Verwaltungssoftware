"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useRef, useState, type FormEvent } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type Redaction = {
  id: string;
  original_document_id: string;
  copy_document_id: string;
  reason: string;
  scope: string;
  steps: string[];
  created_by: string | null;
  created_at: string;
  released_at: string | null;
  released_by: string | null;
  released_visibility: string[] | null;
};

const VISIBILITY = ["tenant", "owner", "provider", "board"] as const;

/** Geschwärzte Kopien eines Originals (7.9.2 PUE11, M25-01): Anlage mit Grund, Umfang und
 *  Bearbeitungsschritten, Freigabe durch eine zweite Person (Vier Augen) mit Auswahl der
 *  Portal-Sichtbarkeit, Liste am Dokument. Die Schwärzung selbst erfolgt außerhalb des
 *  Systems; hochgeladen wird die bereits geschwärzte Datei. Das Original bleibt unverändert. */
export function DocumentRedactions({
  documentId,
  initial,
  userId,
  canCreate,
  canApprove,
}: {
  documentId: string;
  initial: Redaction[];
  userId: string | null;
  canCreate: boolean;
  canApprove: boolean;
}) {
  const t = useTranslations("DocumentRedactions");
  const [items, setItems] = useState(initial);
  const [reason, setReason] = useState("");
  const [scope, setScope] = useState("");
  const [steps, setSteps] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [releasing, setReleasing] = useState<string | null>(null);
  const [visibility, setVisibility] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = async () => {
    const res = await bff<Redaction[]>(`/api/bff/documents/${documentId}/redactions`);
    if (res.ok) setItems(res.data);
  };

  const create = async (event: FormEvent) => {
    event.preventDefault();
    const file = fileRef.current?.files?.[0];
    const stepList = steps
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    if (!file || reason.trim().length < 5 || scope.trim().length < 3 || stepList.length === 0) {
      setError(t("errors.missing"));
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    const body = new FormData();
    body.set("file", file);
    body.set("reason", reason.trim());
    body.set("scope", scope.trim());
    body.set("steps", JSON.stringify(stepList));
    const res = await bff<Redaction>(`/api/bff/documents/${documentId}/redactions`, { method: "POST", body });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setMessage(t("created"));
    setReason("");
    setScope("");
    setSteps("");
    if (fileRef.current) fileRef.current.value = "";
    await refresh();
  };

  const release = async (id: string) => {
    if (visibility.length === 0) {
      setError(t("errors.visibility"));
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<Redaction>(`/api/bff/documents/${documentId}/redactions/${id}/release`, {
      method: "POST",
      body: JSON.stringify({ visibility }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setReleasing(null);
    setVisibility([]);
    setMessage(t("released"));
    await refresh();
  };

  const toggle = (value: string) =>
    setVisibility((current) => (current.includes(value) ? current.filter((v) => v !== value) : [...current, value]));

  return (
    <section className="flex flex-col gap-3" data-testid="document-redactions" aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="text-sm text-muted">{t("intro")}</p>
      {items.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((r) => {
            const own = r.created_by !== null && r.created_by === userId;
            return (
              <li key={r.id} className={`${ui.card} flex flex-col gap-1`} data-testid="redaction-item">
                <p className="text-sm font-medium">
                  {r.released_at ? t("statusReleased") : t("statusPending")}
                  {" · "}
                  <span className="tabular-nums">{formatDateTime(r.created_at)}</span>
                </p>
                <p className="text-sm">
                  <span className="text-muted">{t("reason")}: </span>
                  {r.reason}
                </p>
                <p className="text-sm">
                  <span className="text-muted">{t("scope")}: </span>
                  {r.scope}
                </p>
                <ul className="list-disc pl-5 text-sm">
                  {r.steps.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ul>
                {r.released_at ? (
                  <p className="text-xs text-muted">
                    {t("releasedAt", { at: formatDateTime(r.released_at) })}
                    {" · "}
                    {(r.released_visibility ?? []).map((v) => t(`visibility.${v}`)).join(", ")}
                  </p>
                ) : null}
                <div className="flex flex-wrap items-center gap-2">
                  <Link href={`/dokumente/${r.copy_document_id}`} className={ui.buttonSm}>
                    {t("openCopy")}
                  </Link>
                  {!r.released_at && canApprove ? (
                    own ? (
                      <span className="text-xs text-muted">{t("fourEyes")}</span>
                    ) : releasing === r.id ? null : (
                      <button type="button" className={ui.buttonSm} onClick={() => setReleasing(r.id)}>
                        {t("release")}
                      </button>
                    )
                  ) : null}
                </div>
                {releasing === r.id ? (
                  <fieldset className="flex flex-wrap items-center gap-3 text-sm">
                    <legend className="text-muted">{t("visibilityLegend")}</legend>
                    {VISIBILITY.map((v) => (
                      <label key={v} className="flex items-center gap-1">
                        <input type="checkbox" checked={visibility.includes(v)} onChange={() => toggle(v)} />
                        {t(`visibility.${v}`)}
                      </label>
                    ))}
                    <button type="button" className={ui.primary} disabled={busy} onClick={() => void release(r.id)}>
                      {t("releaseConfirm")}
                    </button>
                    <button type="button" className={ui.buttonSm} onClick={() => setReleasing(null)}>
                      {t("cancel")}
                    </button>
                  </fieldset>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      {canCreate ? (
        <form className={`${ui.card} flex flex-col gap-2`} onSubmit={(e) => void create(e)} data-testid="redaction-form">
          <h3 className="text-sm font-semibold">{t("new")}</h3>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted">{t("file")}</span>
            <input ref={fileRef} type="file" className={ui.input} aria-label={t("file")} accept="application/pdf,image/jpeg,image/png" />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted">{t("reason")}</span>
            <input className={ui.input} value={reason} maxLength={1000} onChange={(e) => setReason(e.target.value)} aria-label={t("reason")} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted">{t("scope")}</span>
            <input className={ui.input} value={scope} maxLength={2000} onChange={(e) => setScope(e.target.value)} aria-label={t("scope")} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted">{t("steps")}</span>
            <textarea className={ui.input} rows={3} value={steps} onChange={(e) => setSteps(e.target.value)} aria-label={t("steps")} />
            <span className="text-xs text-muted">{t("stepsHint")}</span>
          </label>
          <div>
            <button type="submit" className={ui.primary} disabled={busy}>
              {t("create")}
            </button>
          </div>
        </form>
      ) : null}
      {message ? <p className={ui.success}>{message}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
